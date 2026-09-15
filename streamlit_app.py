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
PLAYGROUND = (69, 92, 78)
TEXT = (235, 240, 245)
ARRIVING = (76, 190, 232)
PARKED = (244, 177, 68)
LEAVING = (116, 215, 133)
PERSON = (250, 245, 230)
GATE = (220, 95, 95)


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
    departure_mean, wait_until_close, parked_cars, turnaround_times):
    # A car is introduced at its actual arrival time. It then occupies a parking
    # space immediately. If the departure is limited until gate closing, the car
    # stays parked until the gate closes even if its parking duration would have
    # ended earlier. The final departure phase also takes a configurable amount of
    # time before the car is removed from the occupied count.
    parked_cars["count"] += 1
    parking_duration = dropoff_time(drop_lower, drop_upper)
    departure_duration = departure_time(departure_mean)
    # Nobody can leave before the gate opens. When departure is limited, cars
    # must remain until the gate closes instead.
    arrival = env.now
    departure_start = max(env.now + parking_duration, gate_open)
    if wait_until_close:
        departure_start = max(departure_start, gate_close)
    turnaround_times.append(departure_start + departure_duration - arrival)
    yield env.timeout(max(0, departure_start - env.now))
    yield env.timeout(departure_duration)
    parked_cars["count"] -= 1


def arrival_process(env, open_time, close_time, minutes_before_open,
                    drop_lower, drop_upper, departure_mean, total_cars,
                    wait_until_close, parked_cars, turnaround_times):
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
            parked_cars, turnaround_times))


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
    turnaround_times = []
    env.process(arrival_process(
        env, open_time, close_time, minutes_before_open,
        drop_lower, drop_upper, departure_mean, total_cars,
        wait_until_close, parked_cars, turnaround_times))
    env.process(parked_cars_monitor(env, parked_cars, parked_log))
    env.run(until=sim_duration)
    mean_turnaround = float(np.mean(turnaround_times)) if turnaround_times else 0.0
    return parked_log, mean_turnaround


def run_monte_carlo(iterations, open_time, close_time, minutes_before_open,
                    drop_lower, drop_upper, departure_mean, total_cars,
                    sim_duration, wait_until_close):
    # Repeat the random simulation many times, retain all runs, and choose the
    # one whose peak parking count is closest to the median peak. This keeps a
    # stable central line while also allowing the full Monte Carlo spread to be
    # summarised for percentile bands.
    runs = []
    for _ in range(iterations):
        parked_log, mean_turnaround = run_sim(
            open_time, close_time, minutes_before_open, drop_lower,
            drop_upper, departure_mean, sim_duration, total_cars,
            wait_until_close)
        maximum_parked = max(parked for time_value, parked in parked_log)
        runs.append((parked_log, maximum_parked, mean_turnaround))
    if not runs:
        return None, []
    median_maximum = np.median(
        [maximum for parked_log, maximum, mean_turnaround in runs])
    median_run = min(runs, key=lambda run: abs(run[1] - median_maximum))
    return median_run, runs


def monte_carlo_percentiles(runs):
    # Build the 20th and 80th percentile bounds across all Monte Carlo runs for a
    # given scenario. These are shown as shaded bands around the median line.
    if not runs:
        return [], [], []
    times = sorted({time_value for parked_log, _, _ in runs for time_value, _ in parked_log})
    lower = []
    upper = []
    for time_value in times:
        values = [
            parked for parked_log, _, _ in runs
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
    cars_per_row = (total_cars + 1) // 2
    queue_width = ROAD_RECT[2] - ROAD_RECT[0] - 70
    queue_spacing = queue_width / max(1, cars_per_row - 1)
    queue_y = (ROAD_RECT[1] + ROAD_RECT[3]) // 2
    for index, arrival in enumerate(arrivals):
        row = index // cars_per_row
        column = index % cars_per_row
        cars.append({
            "arrival": arrival,
            "duration": rng.uniform(drop_lower, drop_upper),
            "departure_time": max(1.0, float(np.random.poisson(departure_mean))),
            "x": ROAD_RECT[0] + 35 + column * queue_spacing,
            "y": queue_y - 32 + row * 64,
            "playground_x": ROAD_RECT[0] + 35 + column * queue_spacing,
            "playground_y": ROAD_RECT[1] + 58 + row * 20,
            "half_width": max(8, min(21, queue_spacing * 0.42)),
        })
    return cars


def car_times(car_data, gate_open, gate_close, wait_until_close):
    # A car starts parking immediately when it arrives. People enter the
    # playground after opening and wait there until closing. In normal mode the
    # car can leave after parking and its departure interval, but never before
    # opening; limited mode holds the car until closing before applying that
    # interval.
    arrival = car_data["arrival"]
    parked_end = arrival + car_data["duration"]
    playground_enter = max(parked_end, gate_open)
    walk_start = max(playground_enter, gate_close)
    person_through = walk_start
    car_departure_start = max(parked_end, gate_open)
    if wait_until_close:
        car_departure_start = max(car_departure_start, gate_close)
    car_leave = car_departure_start + car_data["departure_time"]
    return arrival, parked_end, playground_enter, walk_start, person_through, car_leave


def render_frame(cars, elapsed, gate_open, gate_close, wait_until_close,
                 start_time, fonts):
    # Draw a single frame of the scene at a specific moment in time.
    surface = Image.new("RGB", WINDOW_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(surface)
    draw.rounded_rectangle(ROAD_RECT, radius=8, fill=ROAD, outline=ROAD_EDGE, width=3)
    gate_x = (ROAD_RECT[0] + ROAD_RECT[2]) // 2
    gate_y = ROAD_RECT[1] + 110
    school_rect = (gate_x - 82, ROAD_RECT[1] + 4, gate_x + 82, ROAD_RECT[1] + 42)
    draw.rounded_rectangle(school_rect, radius=6, fill=(82, 105, 132), outline=TEXT, width=2)
    draw.polygon(
        [(gate_x - 92, ROAD_RECT[1] + 5),
         (gate_x, ROAD_RECT[1] - 14),
         (gate_x + 92, ROAD_RECT[1] + 5)],
        fill=(154, 76, 76), outline=TEXT)
    draw.text((gate_x - 30, ROAD_RECT[1] + 17), "SCHOOL", font=fonts[1], fill=TEXT)
    draw.rounded_rectangle(
        (ROAD_RECT[0] + 18, ROAD_RECT[1] + 48,
         ROAD_RECT[2] - 18, ROAD_RECT[1] + 90),
        radius=6, fill=PLAYGROUND, outline=ROAD_EDGE, width=2)
    draw.text(
        (ROAD_RECT[0] + 28, ROAD_RECT[1] + 52),
        "PLAYGROUND", font=fonts[1], fill=TEXT)
    draw.line((gate_x - 34, gate_y, gate_x + 34, gate_y), fill=GATE, width=4)
    draw.text((gate_x - 20, gate_y - 18), "GATE", font=fonts[1], fill=GATE)

    parked_count = 0
    playground_count = 0
    school_count = 0
    people_through = 0
    for car_data in cars:
        arrival, parked_end, playground_enter, walk_start, person_through, car_leave = car_times(
            car_data, gate_open, gate_close, wait_until_close)
        if elapsed < arrival:
            continue
        if elapsed >= person_through:
            people_through += 1
            school_count += 1
        if playground_enter <= elapsed < walk_start:
            playground_count += 1
        if elapsed < car_leave:
            parked_count += 1
            colour = PARKED
            car_rect = (
                int(car_data["x"] - car_data["half_width"]), int(car_data["y"] - 11),
                int(car_data["x"] + car_data["half_width"]), int(car_data["y"] + 11))
            car_left, car_top, car_right, car_bottom = car_rect
            draw.rounded_rectangle(car_rect, radius=5, fill=colour, outline=TEXT, width=2)
            car_width = car_right - car_left
            if car_width >= 22:
                window_top = car_top + 3
                window_bottom = car_top + 9
                window_left = car_left + max(5, int(car_width * 0.24))
                window_right = car_right - max(5, int(car_width * 0.24))
                draw.polygon(
                    [(window_left, window_bottom),
                     (window_left + max(4, car_width // 8), window_top),
                     (window_right - max(4, car_width // 8), window_top),
                     (window_right, window_bottom)],
                    fill=(68, 91, 112), outline=TEXT)
                wheel_radius = 4
                for wheel_x in (car_left + 8, car_right - 8):
                    draw.ellipse(
                        (wheel_x - wheel_radius, car_bottom - 3,
                         wheel_x + wheel_radius, car_bottom + 5),
                        fill=(20, 23, 28), outline=TEXT)
                draw.ellipse(
                    (car_right - 4, car_top + 5, car_right, car_top + 9),
                    fill=(255, 235, 150))
                draw.ellipse(
                    (car_left, car_top + 5, car_left + 4, car_top + 9),
                    fill=(220, 75, 75))
        if parked_end <= elapsed < playground_enter:
            person_x = car_data["x"]
            person_y = car_data["y"] - 15
        elif playground_enter <= elapsed < walk_start:
            person_x = car_data["playground_x"]
            person_y = car_data["playground_y"]
        else:
            person_x = None
            person_y = None
        if person_x is not None:
            person_x = int(person_x)
            person_y = int(person_y)
            draw.ellipse(
                (person_x - 4, person_y - 13, person_x + 4, person_y - 5),
                fill=PERSON, outline=TEXT)
            draw.line(
                (person_x, person_y - 5, person_x, person_y + 6),
                fill=PERSON, width=3)
            draw.line(
                (person_x, person_y - 1, person_x - 6, person_y + 3),
                fill=PERSON, width=2)
            draw.line(
                (person_x, person_y - 1, person_x + 6, person_y + 3),
                fill=PERSON, width=2)
            draw.line(
                (person_x, person_y + 6, person_x - 4, person_y + 12),
                fill=PERSON, width=2)
            draw.line(
                (person_x, person_y + 6, person_x + 4, person_y + 12),
                fill=PERSON, width=2)

    draw.text((40, 25), "School Drop-Off Parking", font=fonts[0], fill=TEXT)
    draw.text(
        (40, 55),
        f"Time: {format_clock_time(start_time, elapsed)}   Parked: {parked_count}   "
        f"People through gate: {people_through}",
        font=fonts[1], fill=TEXT)
    return surface, parked_count, playground_count, school_count


def make_visualizer_chart(history, simulation_start):
    figure, axis = plt.subplots(figsize=(7, 4))
    times = [item[0] for item in history]
    parked = [item[1] for item in history]
    playground = [item[2] for item in history]
    school = [item[3] for item in history]
    axis.plot(times, parked, color="#f4b142", label="Cars parked")
    axis.plot(times, playground, color="#8fd694", label="People in playground")
    axis.plot(times, school, color="#8db9f2", label="People in school")
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


def render_guide_tab():
    st.header("How to use this model")
    st.write(
        "This app runs a randomised simulation of a school drop-off system. "
        "Use the controls to change the model parameters, run the simulation, "
        "and compare how many cars are parked over time.")

    st.subheader("What the app does")
    st.write(
        "Cars arrive at random times between the start of the arrival window "
        "and gate closing. Each car receives a random parking duration between "
        "the configured lower and upper bounds, then a random departure delay. "
        "The model records how many cars are parked at regular time intervals.")
    st.write(
        "The parameters can be adjusted in the simulation configuration in the "
        "Two-Scenario Comparison tab. Shared settings apply to both scenarios; "
        "scenario settings control each alternative separately.")

    st.subheader("Run the model before reading the graph")
    st.write(
        "Changing inputs does not generate a new result automatically. Press "
        "Run comparison in the Two-Scenario Comparison tab to execute the "
        "Monte Carlo simulation and generate the comparison graph. More "
        "iterations usually make the result more stable, but take longer to run.")

    st.subheader("Model logic")
    st.code(
        "Set simulation configuration\n"
        "        |\n"
        "        v\n"
        "Generate random arrival times for every car\n"
        "        |\n"
        "        v\n"
        "Car arrives -> parking count increases\n"
        "        |\n"
        "        v\n"
        "Random parking duration ends\n"
        "        |\n"
        "        +--> departure allowed -> random departure delay -> count decreases\n"
        "        |\n"
        "        +--> departure limited -> wait until gate closes -> delay -> count decreases\n"
        "        |\n"
        "        v\n"
        "Repeat for many runs -> median run and 20th/80th percentile band",
        language="text")

    st.subheader("How to read the comparison chart")
    st.write(
        "The solid line is the representative run: the Monte Carlo run whose "
        "peak parked-car count is closest to the median peak across all runs. "
        "The shaded band is calculated independently at each time point from "
        "the 20th to the 80th percentile of parked-car counts across all runs.")
    st.write(
        "The lower bound therefore shows a relatively low-occupancy outcome at "
        "that time, while the upper bound shows a relatively high-occupancy "
        "outcome. The band is not a guaranteed minimum and maximum, and it is "
        "not a confidence interval. A wider band means that random variation "
        "makes the result less predictable. A higher line or band means more "
        "cars are parked and potentially more congestion.")

    st.subheader("Visualisation")
    st.write(
        "After running the comparison, open the Parking Visualizer tab and "
        "choose a saved scenario. Press Run visualization to animate cars, "
        "people in the playground, and people entering school. The visualizer "
        "uses the selected scenario and a random seed to create one illustrative "
        "run; its chart is separate from the Monte Carlo comparison chart.")


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
        f"{'departure held until closing' if wait_until_close else 'departure after opening'}.")

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
            max(car_times(car_data, gate_open, gate_close, wait_until_close)[5]
                for car_data in cars))
        elapsed = 0.0
        while elapsed <= max_time:
            frame, parked_count, playground_count, school_count = render_frame(
                cars, elapsed, gate_open, gate_close, wait_until_close,
                simulation_start, fonts)
            history.append((elapsed, parked_count, playground_count, school_count))
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
    st.write(" This tab lets the user compare two different school drop-off setups. Each setup changes the parking duration, gate opening/closing times, and whether cars wait until the gate closes before leaving.")
    iterations = st.number_input("Monte Carlo iterations", min_value=1, value=100, step=1,
                                 key="comparison_iterations")
    st.subheader("Shared Settings")
    shared = st.columns(5)
    total_cars = shared[0].number_input("Total number of cars", min_value=1, value=55, step=1,
                                        key="comparison_total_cars")
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
            default_name = "drop and wait" if index == 1 else "drop and leave"
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
            median_log, maximum, mean_turnaround = median_run
            times = [time_value for time_value, parked in median_log]
            parked = [count for time_value, count in median_log]
            p_times, p20, p80 = monte_carlo_percentiles(all_runs)
            results.append((name, times, parked, maximum, mean_turnaround, p_times, p20, p80))

        st.subheader(f"Median Run + 20/80 Percentile Bounds for {iterations} Monte Carlo Iterations")
        metric_columns = st.columns(4)
        metric_columns[0].metric(
            f"{results[0][0]} peak parked", f"{results[0][3]} cars")
        metric_columns[1].metric(
            f"{results[0][0]} mean turnaround", f"{results[0][4]:.1f} minutes")
        metric_columns[2].metric(
            f"{results[1][0]} peak parked", f"{results[1][3]} cars")
        metric_columns[3].metric(
            f"{results[1][0]} mean turnaround", f"{results[1][4]:.1f} minutes")
        if chart_mode == "Two lines on one chart":
            figure, axis = plt.subplots(figsize=(10, 5))
            for index, (name, times, parked, maximum, mean_turnaround, p_times, p20, p80) in enumerate(results):
                colour = f"C{index}"
                axis.fill_between(p_times, p20, p80, color=colour, alpha=0.15)
                axis.plot(times, parked, label=f"{name} median", color=colour, linewidth=2)
            axis.legend()
            axes = (axis,)
        else:
            figure, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
            for axis, (name, times, parked, maximum, mean_turnaround, p_times, p20, p80) in zip(axes, results):
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
st.title("School Drop-Off Scenario Comparison and Visualizer")
st.info(
    "**Model summary:** Cars arrive at random times from a configurable number of minutes (default 10) before the gate opening time. "
    "Each car stays for a randomly-sampled parking duration (upper and lower bounds are specified). " \
    "Each car then has a departure delay applied from a Poisson distribution (default mean is 3 minutes) to simulate speed of departure." \
    "Children can only enter the playground after gate opening and enter school at gate closing. Normally, cars can depart "
    "after their parking and departure delays. However, when **Limit car departure until "
    "gate closing** is enabled, cars wait until the gate closes before their departure is simulated."
)
comparison_tab, visualizer_tab, guide_tab = st.tabs(
    ["Two-scenario comparison", "Visualisation", "Guide"])
with comparison_tab:
    render_comparison_tab()
with visualizer_tab:
    render_visualizer_tab()
with guide_tab:
    render_guide_tab()
