## What it does

Takes a unit apart, finds equivalent units, searches astropy's unit registry and lets you define a custom unit for the session.

## How to use

| Button | Uses | Returns |
|---|---|---|
| **Analyze unit** | **Unit** | Name, physical type, strings in several formats (generic, latex, unicode, fits, ogip, vounit, cds), decomposition into SI and CGS bases, composed alternatives |
| **Find equivalent units** | **Unit**, **Include prefixed units** | Table of registry units with the same physical type and the value of 1 such unit in your unit |
| **Search unit registry** | **Registry search** | Units whose name, alias or long name contains the text |
| **List prefixes** | none | The SI prefixes |
| **Define custom unit** | **New unit name**, **New unit =** | Registers the unit |

1. Type a unit expression in **Unit**, for example `erg / (s cm2 Angstrom)`.
2. Press **Analyze unit**. For the example, the decomposition is `1e+07 kg / (m s3)` (scale 9999999.999999998), `Compose: 2.75423e+08 ST`.
3. Press **Find equivalent units**; the **Units** tab shows `ST` with `3.630780548e-09`, the value of 1 ST in your unit.
4. **Registry search** `parsec` gives `pc, parsec, length, 3.085677581e+16`.

## Tips and limits

- Defining `smoot` = `1.7018 m` prints `Defined smoot = 1.7018 m` and the unit is accepted in every unit field until the program closes; it is not saved.
- Tick **Include prefixed units** to also find `km`, `MHz`, `uJy`; the list becomes long.
- Some formats print deprecation warnings (for example `Angstrom` in VOUnit); they are harmless.
