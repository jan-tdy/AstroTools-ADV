## What it does

Generates test light curves: `flux = 1 + signal + noise`, with `flux_err` equal to the noise sigma.

## How to use

1. Choose the **Signal**: `sinusoid`, `transit`, `sinusoid+transit` or `noise`.
2. Set **Points** (1000), **Duration [d]** (100), **Start time** and **Irregular sampling** (random sorted times, on by default).
3. Signal parameters: **Period [d]** (3.7), **Sine amplitude** (1.0), **Sine phase [cycles]**, **Transit depth** (0.01), **Transit duration [d]** (0.2), **Transit epoch [d]** (1.0).
4. **Noise sigma** (0.1) and **Random seed** (0) make the result reproducible.
5. Press **Generate**; stored under **Result name** (default `synthetic`).

## Reading the results

The **Info** tab for the defaults: `TimeSeries: 1000 rows`, columns `time, flux, flux_err`, `time: 2020-01-01T00:27:21.614 .. 2020-04-09T22:48:11.684`, `span: 99.931135 d`. **Light curve** plots it.

## Tips and limits

- Use irregular sampling for period searches: regular spacing causes aliasing above the Nyquist frequency (see [Lomb-Scargle](ts_lombscargle.md)).
- Use the same seed to get the same data again.
