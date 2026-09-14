import io
import random

import matplotlib.pyplot as plt
import numpy as np
import pygame
import simpy
import streamlit as st
from datetime import time, timedelta
from matplotlib.ticker import FuncFormatter
from PIL import Image


# -----------------------------
# Shared simulation logic
# -----------------------------

WINDOW_SIZE = (800, 520)
ROAD_RECT = pygame.Rect(40, 80, 720, 370)
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
    return value.hour * 60 + value.minute


def format_clock_time(start_time, elapsed_minutes):
    absolute_minutes = time_to_minutes(start_time) + elapsed_minutes
    hour = int(absolute_minutes // 60) % 24
    minute = int(absolute_minutes % 60)
    return f"{hour:02d}:{minute:02d}"


def arrival_time(open_time, close_time, minutes_before_open):
    return random.uniform(open_time - minutes_before_open, close_time)


def dropoff_time(lower, upper):
    return random.uniform(lower, upper)


def car(env, name, gate_open, gate_close, drop_lower, drop_upper,
        wait_until_close, parked_cars):
    departure_time = gate_close if wait_until_close else gate_open
    if env.now < departure_time:
        yield env.timeout(departure_time - env.now)
    parked_cars["count"] += 1
    yield env.timeout(dropoff_time(drop_lower, drop_upper))
    parked_cars["count"] -= 1


def arrival_process(env, open_time, close_time, minutes_before_open,
                    drop_lower, drop_upper, total_cars, wait_until_close,
                    parked_cars):
    arrival_times = sorted(
        arrival_time(open_time, close_time, minutes_before_open)
        for _ in range(total_cars))
    for car_id, target_arrival in enumerate(arrival_times, start=1):
        yield env.timeout(target_arrival - env.now)
        env.process(car(
            env, f"Car{car_id}", open_time, close_time,
            drop_lower, drop_upper, wait_until_close, parked_cars))


def parked_cars_monitor(env, parked_cars, parked_log, interval=0.2):
    while True:
        parked_log.append((env.now, parked_cars["count"]))
        yield env.timeout(interval)


def run_sim(open_time, close_time, minutes_before_open, drop_lower,
            drop_upper, sim_duration, total_cars, wait_until_close):
    env = simpy.Environment()
    parked_cars = {"count": 0}
    parked_log = []
    env.process(arrival_process(
        env, open_time, close_time, minutes_before_open,
        drop_lower, drop_upper, total_cars, wait_until_close, parked_cars))
    env.process(parked_cars_monitor(env, parked_cars, parked_log))
    env.run(until=sim_duration)
    return parked_log


def run_monte_carlo(iterations, open_time, close_time, minutes_before_open,
                    drop_lower, drop_upper, total_cars, sim_duration,
                    wait_until_close):
    runs = []
    for _ in range(iterations):
        parked_log = run_sim(
            open_time, close_time, minutes_before_open, drop_lower,
            drop_upper, sim_duration, total_cars, wait_until_close)
        maximum_parked = max(parked for time_value, parked in parked_log)
        runs.append((parked_log, maximum_parked))
    median_maximum = np.median(
        [maximum for parked_log, maximum in runs])
    return min(runs, key=lambda run: abs(run[1] - median_maximum))


# -----------------------------
# Pygame visualizer
# -----------------------------

@st.cache_resource
def pygame_fonts():
    pygame.init()
    return pygame.font.Font(None, 28), pygame.font.Font(None, 22)


def create_cars(total_cars, gate_open, gate_close, arrival_window,
                drop_lower, drop_upper, seed):
    rng = random.Random(seed)
    arrivals = sorted(
        rng.uniform(max(0, gate_open - arrival_window), gate_close)
        for _ in range(total_cars))
    cars = []
    for index, arrival in enumerate(arrivals):
        cars.append({
            "arrival": arrival,
            "duration": rng.uniform(drop_lower, drop_upper),
            "x": ROAD_RECT.left + 35 + (index % 12) * 58,
            "y": ROAD_RECT.top + 45 + (index // 12) * 42,
        })
    return cars


def car_times(car_data, gate_open, gate_close, wait_until_close):
    departure = gate_close if wait_until_close else gate_open
    departure = max(departure, car_data["arrival"])
    parked_end = departure + car_data["duration"]
    person_through = parked_end + PERSON_WALK_MINUTES
    return departure, parked_end, person_through


def render_frame(cars, elapsed, gate_open, gate_close, wait_until_close,
                 start_time, fonts):
    surface = pygame.Surface(WINDOW_SIZE)
    surface.fill(BACKGROUND)
    pygame.draw.rect(surface, ROAD, ROAD_RECT, border_radius=8)
    pygame.draw.rect(surface, ROAD_EDGE, ROAD_RECT, width=3, border_radius=8)
    gate_x = ROAD_RECT.right - 28
    pygame.draw.line(surface, GATE, (gate_x, ROAD_RECT.top),
                     (gate_x, ROAD_RECT.bottom), width=8)
    surface.blit(fonts[1].render("GATE", True, GATE),
                 (gate_x - 28, ROAD_RECT.top - 26))

    parked_count = 0
    people_through = 0
    for car_data in cars:
        departure, parked_end, person_through = car_times(
            car_data, gate_open, gate_close, wait_until_close)
        if elapsed < car_data["arrival"]:
            continue
        if elapsed >= person_through:
            people_through += 1
            continue
        if elapsed < departure:
            colour = ARRIVING
        elif elapsed < parked_end:
            colour = PARKED
            parked_count += 1
        else:
            colour = LEAVING
        car_rect = pygame.Rect(
            int(car_data["x"] - 21), int(car_data["y"] - 11), 42, 22)
        pygame.draw.rect(surface, colour, car_rect, border_radius=5)
        pygame.draw.rect(surface, TEXT, car_rect, width=2, border_radius=5)
        if parked_end <= elapsed < person_through:
            progress = (elapsed - parked_end) / PERSON_WALK_MINUTES
            person_x = car_data["x"] + (gate_x - car_data["x"]) * progress
            pygame.draw.circle(
                surface, PERSON, (int(person_x), int(car_data["y"])), 6)

    surface.blit(fonts[0].render("School Drop-Off Parking", True, TEXT), (40, 25))
    status = fonts[1].render(
        f"Time: {format_clock_time(start_time, elapsed)}   Parked: {parked_count}   "
        f"People through gate: {people_through}", True, TEXT)
    surface.blit(status, (40, 55))
    raw = pygame.image.tostring(surface, "RGB")
    return Image.frombytes("RGB", WINDOW_SIZE, raw), parked_count, people_through


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
    st.header("Parking Visualizer")
    st.write("Watch cars park, people leave their cars, and pass through the gate.")
    scenarios = st.session_state.get("comparison_scenarios", {})
    if not scenarios:
        st.info("Configure scenarios in the comparison tab first.")
        return

    selected_name = st.selectbox("Scenario to visualise", list(scenarios))
    scenario = scenarios[selected_name]
    total_cars = st.session_state["comparison_total_cars"]
    arrival_window = st.session_state["comparison_arrival_window"]
    simulation_start = st.session_state["comparison_simulation_start"]
    simulation_end = st.session_state["comparison_simulation_end"]
    drop_lower = scenario["lower"]
    drop_upper = scenario["upper"]
    gate_open = time_to_minutes(scenario["open"]) - time_to_minutes(simulation_start)
    gate_close = time_to_minutes(scenario["close"]) - time_to_minutes(simulation_start)
    wait_until_close = scenario["wait_until_close"]
    seed = st.number_input("Random seed", min_value=0, value=7, step=1)

    st.caption(
        f"{selected_name}: parking {drop_lower:g}-{drop_upper:g} minutes, "
        f"gate {scenario['open'].strftime('%H:%M')}-{scenario['close'].strftime('%H:%M')}, "
        f"{'departure held until closing' if wait_until_close else 'departure at opening'}.")

    if st.button("Run visualization", type="primary"):
        cars = create_cars(
            total_cars, gate_open, gate_close, arrival_window,
            drop_lower, drop_upper, seed)
        fonts = pygame_fonts()
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
    st.header("Two-Scenario Comparison")
    st.write("Compare parked-car occupancy for two scenarios using Monte Carlo median runs.")
    iterations = st.number_input("Monte Carlo iterations", min_value=1, value=20, step=1,
                                 key="comparison_iterations")
    st.subheader("Shared Settings")
    shared = st.columns(4)
    total_cars = shared[0].number_input("Total number of cars", min_value=1, value=70, step=1,
                                        key="comparison_total_cars")
    arrival_window = shared[1].number_input("Arrival window before gate opening (minutes)",
                                            min_value=0, value=10, step=5,
                                            key="comparison_arrival_window")
    simulation_start = shared[2].slider("Simulation start time", min_value=time(8, 0),
                                        max_value=time(9, 30), value=time(8, 30),
                                        step=timedelta(minutes=15), format="HH:mm",
                                        key="comparison_simulation_start")
    simulation_end = shared[3].slider("Simulation end time", min_value=time(8, 0),
                                      max_value=time(9, 30), value=time(9, 0),
                                      step=timedelta(minutes=15), format="HH:mm",
                                      key="comparison_simulation_end")

    st.subheader("Scenario Settings")
    scenario_1_col, scenario_2_col = st.columns(2)
    values = []
    for index, column in enumerate((scenario_1_col, scenario_2_col), start=1):
        with column:
            default_name = "old" if index == 1 else "new"
            default_lower = 1.0 if index == 1 else 5.0
            default_upper = 3.0 if index == 1 else 10.0
            default_open = time(8, 50) if index == 1 else time(8, 40)
            default_close = time(9, 0) if index == 1 else time(8, 50)
            default_wait = index == 2
            name = st.text_input(f"Scenario {index} name", value=default_name,
                                 key=f"comparison_name_{index}")
            lower = st.slider("Parking duration LOWER bound (minutes)", 0.5, 5.0, default_lower,
                              key=f"comparison_lower_{index}")
            upper = st.slider("Parking duration UPPER bound (minutes)", 1.0, 10.0, default_upper,
                              key=f"comparison_upper_{index}")
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
            log, maximum = run_monte_carlo(
                iterations, open_minutes, close_minutes, arrival_window,
                lower, upper, total_cars, sim_duration, wait_until_close)
            times = [time_value for time_value, parked in log]
            parked = [count for time_value, count in log]
            results.append((name, times, parked, maximum))

        st.subheader(f"Median Run of {iterations} Monte Carlo Iterations")
        metric_1, metric_2 = st.columns(2)
        metric_1.metric(f"{results[0][0]} peak parked", f"{results[0][3]} cars")
        metric_2.metric(f"{results[1][0]} peak parked", f"{results[1][3]} cars")
        if chart_mode == "Two lines on one chart":
            figure, axis = plt.subplots(figsize=(10, 5))
            for name, times, parked, maximum in results:
                axis.plot(times, parked, label=name)
            axis.legend()
            axes = (axis,)
        else:
            figure, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
            for axis, (name, times, parked, maximum) in zip(axes, results):
                axis.plot(times, parked, label=name)
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
comparison_tab, visualizer_tab = st.tabs(["Two-scenario comparison", "Pygame visualisation"])
with comparison_tab:
    render_comparison_tab()
with visualizer_tab:
    render_visualizer_tab()
