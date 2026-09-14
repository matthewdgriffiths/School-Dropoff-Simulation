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


def car(env, name, gate_open, gate_close, drop_lower, drop_upper,
		wait_until_close, parked_cars):
	departure_time = gate_close if wait_until_close else gate_open
	if env.now < departure_time:
		yield env.timeout(departure_time - env.now)

	parked_cars["count"] += 1
	duration = dropoff_time(drop_lower, drop_upper)
	yield env.timeout(duration)
	parked_cars["count"] -= 1


def arrival_process(env, open_time, close_time, minutes_before_open,
					drop_lower, drop_upper, total_cars,
					wait_until_close, parked_cars):
	arrival_times = sorted(
		arrival_time(open_time, close_time, minutes_before_open)
		for _ in range(total_cars))
	for car_id, target_arrival in enumerate(arrival_times, start=1):
		yield env.timeout(target_arrival - env.now)

		env.process(car(env,
						f"Car{car_id}",
						open_time,
						close_time,
						drop_lower,
						drop_upper,
						wait_until_close,
						parked_cars))


def parked_cars_monitor(env, parked_cars, parked_log, interval=0.2):
	while True:
		parked_log.append((env.now, parked_cars["count"]))
		yield env.timeout(interval)


def run_sim(open_time,
			close_time,
			minutes_before_open,
			drop_lower,
			drop_upper,
			sim_duration,
			total_cars,
		wait_until_close):

	env = simpy.Environment()
	parked_cars = {"count": 0}
	parked_log = []

	env.process(arrival_process(env,
								open_time,
								close_time,
								minutes_before_open,
								drop_lower,
								drop_upper,
								total_cars,
								wait_until_close,
								parked_cars))

	env.process(parked_cars_monitor(env, parked_cars, parked_log))

	env.run(until=sim_duration)

	return parked_log


def run_monte_carlo(iterations, open_time, close_time, minutes_before_open,
					drop_lower, drop_upper, total_cars, sim_duration,
					wait_until_close):
	runs = []
	for _ in range(iterations):
		parked_log = run_sim(open_time, close_time, minutes_before_open,
						drop_lower, drop_upper, sim_duration, total_cars,
						wait_until_close)
		maximum_parked = max(parked for time, parked in parked_log)
		runs.append((parked_log, maximum_parked))

	median_maximum = np.median([maximum_parked for parked_log, maximum_parked in runs])
	return min(runs, key=lambda run: abs(run[1] - median_maximum))

# -----------------------------
# Streamlit UI
# -----------------------------

st.title("School Drop-Off Simulation (SimPy)")
st.write("Configure arrival windows, parking durations, and gate timings to see parked-car occupancy.")

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
	scenario_1_wait_until_close = st.checkbox(
		"Limit car departure until gate closing",
		value=False,
		key="scenario_1_wait_until_close")

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
	scenario_2_wait_until_close = st.checkbox(
		"Limit car departure until gate closing",
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
		log_1, max_parked_1 = run_monte_carlo(
			iterations, scenario_1_open_minutes, scenario_1_close_minutes,
			arrival_window, scenario_1_drop_lower, scenario_1_drop_upper,
			total_cars, sim_duration, scenario_1_wait_until_close)
		log_2, max_parked_2 = run_monte_carlo(
			iterations, scenario_2_open_minutes, scenario_2_close_minutes,
			arrival_window, scenario_2_drop_lower, scenario_2_drop_upper,
			total_cars, sim_duration, scenario_2_wait_until_close)

		results = []
		for name, log, max_parked in (
			(scenario_1_name, log_1, max_parked_1),
			(scenario_2_name, log_2, max_parked_2)):
			times = [time for time, parked in log]
			parked = [count for time, count in log]
			results.append((name, times, parked, max_parked))

		st.subheader(f"Median Run of {iterations} Monte Carlo Iterations")
		metric_col_1, metric_col_2 = st.columns(2)
		metric_col_1.metric(f"{results[0][0]} peak parked", f"{results[0][3]} cars")
		metric_col_2.metric(f"{results[1][0]} peak parked", f"{results[1][3]} cars")

		if chart_mode == "Two lines on one chart":
			fig, ax = plt.subplots(figsize=(10, 5))
			for name, times, parked, max_parked in results:
				ax.plot(times, parked, label=name)
			ax.set_title("Parked Cars Over Time")
			ax.legend()
			axes = (ax,)
		else:
			fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
			for ax, (name, times, parked, max_parked) in zip(axes, results):
				ax.plot(times, parked, label=name)
				ax.set_title(name)
				ax.legend()

		for ax in axes:
			ax.xaxis.set_major_formatter(
				FuncFormatter(
					lambda value, position: format_clock_time(simulation_start, value)))
			ax.set_xlabel("Time of day")
			ax.set_ylabel("Parked cars")
			ax.grid(True)
		st.pyplot(fig)
