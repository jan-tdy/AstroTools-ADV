## What it does

Searches the [ESA Gaia archive](https://gea.esac.esa.int/archive/) by cone, by cone or box around a position, or with ADQL, using anonymous access. Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Cone search | **Coordinates** `*`, **Radius** `*` (default `10 arcsec`); optionally **Columns**, **Max rows** | Gaia sources in the cone, as an asynchronous archive job |
| Query object (cone/box) | **Coordinates** `*`, and either **Radius** or both **Box width** and **Box height**; **Max rows** | Gaia sources around the position |
| ADQL query | **ADQL** `*`, **Asynchronous job**, **Max rows** | Whatever your query selects |
| List archive tables | nothing | The names of the archive tables |

1. Choose the query mode.
2. For a cone search, type the position (`10.68 41.27`) and a radius with a unit. **Columns** takes column names such as `source_id, ra, dec`; empty means all columns.
3. For ADQL, write the query in **ADQL**. The default is `SELECT TOP 10 source_id, ra, dec, phot_g_mean_mag FROM gaiadr3.gaia_source`. Tick **Asynchronous job** for long queries and for results beyond the synchronous limit (the field's tooltip gives 2000 rows).
4. Press **Run query** and wait. Asynchronous jobs queue on the archive and can take minutes.

## Reading the results

The **Table** tab shows the returned sources; **Info** shows the row and column counts. **List archive tables** returns a one-column table `name`. Use it to find table names such as `gaiadr3.gaia_source` for your own ADQL.

## Tips and limits

- **Max rows** defaults to 50; `-1` means unlimited. The value is set on the shared Gaia archive object and stays in effect for every later Gaia query in this session, including ones made from the [Astroquery Browser](astroquery_browser.md).
- In **ADQL query** mode, limit the number of rows with `TOP n` inside the query itself. That is the reliable way for ADQL.
- In **Query object** mode a complete box (**Box width** and **Box height**) replaces the radius; with neither you get `Give a radius, or both width and height.`
- The **Timeout (s)** field is not applied to Gaia queries.
- Only anonymous access is offered; there is no login, so private user tables and upload are not available here.
- Gaia releases change column names and tables between data releases. If your ADQL fails with a `column not found` message from the server, check the column list on the archive website.
