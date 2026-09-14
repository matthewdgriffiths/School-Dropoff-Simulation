# User Guide: School Drop-Off Model

## What this app does

This app helps you explore how a school drop-off system behaves under different conditions. It models cars arriving, parking temporarily, and then leaving the site. The app compares two possible scenarios and also shows an animated view of the traffic and parking activity.

You can use it to answer questions such as:

- Will a later gate opening reduce parking pressure?
- How does parking duration affect peak occupancy?
- Does keeping cars until the gate closes create more congestion?

---

## Getting started

### 1. Install the project dependencies

Open a terminal in the project folder and run:

```bash
python3 -m pip install -r requirements.txt
```

### 2. Start the app

Run:

```bash
python3 -m streamlit run streamlit_app.py
```

Then open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

---

## Interface overview

The app has two tabs:

### A. Two-scenario comparison

This is the main analysis tab. It lets you compare two different setups side by side.

#### Shared settings

These are values used by both scenarios:

- Total number of cars
- Arrival window before the gate opens
- Simulation start time
- Simulation end time

#### Scenario settings

For each scenario, you can adjust:

- scenario name
- parking duration lower bound
- parking duration upper bound
- gate open time
- gate close time
- whether cars must wait until closing before leaving

#### Monte Carlo iterations

This value tells the app how many random simulation runs to test. More runs usually give a more stable estimate, but the app will take longer to compute.

### B. Visualisation

This tab shows a simple animation of the parking area. It is helpful for understanding the flow of cars and people through the gate.

---

## How to read the comparison chart

The chart shows parked-car counts over time.

- The x-axis is time-of-day.
- The y-axis is parked cars.
- Each line represents one scenario.

A higher and wider line means that more cars are likely to be waiting/parked at the same time. This often indicates more congestion.

The app also displays peak parked-car values for each scenario.

---

## What the simulation is really measuring

The model is built around a few assumptions:

- cars begin arriving `arrival_window` minutes before the gate opens, and can continue arriving until the gate closes
- the overall arrival pattern is spread throughout that full period using a Poisson-style distribution of car arrivals
- each car stays for a random parking duration sampled between the chosen lower and upper bounds
- cars can leave once their parking time ends, unless the "Limit car departure until gate closing" option is checked
- passengers then walk through the gate after parking ends

This means the results are best used for comparing relative scenarios rather than predicting exact real-world traffic with perfect accuracy.

---

## Tips for using the model well

### Start with sensible values

Try these to get familiar with the app:

- total cars: 50 to 100
- arrival window: 5 to 20 minutes
- parking duration: 1 to 10 minutes
- gate opening: around 8:40 to 8:50
- gate closing: around 9:00

### Compare one variable at a time

A good way to learn is to vary one setting at a time, such as:

- gate opening time
- parking duration range
- wait-until-closing option

This makes it easier to see what causes the biggest change in congestion.

### Use the visualiser to understand the pattern

Once you have a scenario that seems interesting, switch to the visualisation tab to see the cars and people moving through the scene.

---

## Common interpretation examples

### Scenario A: earlier gate opening

If the gate opens earlier, cars may leave the queue sooner, which often reduces peak parking occupancy.

### Scenario B: longer parking duration

If cars stay parked longer, the model will produce a higher peak occupancy and slower gate throughput.

### Scenario C: waiting until gate closing

If departures are prevented until the gate closes, the queue may become much heavier and occupancy may rise sharply around closing time.

---

## Troubleshooting

### The app does not start

Make sure the dependencies are installed:

```bash
python3 -m pip install -r requirements.txt
```

Then run:

```bash
python3 -m streamlit run streamlit_app.py
```

### The charts look strange

Check that:

- the end time is later than the start time
- gate times fit inside the chosen simulation window
- the arrival window is not before the simulation start

### The visualiser does not show data

Go to the comparison tab first and create the scenario data. The visualiser reads the saved scenarios from the app state.

---

## Summary

This project is a simple, clear simulation of a school drop-off process. It is designed to help users compare scenarios and understand how timing and parking duration affect congestion. The model is intentionally transparent and easy to modify, making it useful both as a teaching tool and as a starting point for more advanced transport simulations.

---

## Related project files

- `streamlit_app.py` — main application logic
- `requirements.txt` — Python dependencies
- `docs/DEVELOPER_WIKI.md` — deeper technical documentation
