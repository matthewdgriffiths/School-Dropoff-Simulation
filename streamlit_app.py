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


def arrival_time(open_time, sim_duration):
	return random.triangular(0, sim_duration, open_time)


def dropoff_time(lower, upper):
	return random.uniform(lower, upper)


def car(env, name, gate_open, gate_close, dropoff_lane, drop_lower,
			drop_upper, wait_until_close):
	wait_until = gate_close if wait_until_close else gate_open
	if env.now < wait_until:
		yield env.timeout(wait_until - env.now)

	with dropoff_lane.request() as req:
		yield req
		duration = dropoff_time(drop_lower, drop_upper)
		yield env.timeout(duration)


def arrival_process(env, rate_per_min, open_time, close_time,
					dropoff_lane,
					drop_lower, drop_upper, sim_duration, total_cars,
					wait_until_close):
	car_id = 0
	while car_id < total_cars:
		interarrival = np.random.exponential(1 / rate_per_min)
		yield env.timeout(interarrival)

		car_id += 1
		target_arrival = arrival_time(open_time, sim_duration)
		yield env.timeout(max(0, target_arrival - env.now))

		env.process(car(env,
						f"Car{car_id}",
						open_time,
						close_time,
						dropoff_lane,
						drop_lower,
						drop_upper,
						wait_until_close))


def queue_monitor(env, dropoff_lane, queue_log, interval=0.2):
	while True:
		queue_log.append((env.now, len(dropoff_lane.queue)))
		yield env.timeout(interval)


def run_sim(rate_per_min,
			open_time,
			close_time,
			drop_lower,
			drop_upper,
			sim_duration,
		total_cars,
		wait_until_close):

	env = simpy.Environment()
	dropoff_lane = simpy.Resource(env, capacity=1)
	queue_log = []

	env.process(arrival_process(env,
								rate_per_min,
								open_time,
								close_time,
								dropoff_lane,
								drop_lower,
								drop_upper,
								sim_duration,
								total_cars,
								wait_until_close))

	env.process(queue_monitor(env, dropoff_lane, queue_log))

	env.run(until=sim_duration)

	return queue_log


def run_monte_carlo(iterations, rate_per_min, open_time, close_time,
					drop_lower, drop_upper,
					sim_duration, total_cars, wait_until_close):
	runs = []
	for _ in range(iterations):
		queue_log = run_sim(rate_per_min, open_time, close_time,
						drop_lower, drop_upper,
						sim_duration, total_cars, wait_until_close)
		maximum_queue = max(queue for time, queue in queue_log)
		runs.append((queue_log, maximum_queue))

	median_maximum = np.median([maximum_queue for queue_log, maximum_queue in runs])
	return min(runs, key=lambda run: abs(run[1] - median_maximum))

# -----------------------------
# Streamlit UI
# -----------------------------

st.title("School Drop-Off Simulation (SimPy)")
st.write("Play with arrival rates, drop-off durations, and gate timings to see queue behaviour.")

st.header("Simulation Controls")

iterations = st.number_input(
	"Monte Carlo iterations",
	min_value=1,
	value=20,
	step=1,
	help="Number of independent simulation runs for each scenario.")

st.subheader("Shared Settings")
shared_col_1, shared_col_2, shared_col_3 = st.columns(3)
with shared_col_1:
	total_cars = st.number_input("Total number of cars", min_value=1, value=70, step=1)
with shared_col_2:
	rate = st.slider("Cars per minute", 1, 20, 6)
with shared_col_3:
	simulation_start = st.slider(
		"Simulation start time",
		min_value=time(8, 0),
		max_value=time(9, 30),
		value=time(8, 30),
		step=timedelta(minutes=15),
		format="HH:mm")
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
	scenario_1_name = st.text_input("Scenario 1 name", value="Scenario 1")
	scenario_1_drop_lower = st.slider("Drop-off duration LOWER bound (minutes)", 0.5, 5.0, 1.0, key="scenario_1_drop_lower")
	scenario_1_drop_upper = st.slider("Drop-off duration UPPER bound (minutes)", 1.0, 10.0, 3.0, key="scenario_1_drop_upper")
	scenario_1_open_time = st.slider(
		"Gate opens at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 15),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_1_open_time")
	scenario_1_close_time = st.slider(
		"Gate closes at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 30),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_1_close_time")
	scenario_1_wait_until_close = st.checkbox(
		"Parents wait at the gate until closing time",
		value=False,
		key="scenario_1_wait_until_close")

with scenario_2_col:
	st.markdown("**Scenario 2**")
	scenario_2_name = st.text_input("Scenario 2 name", value="Scenario 2")
	scenario_2_drop_lower = st.slider("Drop-off duration LOWER bound (minutes)", 0.5, 5.0, 1.0, key="scenario_2_drop_lower")
	scenario_2_drop_upper = st.slider("Drop-off duration UPPER bound (minutes)", 1.0, 10.0, 3.0, key="scenario_2_drop_upper")
	scenario_2_open_time = st.slider(
		"Gate opens at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 15),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_2_open_time")
	scenario_2_close_time = st.slider(
		"Gate closes at",
		min_value=time(8, 0),
		max_value=time(9, 0),
		value=time(8, 30),
		step=timedelta(minutes=5),
		format="HH:mm",
		key="scenario_2_close_time")
	scenario_2_wait_until_close = st.checkbox(
		"Parents wait at the gate until closing time",
		value=False,
		key="scenario_2_wait_until_close")

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

	validation_errors = []
	if sim_duration <= 0:
		validation_errors.append("Simulation end time must be after the start time.")
	for name, open_minutes, close_minutes in (
		(scenario_1_name, scenario_1_open_minutes, scenario_1_close_minutes),
		(scenario_2_name, scenario_2_open_minutes, scenario_2_close_minutes)):
		if not 0 <= open_minutes < close_minutes <= sim_duration:
			validation_errors.append(
				f"{name} gate times must fall within the simulation window and open before closing.")

	if validation_errors:
		for error in validation_errors:
			st.error(error)
	else:
		log_1, max_queue_1 = run_monte_carlo(
			iterations, rate, scenario_1_open_minutes,
			scenario_1_close_minutes, scenario_1_drop_lower,
			scenario_1_drop_upper, sim_duration, total_cars,
			scenario_1_wait_until_close)
		log_2, max_queue_2 = run_monte_carlo(
			iterations, rate, scenario_2_open_minutes,
			scenario_2_close_minutes, scenario_2_drop_lower,
			scenario_2_drop_upper, sim_duration, total_cars,
			scenario_2_wait_until_close)

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
