import io
import random

import matplotlib.pyplot as plt
import numpy as np
import pygame
import streamlit as st
from PIL import Image


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


def car_times(car, gate_open, gate_close, wait_until_close):
    departure = gate_close if wait_until_close else gate_open
    departure = max(departure, car["arrival"])
    parked_end = departure + car["duration"]
    person_through = parked_end + PERSON_WALK_MINUTES
    return departure, parked_end, person_through


def render_frame(cars, elapsed, gate_open, gate_close, wait_until_close, fonts):
    surface = pygame.Surface(WINDOW_SIZE)
    surface.fill(BACKGROUND)
    pygame.draw.rect(surface, ROAD, ROAD_RECT, border_radius=8)
    pygame.draw.rect(surface, ROAD_EDGE, ROAD_RECT, width=3, border_radius=8)

    gate_x = ROAD_RECT.right - 28
    pygame.draw.line(surface, GATE, (gate_x, ROAD_RECT.top),
                     (gate_x, ROAD_RECT.bottom), width=8)
    gate_label = fonts[1].render("GATE", True, GATE)
    surface.blit(gate_label, (gate_x - 28, ROAD_RECT.top - 26))

    parked_count = 0
    people_through = 0
    for car in cars:
        departure, parked_end, person_through = car_times(
            car, gate_open, gate_close, wait_until_close)
        if elapsed < car["arrival"]:
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

        car_rect = pygame.Rect(int(car["x"] - 21), int(car["y"] - 11), 42, 22)
        pygame.draw.rect(surface, colour, car_rect, border_radius=5)
        pygame.draw.rect(surface, TEXT, car_rect, width=2, border_radius=5)

        if parked_end <= elapsed < person_through:
            progress = (elapsed - parked_end) / PERSON_WALK_MINUTES
            person_x = car["x"] + (gate_x - car["x"]) * progress
            pygame.draw.circle(surface, PERSON, (int(person_x), int(car["y"])), 6)

    title = fonts[0].render("School Drop-Off Parking", True, TEXT)
    surface.blit(title, (40, 25))
    status = fonts[1].render(
        f"Time: {elapsed:05.1f} min   Parked: {parked_count}   "
        f"People through gate: {people_through}", True, TEXT)
    surface.blit(status, (40, 55))

    raw = pygame.image.tostring(surface, "RGB")
    return Image.frombytes("RGB", WINDOW_SIZE, raw), parked_count, people_through


def make_chart(history):
    figure, axis = plt.subplots(figsize=(7, 4))
    times = [item[0] for item in history]
    parked = [item[1] for item in history]
    through = [item[2] for item in history]
    axis.plot(times, parked, color="#f4b142", label="Cars parked")
    axis.plot(times, through, color="#74d793", label="People through gate")
    axis.set_xlabel("Simulation time (minutes)")
    axis.set_ylabel("People / cars")
    axis.set_title("Parking and gate throughput")
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure.tight_layout()
    return figure


st.set_page_config(page_title="School Drop-Off Visualizer", layout="wide")
st.title("School Drop-Off Visualizer")
st.write("Watch cars park, people leave their cars, and pass through the gate.")

with st.expander("Scenario configuration", expanded=True):
    controls = st.columns(4)
    total_cars = controls[0].number_input("Total cars", min_value=1, value=70, step=1)
    arrival_window = controls[1].number_input(
        "Arrival window before gate (minutes)", min_value=0, value=10, step=5)
    gate_open = controls[2].number_input("Gate opens (minutes)", min_value=0, value=15, step=5)
    gate_close = controls[3].number_input("Gate closes (minutes)", min_value=1, value=20, step=5)
    duration_col, hold_col, seed_col = st.columns(3)
    drop_lower = duration_col.number_input("Parking duration lower", min_value=0.1, value=1.0, step=0.5)
    drop_upper = duration_col.number_input("Parking duration upper", min_value=0.1, value=3.0, step=0.5)
    wait_until_close = hold_col.checkbox("Hold departures until gate closes")
    seed = seed_col.number_input("Random seed", min_value=0, value=7, step=1)

if gate_open >= gate_close:
    st.error("Gate opening must be before gate closing.")
    st.stop()
if drop_lower > drop_upper:
    st.error("Parking duration lower bound must not exceed the upper bound.")
    st.stop()

start = st.button("Run visualization", type="primary")
if start:
    cars = create_cars(
        total_cars, gate_open, gate_close, arrival_window,
        drop_lower, drop_upper, seed)
    fonts = pygame_fonts()
    frame_slot, chart_slot = st.columns(2)
    frame_output = frame_slot.empty()
    chart_output = chart_slot.empty()
    history = []
    max_time = max(gate_close, max(car_times(car, gate_open, gate_close, wait_until_close)[2] for car in cars))
    step = 0.5
    elapsed = 0.0

    while elapsed <= max_time:
        frame, parked_count, people_through = render_frame(
            cars, elapsed, gate_open, gate_close, wait_until_close, fonts)
        history.append((elapsed, parked_count, people_through))
        frame_output.image(frame, use_container_width=True)
        figure = make_chart(history)
        chart_output.pyplot(figure, clear_figure=True)
        plt.close(figure)
        elapsed += step

    st.success("Visualization complete. Press Run visualization to replay it.")
