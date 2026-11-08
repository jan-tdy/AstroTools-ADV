---
title: Units, quantities and constants
order: 11
lede: Convert a radio line to a velocity, evaluate quantity expressions with magnitudes, and use physical constants of a chosen edition.
---

## A Doppler velocity from a frequency

An H I line has a rest frequency of 1420.405751 MHz and you observe it at 1400 MHz. Open [Unit converter](../reference/basics/unit_converter.md).

1. **Value**: `1400 MHz`. **Convert to**: `km/s`.
2. **Equivalency**: `doppler_radio`. **Parameter 1**: `1420.405751 MHz` (the rest frequency).
3. Press **Convert**.

![Unit converter with the radio Doppler equivalency](../assets/guides/basics-unit-converter.png "Radio Doppler velocity of an H I line observed at 1400 MHz.")

The result is `4306.861 km / s` (`4306861.08 m / s` in SI), physical type `speed/velocity`. Without the equivalency the converter refuses to turn a frequency into a velocity.

## Several quantities in one script

[Quantity calculator](../reference/basics/quantity_calculator.md) evaluates one expression per line; `name = expr` keeps a variable.

```text
d = 10 * u.pc
d.to(u.lyr)
m = Magnitude(5 * u.mag(u.AB))
m.to(u.Jy)
v_esc = sqrt(2 * const.G * 1 * u.Msun / (1 * u.AU))
v_esc.to(u.km / u.s)
```

![Quantity calculator results](../assets/guides/basics-quantity-calculator.png "Distances, magnitudes and a constant in one script.")

10 pc is `32.6156 lyr`; an AB magnitude of 5 is `36.3078 Jy`; the escape speed from 1 AU around the Sun is `42.12 km/s`. The line `v_esc = ...` shows an unsimplified unit (`m(3/2) solMass(1/2) / ...`); the following `.to(u.km / u.s)` line gives the readable one.

## Constants of a chosen edition

Open [Physical constants](../reference/basics/constants.md), set **Filter** to `IAU` and press **List constants**. The table shows the IAU values: `GM_sun = 1.3271244e+20 m3 / s2` (nominal, exact), `au = 1.495978707e+11 m`, `L_sun = 3.828e+26 W`. In **Calculator**, `(const.M_sun / const.M_earth).decompose()` gives the mass ratio `332946`.

![Constants filtered by IAU with the calculator](../assets/guides/basics-constants.png "Filter the constants table and compute a mass ratio.")

`M_sun` and `M_earth` carry a relative uncertainty of 2.2e-05 (from G); the `GM` values are exact, so for orbital work use `GM_sun` rather than `G * M_sun`. Pick another **Constants set** when you must reproduce a published number.
