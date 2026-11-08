## What it does

Converts between distance, parallax and distance modulus, and gives absolute magnitude when you also supply an apparent magnitude.

## How to use

1. Set **Input is** to `distance`, `parallax` or `distmod`.
2. Enter **Values**: numbers separated by spaces, commas or newlines, or an expression such as `np.linspace(1, 10, 5)`.
3. Set **Unit** to match (`pc`, `kpc`, `Mpc`, `ly`, `AU`, `m`, `km` for distances, `mas` for parallax, `mag` for distance modulus).
4. Optional: **Apparent magnitude** adds an `abs_mag` column.
5. Press **Calculate**; **Store table in workspace** keeps the table.

## Reading the results

Distances `10 100 1000` pc give distance modulus 0, 5 and 10 mag and parallax 100, 10 and 1 mas; 1000 pc is 3261.563777 ly and 206264806.2 AU. With apparent magnitude 8 the absolute magnitudes are 8, 3 and -2 for 10, 100 and 1000 pc. Rows keep the order of your input.

## Tips and limits

- Parallax in mas gives distance in pc as 1000 / parallax. A zero or negative parallax has no distance and produces an error.
- This is a pure geometry conversion; extinction is not applied. For dust see [IRSA Dust](../online/aq_irsa_dust.md).
