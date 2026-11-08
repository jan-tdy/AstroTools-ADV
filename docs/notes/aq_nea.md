## What it does

Queries the [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/) tables by planet or host name, by criteria or by sky region. Results come from the remote service; see [the category overview](index.md).

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Query object | **Planet/host name** `*`, **Table** | Rows for that planet or host |
| Query criteria | **Table**, **Select** (`pl_name,hostname,pl_rade`), **Where** (`pl_rade<2 and disc_year>2020`), **Order by** | Rows satisfying the ADQL condition |
| Query region | **Table**, **Coordinates** `*`, **Radius** `*` (default `1 deg`) | Rows inside the cone |
| Object aliases | **Object name** `*` | Alternative names |

**Table**: `ps` (all parameter sets, many rows per planet), `pscomppars` (one composite row per planet), `stellarhosts`, `keplernames`.

1. Choose the mode and fill its fields, then press **Run query**.
2. Store the result with **Store table in workspace**.

## Reading the results

Each row is one planet (or parameter set); columns follow the archive naming (`pl_name`, `hostname`, `pl_rade`, `disc_year`...).

## Tips and limits

- Use `pscomppars` for one value per planet; `ps` gives every published solution.
- **Select** `*` returns the default column set.
- **Timeout (s)** applies to this page.
