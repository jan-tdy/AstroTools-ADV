## What it does

Computes Lomb-Scargle periodograms (also multiband) for unevenly sampled data, with false-alarm levels.

## How to use

1. Choose the **Series**, **Signal column**, **Error column** and optional **Band column** (**Multiband** uses `LombScargleMultiband`; no false-alarm probability then).
2. **Normalization** (`standard`, `model`, `log`, `psd`), **Method** (`auto`, `slow`, `chi2`, `cython`, `fast`, `fastchi2`), **n terms** (>1 needs `chi2` or `fastchi2`), **Fit mean**, **Center data**.
3. Frequency grid: **Samples per peak** (5), **Nyquist factor** (5), **Min frequency**, **Max frequency** (1/day), or **Manual frequencies** (`linspace(0.01, 1, 5000)`).
4. **FAP method** (`baluev`, `davies`, `naive`, `bootstrap` with **Bootstraps**) and **FAP levels** (`0.1, 0.05, 0.01`).
5. **Plot x axis** `frequency` or `period`, **Log x axis**. Press **Compute periodogram**; stored as **Result name** (default `periodogram`).

## Reading the results

For the synthetic sinusoid (period 3.7 d, irregular sampling, 1000 points): `best frequency 0.27118675 1/d`, `best period 3.6874958 d`, `peak power 0.95388507`, `false-alarm probability (baluev): 0`; the 1% level is at power 0.0272. Other tabs: **Periodogram**, **Folded + model**, **Null distribution**, **Table**.

## Tips and limits

- The best period of 3.687 d versus the true 3.7 d is the frequency resolution of a 100 d series (1/100 per day), not an error.
- Evenly spaced data above the Nyquist frequency give aliases; with regular 0.1 d sampling a 3.7 d signal reappeared at 10.27 1/d.
- Peaks below the FAP line are not significant.
