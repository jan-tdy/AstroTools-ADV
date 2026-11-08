## What it does

Lists the physical constants of an astropy constants set and evaluates expressions that use them.

## How to use

1. Choose the **Constants set**: `astropy default` or a specific edition (`astropyconst13`, `astropyconst20`, `astropyconst40`, `astropyconst80`, `codata2010`...). Pick an edition when you must reproduce a published value.
2. **System**: `si` or `cgs`. Electromagnetic constants stay SI.
3. **Filter** matches part of a name, abbreviation or reference (`boltz`). Press **List constants**.
4. In **Calculator** write expressions with `const.<abbrev>` and `u.<unit>`, then press **Evaluate**. **Store result in workspace** saves the last value under **Store as** (default `constant`).

## Reading the results

The **Constants** tab has columns `name`, `abbrev`, `value`, `unit`, `uncertainty`, `rel. uncertainty`, `reference`, `system`. Filter `boltz` returns `k_B` 1.380649e-23 J / K and `sigma_sb` 5.670374419e-08 W / (m2 K4), both CODATA 2022 with zero uncertainty (exact). The default calculator line `const.G * (1 * u.Msun) / (1 * u.AU)**2` gives `6.6743e-11 m3 solMass / (kg AU2 s2)` with physical type acceleration; the units are not simplified, convert with `.to(u.m/u.s**2)` to get 0.005930 m/s².

## Tips and limits

- Different sets give different values for G, so state the set in publications.
- Constants with an uncertainty of 0 are defined exactly.
