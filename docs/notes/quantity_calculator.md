## What it does

Evaluates several lines of astropy `Quantity` arithmetic, including magnitudes, dex and decibels, and keeps the last result.

## How to use

1. Write one expression per line in **Expressions**. A line `name = expr` defines a variable usable in later lines; lines starting with `#` are comments.
2. Available names: `u`, `np`, `const`, `Quantity`, `Magnitude`, `Dex`, `Decibel` and math functions such as `sqrt`, `exp`, `log10`.
3. Press **Evaluate**. **Store result in workspace** keeps the last result under **Store as** (default `calc`).

## Reading the results

Each line is echoed with its value and physical type. Example:

```text
a = 3 * u.km / u.s     ->  3.0 km / s   [speed/velocity]
b = a.to(u.pc/u.Myr)   ->  3.068136495137085 pc / Myr
sqrt(4 * u.m**2)       ->  2.0 m   [length]
```

## Tips and limits

- Expressions are Python; only the listed names exist.
- Magnitude, dex and decibel units follow astropy's logarithmic-unit rules: add and subtract them, but do not multiply.
- A failing line stops the evaluation and the message names that line.
- See [Physical constants](constants.md) for `const.*` values.
