import streamlit as st
import simpy
import numpy as np
import random
import matplotlib.pyplot as plt
from datetime import time, timedelta
from matplotlib.ticker import FuncFormatter


# -----------------------------
# Simulation Components
# -----------------------------

def time_to_minutes(value):
	return value.hour * 60 + value.minute


def format_clock_time(start_time, elapsed_minutes):
	absolute_minutes = time_to_minutes(start_time) + elapsed_minutes
	hour = int(absolute_minutes // 60) % 24
	minute = int(absolute_minutes % 60)
	return f"{hour:02d}:{minute:02d}"


def arrival_time(open_time, close_time, minutes_before_open):
	return random.uniform(
		open_time - minutes_before_open,
		close_time)


def dropoff_time(lower, upper):
	return random.uniform(lower, upper)


def car(env, name, gate_open, dropoff_lane, drop_lower, drop_upper,
		wait_until_open, held_queue):
	if wait_until_open and env.now < gate_open:
		yield env.timeout(gate_open - env.now)
	if wait_until_open:
		held_queue["count"] -= 1

	with dropoff_lane.request() as req:
		yield req
		duration = dropoff_time(drop_lower, drop_upper)
		yield env.timeout(duration)


def arrival_process(env, open_time, close_time, minutes_before_open,
					dropoff_lane, drop_lower, drop_upper, total_cars,
					wait_until_open, held_queue):
	arrival_times = sorted(
		arrival_time(open_time, close_time, minutes_before_open)
		for _ in range(total_cars))
	for car_id, target_arrival in enumerate(arrival_times, start=1):
		yield env.timeout(target_arrival - env.now)
		if wait_until_open:
			held_queue["count"] += 1

		env.process(car(env,
						f"Car{car_id}",
						open_time,
						dropoff_lane,
						drop_lower,
						drop_upper,
						wait_until_open,
						held_queue))


def queue_monitor(env, dropoff_lane, held_queue, queue_log, interval=0.2):
	while True:
		queue_log.append((env.now, held_queue["count"] + len(dropoff_lane.queue)))
		yield env.timeout(interval)


def run_sim(open_time,
			close_time,
			minutes_before_open,
			drop_lower,
			drop_upper,
			sim_duration,
			total_cars,
			wait_until_open):

	env = simpy.Environment()
	dropoff_lane = simpy.Resource(env, capacity=1)
	held_queue = {"count": 0}
	queue_log = []

	env.process(arrival_process(env,
								open_time,
								close_time,
								minutes_before_open,
								dropoff_lane,
								drop_lower,
								drop_upper,
								total_cars,
								wait_until_open,
								held_queue))

	env.process(queue_monitor(env, dropoff_lane, held_queue, queue_log))

	env.run(until=sim_duration)

	return queue_log


def run_monte_carlo(iterations, open_time, close_time, minutes_before_open,
					drop_lower, drop_upper, total_cars, sim_duration,
					wait_until_open):
	runs = []
	for _ in range(iterations):
		queue_log = run_sim(open_time, close_time, minutes_before_open,
						drop_lower, drop_upper, sim_duration, total_cars,
						wait_until_open)
		maximum_queue = max(queue for time, queue in queue_log)
		runs.append((queue_log, maximum_queue))

	median_maximum = np.median([maximum_queue for queue_log, maximum_queue in runs])
	return min(runs, key=lambda run: abs(run[1] - median_maximum))

# -----------------------------
# Streamlit UI
# -----------------------------

st.title("School Drop-Off Simulation (SimPy)")
st.write("Configure arrival windows, drop-off durations, and gate timings to see queue behaviour.")

st.header("Simulation Controls")

iterations = st.number_input(
	"Monte Carlo iterations",
	min_value=1,
	value=20,
	step=1,
	help="Number of independent simulation runs for each scenario.")

st.subheader("Shared Settings")
shared_col_1, shared_col_2, shared_col_3, shared_col_4 = st.columns(4)
with shared_col_1:
	total_cars = st.number_input("Total number of cars", min_value=1, value=70, step=1)
with shared_col_2:
	arrival_window = st.number_input(
		"Arrival window before gate opening (minutes)",
		min_value=0,
		value=10,
		step=5)
with shared_col_3:
	simulation_start = st.slider(
		"Simulation start time",
		min_value=time(8, 0),
		max_value=time(9, 30),
		value=time(8, 30),
		step=timedelta(minutes=15),
		format="HH:mm")
with shared_col_4:
	simulation_end = st.slider(
		"Simulation end time",
		min_value=time(8, 0),
		max_value=time(9, 30),
		value=time(9, 0),
		step=timedelta(minutes=15),
		format="HH:mm")

st.subheader("Scenario Settings")
scenario_1_col, scenario_2_col = st.columns(2)

with scenario_1_col:
	st.markdown("**Scenario 1**")
	scenario_1_name = st.text_input("Scenario 1 name", value="old")
	scenario_1_drop_lower = st.slider("Drop-off duration LOWER bound (minutes)", 0.5, 5.0, 1.0, key="scenario_1_drop_lower")
	scenario_1_drop_upper = st.slider("Drop-off duration UPPER bound (minutes)", 1.0, 10.0, 3.0, key="scenario_1_drop_upper")
	scenario_1_open_time = st.slider(
		"Gate opens at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 45),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_1_open_time")
	scenario_1_close_time = st.slider(
		"Gate closes at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 50),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_1_close_time")
	scenario_1_wait_until_open = st.checkbox(
		"Limit car departure until gate opening",
		value=False,
		key="scenario_1_wait_until_open")

with scenario_2_col:
	st.markdown("**Scenario 2**")
	scenario_2_name = st.text_input("Scenario 2 name", value="new")
	scenario_2_drop_lower = st.slider("Drop-off duration LOWER bound (minutes)", 0.5, 5.0, 1.0, key="scenario_2_drop_lower")
	scenario_2_drop_upper = st.slider("Drop-off duration UPPER bound (minutes)", 1.0, 10.0, 3.0, key="scenario_2_drop_upper")
	scenario_2_open_time = st.slider(
		"Gate opens at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 45),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_2_open_time")
	scenario_2_close_time = st.slider(
		"Gate closes at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 50),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_2_close_time")
	scenario_2_wait_until_open = st.checkbox(
		"Limit car departure until gate opening",
		value=False,
		key="scenario_2_wait_until_open")

chart_mode = st.radio(
	"Chart layout",
	("Two lines on one chart", "Side-by-side charts"),
	horizontal=True)

if st.button("Run Simulation"):
	start_minutes = time_to_minutes(simulation_start)
	end_minutes = time_to_minutes(simulation_end)
	sim_duration = end_minutes - start_minutes
	scenario_1_open_minutes = time_to_minutes(scenario_1_open_time) - start_minutes
	scenario_1_close_minutes = time_to_minutes(scenario_1_close_time) - start_minutes
	scenario_2_open_minutes = time_to_minutes(scenario_2_open_time) - start_minutes
	scenario_2_close_minutes = time_to_minutes(scenario_2_close_time) - start_minutes
	arrival_window = int(arrival_window)

	validation_errors = []
	if sim_duration <= 0:
		validation_errors.append("Simulation end time must be after the start time.")
	for name, open_minutes, close_minutes in (
		(scenario_1_name, scenario_1_open_minutes, scenario_1_close_minutes),
		(scenario_2_name, scenario_2_open_minutes, scenario_2_close_minutes)):
		if not 0 <= open_minutes < close_minutes <= sim_duration:
			validation_errors.append(
				f"{name} gate times must fall within the simulation window and open before closing.")
	if arrival_window > min(scenario_1_open_minutes, scenario_2_open_minutes):
		validation_errors.append(
			"The shared arrival window cannot begin before the simulation start time.")

	if validation_errors:
		for error in validation_errors:
			st.error(error)
	else:
		log_1, max_queue_1 = run_monte_carlo(
			iterations, scenario_1_open_minutes, scenario_1_close_minutes,
			arrival_window, scenario_1_drop_lower, scenario_1_drop_upper,
			total_cars, sim_duration, scenario_1_wait_until_open)
		log_2, max_queue_2 = run_monte_carlo(
			iterations, scenario_2_open_minutes, scenario_2_close_minutes,
			arrival_window, scenario_2_drop_lower, scenario_2_drop_upper,
			total_cars, sim_duration, scenario_2_wait_until_open)

		results = []
		for name, log, max_queue in (
			(scenario_1_name, log_1, max_queue_1),
			(scenario_2_name, log_2, max_queue_2)):
			times = [time for time, queue in log]
			queues = [queue for time, queue in log]
			results.append((name, times, queues, max_queue))

		st.subheader(f"Median Run of {iterations} Monte Carlo Iterations")
		metric_col_1, metric_col_2 = st.columns(2)
		metric_col_1.metric(results[0][0], f"{results[0][3]} cars")
		metric_col_2.metric(results[1][0], f"{results[1][3]} cars")

		if chart_mode == "Two lines on one chart":
			fig, ax = plt.subplots(figsize=(10, 5))
			for name, times, queues, max_queue in results:
				ax.plot(times, queues, label=name)
			ax.set_title("Queue Length Over Time")
			ax.legend()
			axes = (ax,)
		else:
			fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
			for ax, (name, times, queues, max_queue) in zip(axes, results):
				ax.plot(times, queues, label=name)
				ax.set_title(name)
				ax.legend()

		for ax in axes:
			ax.xaxis.set_major_formatter(
				FuncFormatter(
					lambda value, position: format_clock_time(simulation_start, value)))
			ax.set_xlabel("Time of day")
			ax.set_ylabel("Queue length (cars)")
			ax.grid(True)
		st.pyplot(fig)
