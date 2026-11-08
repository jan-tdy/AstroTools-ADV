## What it does

Finds change points in a series with Bayesian blocks (`bayesian_blocks`).

## How to use

1. **t (times / values)** is the data. **Fitness**: `events` (event times), `regular_events` (needs **dt**), `measures` (needs **x (counts/measurements)** and **sigma**).
2. **p0 (false alarm)** (0.05) sets how conservative the blocking is; **gamma** or **ncp_prior** override it.
3. Press **Compute blocks**. **Edges** lists the block boundaries; **Blocks** the counts.

## Reading the results

The scenario's event list gives 3 blocks with edges `0.29122976, 50.04986119, 59.79259918, 98.93841099`: a rate change at about 50 and another at about 60.

## Tips and limits

- Smaller p0 gives fewer blocks.
