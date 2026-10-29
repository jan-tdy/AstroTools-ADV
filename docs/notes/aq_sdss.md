## What it does

Searches the [Sloan Digital Sky Survey](https://www.sdss.org/) catalogs by position, cross-identifies positions against it, or runs a SQL query on the SDSS CAS database. Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Query region | **Coordinates** `*`, **Radius** `*` (default `2 arcmin`), **Spectroscopic only**, **Data release** | Objects in the cone |
| Cross-identify | **Coordinates** `*`, **Radius** `*` (default `5 arcsec`), **Spectroscopic only**, **Data release** | The nearest objects to each position |
| SQL query | **SQL** `*`, **Data release** | Whatever your query selects |

1. Choose the query mode.
2. **Data release** is the number of the SDSS data release (default 17).
3. Tick **Spectroscopic only** to restrict the result to objects that have an SDSS spectrum.
4. For SQL, the default query is `SELECT TOP 10 objID, ra, dec, r FROM PhotoObj`. Use the SDSS SkyServer schema browser to find table and column names.
5. Press **Run query**.

## Reading the results

The **Table** tab lists the SDSS objects with their IDs, positions and magnitudes (the default photometric columns for region and cross-identification queries). With **Spectroscopic only** the rows are the objects that have a spectrum. **Info** shows the row and column counts. If nothing is found astroquery may return no table at all, and the **Info** tab then reports the empty result.

## Tips and limits

- **Cross-identify** accepts a workspace coordinate list (type its name in **Coordinates**) and returns matches for each position.
- SQL queries are executed by the SDSS server, which limits query time and result size. Put `TOP n` in the query for exploration.
- A data release that does not exist or is not supported by the installed astroquery produces an error from the service.
- **Timeout (s)** applies to SDSS queries.
