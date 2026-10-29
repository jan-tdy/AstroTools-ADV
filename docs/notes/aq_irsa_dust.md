## What it does

Looks up Galactic dust reddening and extinction at a position from the dust maps served by [IRSA](https://irsa.ipac.caltech.edu/applications/DUST/) (the Schlegel, Finkbeiner & Davis and Schlafly & Finkbeiner maps). Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Dust extinction | **Position** `*`; optionally **Radius** | A table of E(B-V) values and extinctions in many filters |
| Dust table section | **Position** `*`; optionally **Radius**, **Section** | One section of the IRSA result, for example `ebv` |

1. Choose **Dust extinction** for the usual answer.
2. Type the **Position** as a name (`M31`, resolved by IRSA) or as coordinates (`10.68 41.27`).
3. **Radius** is optional and must be an angle with a unit, for example `2 deg`. The service has a limit on it and rejects values it does not allow.
4. Press **Run query**.

## Reading the results

The extinction table has one row per filter with the extinction in magnitudes for that filter and the reddening E(B-V) it was derived from. Use the row for your filter to correct an observed magnitude. **Info** shows the row and column counts.

## Tips and limits

- The numbers describe the Galactic dust column only; they say nothing about dust in the target.
- Different maps give somewhat different E(B-V). The returned table says which map each column comes from.
- **Dust table section** is for people who know the IRSA response layout. Without a **Section** it returns the default section.
- **Timeout (s)** applies to IRSA Dust queries.
