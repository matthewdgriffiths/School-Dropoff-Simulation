import streamlit as st
import simpy
import numpy as np
import random
import matplotlib.pyplot as plt


# -----------------------------
# Simulation Components
# -----------------------------

def biased_arrival_time(open_time, close_time, before_pct, after_pct, sim_duration):
	r = random.random()
	if r < before_pct:
		return random.uniform(0, open_time)
	elif r > 1 - after_pct:
		return random.uniform(close_time, sim_duration)
	else:
		return random.uniform(open_time, close_time)


def dropoff_time(lower, upper):
	return random.uniform(lower, upper)


def car(env, name, gate_open, gate_close, dropoff_lane, drop_lower, drop_upper):
	if env.now < gate_open:
		yield env.timeout(gate_open - env.now)

	with dropoff_lane.request() as req:
		yield req
		duration = dropoff_time(drop_lower, drop_upper)
		yield env.timeout(duration)


def arrival_process(env, rate_per_min, open_time, close_time,
					before_pct, after_pct, dropoff_lane,
					drop_lower, drop_upper, sim_duration):
	car_id = 0
	while True:
		interarrival = np.random.exponential(1 / rate_per_min)
		yield env.timeout(interarrival)

		car_id += 1
		arrival_time = biased_arrival_time(open_time, close_time,
										   before_pct, after_pct,
										   sim_duration)
		yield env.timeout(max(0, arrival_time - env.now))

		env.process(car(env,
						f"Car{car_id}",
						open_time,
						close_time,
						dropoff_lane,
						drop_lower,
						drop_upper))


def queue_monitor(env, dropoff_lane, queue_log, interval=0.2):
	while True:
		queue_log.append((env.now, len(dropoff_lane.queue)))
		yield env.timeout(interval)


def run_sim(rate_per_min,
			open_time,
			close_time,
			before_pct,
			after_pct,
			drop_lower,
			drop_upper,
			sim_duration):

	env = simpy.Environment()
	dropoff_lane = simpy.Resource(env, capacity=1)
	queue_log = []

	env.process(arrival_process(env,
								rate_per_min,
								open_time,
								close_time,
								before_pct,
								after_pct,
								dropoff_lane,
								drop_lower,
								drop_upper,
								sim_duration))

	env.process(queue_monitor(env, dropoff_lane, queue_log))

	env.run(until=sim_duration)

	return queue_log


# -----------------------------
# Streamlit UI
# -----------------------------

st.title("School Drop-Off Simulation (SimPy)")
st.write("Play with arrival rates, drop-off durations, and gate timings to see queue behaviour.")

st.header("Simulation Controls")

rate = st.slider("Cars per minute (Poisson rate)", 1, 20, 4)
drop_lower = st.slider("Drop-off duration LOWER bound (minutes)", 0.5, 5.0, 1.0)
drop_upper = st.slider("Drop-off duration UPPER bound (minutes)", 1.0, 10.0, 3.0)

open_time = st.slider("Gate opens at (minutes after simulation start)", 0, 60, 40)
close_time = st.slider("Gate closes at", 0, 60, 50)

before_pct = st.slider("Percentage arriving BEFORE gate opens", 0.0, 0.5, 0.30)
after_pct = st.slider("Percentage arriving AFTER gate closes", 0.0, 0.2, 0.05)

sim_duration = st.slider("Simulation duration (minutes)", 30, 120, 70)

if st.button("Run Simulation"):
	log = run_sim(rate, open_time, close_time,
				  before_pct, after_pct,
				  drop_lower, drop_upper,
				  sim_duration)

	times = [t for t, q in log]
	queues = [q for t, q in log]

	max_queue = max(queues)
	st.subheader(f"Maximum Queue Length: {max_queue} cars")

	fig, ax = plt.subplots(figsize=(10, 5))
	ax.plot(times, queues, label="Queue length")
	ax.set_xlabel("Time (minutes)")
	ax.set_ylabel("Queue length (cars)")
	ax.set_title("Queue Length Over Time")
	ax.grid(True)
	st.pyplot(fig)
