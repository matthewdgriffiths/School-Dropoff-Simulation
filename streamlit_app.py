import random

import matplotlib.pyplot as plt
import numpy as np
import simpy
import streamlit as st
from datetime import time, timedelta
from matplotlib.ticker import FuncFormatter
from PIL import Image, ImageDraw, ImageFont


# -----------------------------
# Shared simulation logic
# -----------------------------
# This section contains the core maths and simulation rules used by both the
# comparison tab and the visualizer tab. The code models cars arriving at a
# school gate, parking for a random amount of time, then leaving the site.

WINDOW_SIZE = (800, 520)
ROAD_RECT = (40, 80, 760, 450)
BACKGROUND = (24, 29, 38)
ROAD = (49, 58, 69)
ROAD_EDGE = (130, 143, 157)
TEXT = (235, 240, 245)
ARRIVING = (76, 190, 232)
PARKED = (244, 177, 68)
LEAVING = (116, 215, 133)
PERSON = (250, 245, 230)
GATE = (220, 95, 95)
PERSON_WALK_MINUTES = 2.0


def time_to_minutes(value):
    # Convert a Python time object like 08:45 into a number of minutes since
    # midnight. This makes time comparisons much easier in the simulation.
    return value.hour * 60 + value.minute


def format_clock_time(start_time, elapsed_minutes):
    # Build a human-friendly clock string from the simulation start time plus a
    # number of elapsed minutes.
    absolute_minutes = time_to_minutes(start_time) + elapsed_minutes
    hour = int(absolute_minutes // 60) % 24
    minute = int(absolute_minutes % 60)
    return f"{hour:02d}:{minute:02d}"


def arrival_time(open_time, close_time, minutes_before_open):
    # The full arrival window is:
    #   [gate_open - arrival_window, gate_close]
    # So if gate opens at 08:50 and arrival_window = 10, the first cars are
    # allowed to appear at 08:40 and can continue arriving until the gate closes.
    start_of_window = max(0, open_time - minutes_before_open)
    if close_time < start_of_window:
        return start_of_window
    return random.uniform(start_of_window, close_time)


def dropoff_time(lower, upper):
    # After a car arrives, it remains parked for a random duration sampled from
    # the lower and upper bounds (in whole minutes in the UI).
    return random.uniform(lower, upper)


def departure_time(mean_minutes):
    # Once the parking duration ends, the car takes a random amount of time to
    # leave the parking area. The departure delay is sampled from a Poisson
    # distribution using the configured mean in minutes.
    return max(1.0, float(np.random.poisson(mean_minutes)))


def car(env, name, gate_open, gate_close, drop_lower, drop_upper,
    departure_mean, wait_until_close, parked_cars):
    # A car is introduced at its actual arrival time. It then occupies a parking
    # space immediately. If the departure is limited until gate closing, the car
    # stays parked until the gate closes even if its parking duration would have
    # ended earlier. The final departure phase also takes a configurable amount of
    # time before the car is removed from the occupied count.
    parked_cars["count"] += 1
    parking_duration = dropoff_time(drop_lower, drop_upper)
    departure_duration = departure_time(departure_mean)
    if wait_until_close:
        gate_departure = gate_close
        if env.now + parking_duration < gate_departure:
            yield env.timeout(gate_departure - env.now)
        else:
            yield env.timeout(max(0, gate_departure - env.now))
    else:
        yield env.timeout(parking_duration)
    yield env.timeout(departure_duration)
    parked_cars["count"] -= 1


def arrival_process(env, open_time, close_time, minutes_before_open,
                    drop_lower, drop_upper, departure_mean, total_cars,
                    wait_until_close, parked_cars):
    # Create the schedule of when each car should arrive. The arrivals are sorted
    # so the queue looks realistic. The arrival window is explicitly:
    #   [gate_open - arrival_window, gate_close]
    # which means a 10-minute window before opening still allows cars to arrive
    # from 08:40 when the gate opens at 08:50.
    arrival_times = sorted(
        arrival_time(open_time, close_time, minutes_before_open)
        for _ in range(total_cars))
    for car_id, target_arrival in enumerate(arrival_times, start=1):
        yield env.timeout(target_arrival - env.now)
        env.process(car(
            env, f"Car{car_id}", open_time, close_time,
            drop_lower, drop_upper, departure_mean, wait_until_close,
            parked_cars))


def parked_cars_monitor(env, parked_cars, parked_log, interval=0.2):
    # Record the number of cars parked at regular time intervals so we can plot
    # the occupancy over time.
    while True:
        parked_log.append((env.now, parked_cars["count"]))
        yield env.timeout(interval)


def run_sim(open_time, close_time, minutes_before_open, drop_lower,
            drop_upper, departure_mean, sim_duration, total_cars,
            wait_until_close):
    # Build a single simulation run and return the occupancy history. This is the
    # basic model used for one random sample.
    env = simpy.Environment()
    parked_cars = {"count": 0}
    parked_log = []
    env.process(arrival_process(
        env, open_time, close_time, minutes_before_open,
        drop_lower, drop_upper, departure_mean, total_cars,
        wait_until_close, parked_cars))
    env.process(parked_cars_monitor(env, parked_cars, parked_log))
    env.run(until=sim_duration)
    return parked_log


def run_monte_carlo(iterations, open_time, close_time, minutes_before_open,
                    drop_lower, drop_upper, departure_mean, total_cars,
                    sim_duration, wait_until_close):
    # Repeat the random simulation many times, retain all runs, and choose the
    # one whose peak parking count is closest to the median peak. This keeps a
    # stable central line while also allowing the full Monte Carlo spread to be
    # summarised for percentile bands.
    runs = []
    for _ in range(iterations):
        parked_log = run_sim(
            open_time, close_time, minutes_before_open, drop_lower,
            drop_upper, departure_mean, sim_duration, total_cars,
            wait_until_close)
        maximum_parked = max(parked for time_value, parked in parked_log)
        runs.append((parked_log, maximum_parked))
    if not runs:
        return None, []
    median_maximum = np.median(
        [maximum for parked_log, maximum in runs])
    median_run = min(runs, key=lambda run: abs(run[1] - median_maximum))
    return median_run, runs


def monte_carlo_percentiles(runs):
    # Build the 20th and 80th percentile bounds across all Monte Carlo runs for a
    # given scenario. These are shown as shaded bands around the median line.
    if not runs:
        return [], [], []
    times = sorted({time_value for parked_log, _ in runs for time_value, _ in parked_log})
    lower = []
    upper = []
    for time_value in times:
        values = [
            parked for parked_log, _ in runs
            for log_time, parked in parked_log
            if abs(log_time - time_value) < 1e-9
        ]
        if values:
            lower.append(np.percentile(values, 20))
            upper.append(np.percentile(values, 80))
    return times, lower, upper


# -----------------------------
# Streamlit visualizer
# -----------------------------
# These functions turn the raw simulation data into a simple animated scene and
# charts for the user interface. Think of it as drawing a time-based story of the
# school drop-off process.

@st.cache_resource
def visualizer_fonts():
    # Load the fonts once and cache them so the animation does not re-load them
    # every frame.
    return ImageFont.load_default(), ImageFont.load_default()


def create_cars(total_cars, gate_open, gate_close, arrival_window,
                drop_lower, drop_upper, departure_mean, seed):
    # Generate the data for each car in the visual simulation: when it arrives,
    # how long it stays parked, how long it takes to clear the space, and where
    # to draw it on the screen.
    rng = random.Random(seed)
    arrival_start = max(0, gate_open - arrival_window)
    arrivals = sorted(
        rng.uniform(arrival_start, gate_close)
        for _ in range(total_cars))
    cars = []
    for index, arrival in enumerate(arrivals):
        cars.append({
            "arrival": arrival,
            "duration": rng.uniform(drop_lower, drop_upper),
            "departure_time": max(1.0, float(np.random.poisson(departure_mean))),
            "walk_time": PERSON_WALK_MINUTES,
            "x": ROAD_RECT[0] + 35 + (index % 12) * 58,
            "y": ROAD_RECT[1] + 45 + (index // 12) * 42,
        })
    return cars


def car_times(car_data, gate_open, gate_close, wait_until_close):
    # A car starts parking immediately when it arrives. If departure is limited,
    # the car remains parked until the gate closes before leaving. The vehicle
    # then spends a configurable departure interval before the person walks to
    # the gate.
    arrival = car_data["arrival"]
    parked_end = arrival + car_data["duration"]
    if wait_until_close:
        parked_end = max(parked_end, gate_close)
    departure_end = parked_end + car_data["departure_time"]
    person_through = departure_end + car_data["walk_time"]
    return arrival, parked_end, departure_end, person_through


def render_frame(cars, elapsed, gate_open, gate_close, wait_until_close,
                 start_time, fonts):
    # Draw a single frame of the scene at a specific moment in time.
    surface = Image.new("RGB", WINDOW_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(surface)
    draw.rounded_rectangle(ROAD_RECT, radius=8, fill=ROAD, outline=ROAD_EDGE, width=3)
    gate_x = ROAD_RECT[2] - 28
    draw.line((gate_x, ROAD_RECT[1], gate_x, ROAD_RECT[3]), fill=GATE, width=8)
    draw.text((gate_x - 28, ROAD_RECT[1] - 26), "GATE", font=fonts[1], fill=GATE)

    parked_count = 0
    people_through = 0
    for car_data in cars:
        arrival, parked_end, departure_end, person_through = car_times(
            car_data, gate_open, gate_close, wait_until_close)
        if elapsed < arrival:
            continue
        if elapsed >= person_through:
            people_through += 1
            continue
        if elapsed < parked_end:
            colour = PARKED
            parked_count += 1
        else:
            colour = LEAVING
        car_rect = (
            int(car_data["x"] - 21), int(car_data["y"] - 11),
            int(car_data["x"] + 21), int(car_data["y"] + 11))
        draw.rounded_rectangle(car_rect, radius=5, fill=colour, outline=TEXT, width=2)
        if departure_end <= elapsed < person_through:
            progress = (elapsed - departure_end) / car_data["walk_time"]
            person_x = car_data["x"] + (gate_x - car_data["x"]) * progress
            draw.ellipse(
                (int(person_x - 6), int(car_data["y"] - 6),
                 int(person_x + 6), int(car_data["y"] + 6)), fill=PERSON)

    draw.text((40, 25), "School Drop-Off Parking", font=fonts[0], fill=TEXT)
    draw.text(
        (40, 55),
        f"Time: {format_clock_time(start_time, elapsed)}   Parked: {parked_count}   "
        f"People through gate: {people_through}",
        font=fonts[1], fill=TEXT)
    return surface, parked_count, people_through


def make_visualizer_chart(history, simulation_start):
    figure, axis = plt.subplots(figsize=(7, 4))
    times = [item[0] for item in history]
    parked = [item[1] for item in history]
    through = [item[2] for item in history]
    axis.plot(times, parked, color="#f4b142", label="Cars parked")
    axis.plot(times, through, color="#74d793", label="People through gate")
    axis.xaxis.set_major_formatter(
        FuncFormatter(
            lambda value, position: format_clock_time(simulation_start, value)))
    axis.set_xlabel("Time of day")
    axis.set_ylabel("People / cars")
    axis.set_title("Parking and gate throughput")
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure.tight_layout()
    return figure


def render_visualizer_tab():
    # This tab shows a cartoon-style view of what the simulation is doing.
    # It uses the same scenario data that was built in the comparison tab.
    st.header("Parking Visualizer")
    st.write("Watch cars park, people leave their cars, and pass through the gate.")
    scenarios = st.session_state.get("comparison_scenarios", {})
    if not scenarios:
        st.info("Configure scenarios in the comparison tab first.")
        return

    required_keys = [
        "comparison_total_cars",
        "comparison_arrival_window",
        "comparison_simulation_start",
        "comparison_simulation_end",
        "comparison_departure_mean",
    ]
    missing = [key for key in required_keys if key not in st.session_state]
    if missing:
        st.info("Configure the comparison settings first, then return to the visualiser.")
        return

    selected_name = st.selectbox("Scenario to visualise", list(scenarios))
    scenario = scenarios[selected_name]
    total_cars = st.session_state["comparison_total_cars"]
    arrival_window = st.session_state["comparison_arrival_window"]
    simulation_start = st.session_state["comparison_simulation_start"]
    simulation_end = st.session_state["comparison_simulation_end"]
    departure_mean = st.session_state["comparison_departure_mean"]
    drop_lower = scenario["lower"]
    drop_upper = scenario["upper"]
    gate_open = time_to_minutes(scenario["open"]) - time_to_minutes(simulation_start)
    gate_close = time_to_minutes(scenario["close"]) - time_to_minutes(simulation_start)
    wait_until_close = scenario["wait_until_close"]
    seed = st.number_input("Random seed", min_value=0, value=42, step=1)

    st.caption(
        f"{selected_name}: parking {drop_lower:g}-{drop_upper:g} minutes, "
        f"car departure mean {departure_mean:g} minutes, "
        f"gate {scenario['open'].strftime('%H:%M')}-{scenario['close'].strftime('%H:%M')}, "
        f"{'departure held until closing' if wait_until_close else 'departure at opening'}.")

    if st.button("Run visualization", type="primary"):
        cars = create_cars(
            total_cars, gate_open, gate_close, arrival_window,
            drop_lower, drop_upper, departure_mean, seed)
        fonts = visualizer_fonts()
        frame_slot, chart_slot = st.columns(2)
        frame_output = frame_slot.empty()
        chart_output = chart_slot.empty()
        history = []
        max_time = max(
            gate_close,
            max(car_times(car_data, gate_open, gate_close, wait_until_close)[2]
                for car_data in cars))
        elapsed = 0.0
        while elapsed <= max_time:
            frame, parked_count, people_through = render_frame(
                cars, elapsed, gate_open, gate_close, wait_until_close,
                simulation_start, fonts)
            history.append((elapsed, parked_count, people_through))
            frame_output.image(frame, use_container_width=True)
            figure = make_visualizer_chart(history, simulation_start)
            chart_output.pyplot(figure, clear_figure=True)
            plt.close(figure)
            elapsed += 0.5
        st.success("Visualization complete. Press Run visualization to replay it.")


# -----------------------------
# Two-scenario comparison
# -----------------------------

def render_comparison_tab():
    # This tab lets the user compare two different school drop-off setups.
    # Each setup changes the parking duration, gate opening/closing times, and
    # whether cars wait until the gate closes before leaving.
    st.header("Two-Scenario Comparison")
    st.write("Compare parked-car occupancy for two scenarios using Monte Carlo median runs.")
    iterations = st.number_input("Monte Carlo iterations", min_value=1, value=100, step=1,
                                 key="comparison_iterations")
    st.subheader("Shared Settings")
    shared = st.columns(5)
    total_cars = shared[0].number_input("Total number of cars", min_value=1, value=55, step=1,
                                        key="comparison_total_cars")s
    arrival_window = shared[1].number_input("Arrival window before gate opening (minutes)",
                                            min_value=0, value=10, step=1,
                                            key="comparison_arrival_window")
    departure_mean = shared[2].number_input("Car departure mean (minutes)",
                                            min_value=1, max_value=10, value=3, step=1,
                                            key="comparison_departure_mean")
    simulation_start = shared[3].slider("Simulation start time", min_value=time(8, 0),
                                        max_value=time(9, 30), value=time(8, 30),
                                        step=timedelta(minutes=15), format="HH:mm",
                                        key="comparison_simulation_start")
    simulation_end = shared[4].slider("Simulation end time", min_value=time(8, 0),
                                      max_value=time(9, 30), value=time(9, 15),
                                      step=timedelta(minutes=15), format="HH:mm",
                                      key="comparison_simulation_end")

    st.subheader("Scenario Settings")
    scenario_1_col, scenario_2_col = st.columns(2)
    values = []
    for index, column in enumerate((scenario_1_col, scenario_2_col), start=1):
        with column:
            default_name = "drop and wait" if index == 1 else "drop and run"
            default_lower = 3 if index == 1 else 3
            default_upper = 7 if index == 1 else 7
            default_open = time(8, 40) if index == 1 else time(8, 40)
            default_close = time(8, 50) if index == 1 else time(8, 50)
            default_wait = index == 1
            name = st.text_input(f"Scenario {index} name", value=default_name,
                                 key=f"comparison_name_{index}")
            lower = st.slider("Parking duration LOWER bound (minutes)", 1, 5, default_lower,
                              step=1, key=f"comparison_lower_{index}")
            upper = st.slider("Parking duration UPPER bound (minutes)", 1, 10, default_upper,
                              step=1, key=f"comparison_upper_{index}")
            gate_open = st.slider("Gate opens at", min_value=time(8, 0), max_value=time(9, 0),
                                  value=default_open, step=timedelta(minutes=5),
                                  format="HH:mm", key=f"comparison_open_{index}")
            gate_close = st.slider("Gate closes at", min_value=time(8, 0), max_value=time(9, 0),
                                   value=default_close, step=timedelta(minutes=5),
                                   format="HH:mm", key=f"comparison_close_{index}")
            wait_until_close = st.checkbox("Limit car departure until gate closing", value=default_wait,
                                           key=f"comparison_wait_{index}")
            values.append((name, lower, upper, gate_open, gate_close, wait_until_close))

    st.session_state["comparison_scenarios"] = {
        name: {
            "lower": lower,
            "upper": upper,
            "open": gate_open,
            "close": gate_close,
            "wait_until_close": wait_until_close,
        }
        for name, lower, upper, gate_open, gate_close, wait_until_close in values
    }

    chart_mode = st.radio("Chart layout", ("Two lines on one chart", "Side-by-side charts"),
                          horizontal=True, key="comparison_chart_mode")

    if st.button("Run comparison", type="primary"):
        start_minutes = time_to_minutes(simulation_start)
        sim_duration = time_to_minutes(simulation_end) - start_minutes
        scenarios = []
        errors = []
        if sim_duration <= 0:
            errors.append("Simulation end time must be after the start time.")
        for name, lower, upper, gate_open, gate_close, wait_until_close in values:
            open_minutes = time_to_minutes(gate_open) - start_minutes
            close_minutes = time_to_minutes(gate_close) - start_minutes
            if not 0 <= open_minutes <= close_minutes <= sim_duration:
                errors.append(f"{name} gate times must fit inside the simulation window.")
            if arrival_window > open_minutes:
                errors.append(f"{name} arrival window begins before the simulation start.")
            scenarios.append((name, lower, upper, open_minutes, close_minutes, wait_until_close))

        if errors:
            for error in errors:
                st.error(error)
            return

        results = []
        for name, lower, upper, open_minutes, close_minutes, wait_until_close in scenarios:
            median_run, all_runs = run_monte_carlo(
                iterations, open_minutes, close_minutes, arrival_window,
                lower, upper, departure_mean, total_cars,
                sim_duration, wait_until_close)
            if median_run is None:
                continue
            median_log, maximum = median_run
            times = [time_value for time_value, parked in median_log]
            parked = [count for time_value, count in median_log]
            p_times, p20, p80 = monte_carlo_percentiles(all_runs)
            results.append((name, times, parked, maximum, p_times, p20, p80))

        st.subheader(f"Median Run + 20/80 Percentile Bounds for {iterations} Monte Carlo Iterations")
        metric_1, metric_2 = st.columns(2)
        metric_1.metric(f"{results[0][0]} peak parked", f"{results[0][3]} cars")
        metric_2.metric(f"{results[1][0]} peak parked", f"{results[1][3]} cars")
        if chart_mode == "Two lines on one chart":
            figure, axis = plt.subplots(figsize=(10, 5))
            for index, (name, times, parked, maximum, p_times, p20, p80) in enumerate(results):
                colour = f"C{index}"
                axis.fill_between(p_times, p20, p80, color=colour, alpha=0.15)
                axis.plot(times, parked, label=f"{name} median", color=colour, linewidth=2)
            axis.legend()
            axes = (axis,)
        else:
            figure, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
            for axis, (name, times, parked, maximum, p_times, p20, p80) in zip(axes, results):
                colour = axis._get_lines[0].get_color() if axis.has_data() else None
                axis.fill_between(p_times, p20, p80, color=colour or "C0", alpha=0.15)
                axis.plot(times, parked, label=f"{name} median", color=colour or "C0", linewidth=2)
                axis.set_title(name)
                axis.legend()
        for axis in axes:
            axis.xaxis.set_major_formatter(
                FuncFormatter(lambda value, position: format_clock_time(simulation_start, value)))
            axis.set_xlabel("Time of day")
            axis.set_ylabel("Parked cars")
            axis.grid(True)
        st.pyplot(figure)
        plt.close(figure)


st.set_page_config(page_title="School Drop-Off Models", layout="wide")
st.title("School Drop-Off Models")
st.info(
    "**Model summary:** Cars arrive at random times from the gate opening time "
    "minus the arrival window through gate closing. Each car stays for a randomly "
    "sampled parking duration, then its departure delay is sampled from a Poisson "
    "distribution using the shared departure mean. The comparison tab repeats "
    "this process with Monte Carlo simulations and shows a representative central "
    "occupancy run with 20th- and 80th-percentile bounds."
)
comparison_tab, visualizer_tab = st.tabs(["Two-scenario comparison", "Visualisation"])
with comparison_tab:
    render_comparison_tab()
with visualizer_tab:
    render_visualizer_tab()
