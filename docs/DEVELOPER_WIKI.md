# Developer Wiki: School Drop-Off Simulation

## Overview

This project models a school drop-off queue where cars arrive before the gate opens, wait in the drop-off area, park for a random amount of time, and then leave. The app compares two scenarios and can also animate the process visually.

The model is built around a discrete-event simulation using SimPy. In plain terms, the program does not simulate every single second in a continuous loop. Instead, it schedules important moments in time such as:

- when a car arrives
- when the gate opens or closes
- when a car parks
- when a car leaves the parking area
- when passengers pass through the gate

This makes the simulation fast, readable, and easier to compare across many random runs.

---

## Purpose of the model

The simulation answers questions such as:

- How many cars are likely to be parked at once?
- Does a later gate opening reduce congestion?
- Does limiting departures until gate closing create a bigger queue?
- How does parking duration influence occupancy?

The app uses a Monte Carlo style approach to compare scenarios by repeatedly running random simulations and choosing the run closest to the median peak occupancy.

---

## High-level architecture

The code is split into a few logical sections:

1. Shared simulation logic
   - time conversion helpers
   - random arrival and parking-time generation
   - SimPy process definitions
   - Monte Carlo runner

2. Streamlit visualizer
   - car generation for the animation
   - drawing frames for the car park scene
   - plotting occupancy and gate throughput charts

3. Two-scenario comparison page
   - user inputs for two alternative scenarios
   - validation of gate windows and simulation timings
   - chart generation comparing parked-car counts

---

## Core simulation concepts

### 1. Time handling

The project uses minute-based values internally.

- `time_to_minutes(value)` converts a Python `datetime.time` into minutes since midnight.
- `format_clock_time(start_time, elapsed_minutes)` converts simulation time back into a readable clock display.

This makes calculations easier because all timing checks are simple numeric comparisons.

### 2. Random arrivals

`arrival_time(open_time, close_time, minutes_before_open)` generates a random arrival time between:

- `gate_open - minutes_before_open`, and
- `gate_close`

This means cars can begin arriving before the gate opens and continue arriving right through to the closing time. The distribution over this full interval is treated as a Poisson-style arrival process, with the user-specified total number of cars spread across that time window.

### 3. Random parking duration

`dropoff_time(lower, upper)` chooses a random time between the lower and upper duration bounds. This represents the time each car spends parked while passengers get out and move through the gate.

### 4. Car process

The `car(...)` function defines the lifecycle of one car. It does the following:

- waits until the gate opens or closes depending on the scenario
- increments the parking count when the car starts occupying a space
- waits for a random drop-off duration
- decrements the parking count once the car leaves

The `wait_until_close` flag is important. If it is true, cars cannot leave until the gate closes; otherwise they may leave when the gate opens.

### 5. Arrival process

The `arrival_process(...)` function creates all car events in a sorted schedule. This makes the arrival pattern look natural instead of having all cars appear at once.

---

## SimPy model behaviour

The simulation uses an event-driven environment:

- `simpy.Environment()` creates the simulation clock.
- `env.process(...)` schedules background processes.
- `yield env.timeout(...)` pauses a process until a time event occurs.

The model tracks a global parking count as cars enter and leave the parking area. A monitor records the count regularly so the app can plot occupancy across time.

### Important functions

- `run_sim(...)`
  - creates a single simulation run
  - schedules arrivals and tracking
  - runs the environment until the chosen duration ends
  - returns the parked-car history

- `run_monte_carlo(...)`
  - repeats the simulation many times with random inputs
  - stores the peak parked-car count for each run
  - computes the median peak value
  - returns the run closest to that median to use as a stable comparison result

---

## Visualization layer

The visualizer is not the simulation engine itself. It is a presentation layer that draws the same scenario in a more understandable way.

### `create_cars(...)`

This function converts simulation inputs into a list of car objects with:

- arrival time
- parking duration
- Poisson-sampled departure delay
- x and y coordinates for drawing

The cars are placed in two horizontal rows so the queue remains visible within the
visualizer canvas.

### `car_times(...)`

This function calculates the key moments for a car:

- parking-end time
- playground-entry time
- school-entry start time
- person-through-gate time
- car-leave time

The timing rules are:

- before gate opening, the person remains beside the car
- at gate opening, the person enters the playground
- people enter school at gate closing in both modes
- when departure is not limited, the car leaves after both parking has finished and the gate has opened, followed by its sampled departure interval
- when departure is limited, the car waits until the later of parking completion or gate closing, then applies its sampled departure interval

This allows the visualizer to show cars and people according to their state:

- parked
- waiting beside a car
- waiting in the playground
- walking through the gate
- in school

### `render_frame(...)`

This draws a single frame of the animation. It creates an image with cars at the
bottom, a small gate in the middle, a playground above the gate, and a school at
the top. Cars are drawn with windows, wheels, lights, and body colour. People are
drawn with a head, body, arms, and legs. It also updates the text in the top-left
corner to show:

- current time
- current parked count
- number of people through the gate

### `make_visualizer_chart(...)`

This creates the time-series plot showing:

- cars parked over time
- people in the playground over time
- people in school over time

---

## Streamlit app structure

The interface uses tabs:

- Comparison tab
- Visualisation tab

### Comparison tab

This page lets the user compare two scenarios using the same shared settings:

- total number of cars
- arrival window before gate opening
- simulation start and end times
- gate times for each scenario
- parking duration bounds
- whether cars must wait until gate closing before leaving

The app validates input to ensure:

- the simulation window is valid
- gate times fit within the selected window
- the arrival window does not begin before the simulation start

It then runs Monte Carlo simulations and plots the resulting parked-car counts.

### Visualisation tab

This page is designed to help a user understand the dynamics visually. It uses a scenario saved from the comparison tab and animates the process by looping through times in small increments.

The visualiser also has a control for the random seed. People enter school
immediately at their release time, so there is no separate gate-through delay.

---

## Data flow

The general flow is:

1. User sets shared simulation settings.
2. User defines two scenarios.
3. Application validates the settings.
4. `run_monte_carlo(...)` produces a representative median run for each scenario.
5. The comparison tab plots parked-car counts over time.
6. The visualiser tab animates the same scenario on a simple map.

---

## Design notes and assumptions

The model is intentionally simple and transparent. It focuses on queue dynamics rather than full traffic engineering. Some assumptions include:

- cars arrive across the full period from `gate_open - arrival_window` through to `gate_close`
- the arrival spread is treated as a Poisson-style distribution over that interval, with the specified total car count distributed through it
- parking durations vary uniformly between lower and upper bounds
- each car occupies one parking space for the duration of its drop-off
- persons walk through the gate after parking ends
- cars remain parked until the gate opens or gate closes depending on the `wait_until_close` setting
- gate timing is the major constraining factor in the queue

This makes the model suitable for comparing scenarios quickly and clearly, even if it is not a full real-world traffic simulation.

---

## Key files

- `streamlit_combined_app.py` — main application
- `requirements.txt` — project dependencies

---

## Extension ideas

Possible improvements for future versions include:

- adding a real road network and queue layout
- modelling car departure batching more realistically
- showing the precise waiting times before the gate
- adding export of results to CSV
- building a separate backend API for simulation runs
