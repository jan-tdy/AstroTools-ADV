## What it does

Searches for periodic box-shaped dips (transits) with Box Least Squares and can mask the found transits.

## How to use

1. Choose the **Series**, **Signal column** and **Error column**.
2. **Durations**: trial durations in days (default `0.05, 0.1, 0.2`).
3. Period grid: **Min period**, **Max period** (days) or **Manual periods**; **Min transits** (3), **Frequency factor** (larger = coarser), **Oversample** (10).
4. **Objective** `likelihood` or `snr`, **Method** `fast` or `slow`.
5. **Run BLS**; stored as **Result name** (default `bls`). **Mask transits -> new series** removes the in-transit points and stores **Masked series name**.

## Reading the results

For a synthetic transit light curve (period 3.7 d, depth 0.01, noise 0.002, 1000 irregular points, durations `0.1, 0.2, 0.3`): `best period 3.6995366 d`, `duration 0.2 d`, `depth 0.0101866 +/- 0.000266 (SNR 38.3)`, `odd/even depth 0.0105606 / 0.00990061`, `transits observed 24`. **Stats** lists each transit; **Folded + model** plots the fit.

## Tips and limits

- Include the real duration among the trial **Durations**; otherwise the depth is underestimated.
- A large odd/even depth difference suggests an eclipsing binary at twice the period.
- Use **Mask transits** to find the next planet in the residuals.
