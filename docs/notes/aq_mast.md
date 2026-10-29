## What it does

Searches the [Mikulski Archive for Space Telescopes (MAST)](https://mast.stsci.edu/) for observations (HST, JWST, TESS, Kepler and others) and for MAST-hosted catalogs. The page runs metadata queries only: it lists observations and the data products belonging to them, but does not download files, and it does not log in, so proprietary data cannot be listed. Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Observations: object | **Object name** `*`, **Radius** `*` (default `0.2 deg`) | Observations near the object |
| Observations: region | **Coordinates** `*`, **Radius** `*` | Observations in the cone |
| Observations: criteria | **Criteria** `*` | Observations matching the criteria |
| Observations: data products | **Observation ids**, or **...or workspace table** | The files belonging to those observations |
| Catalogs: object | **Object name** `*`, **Radius** `*`, **Catalog** | Catalog sources near the object |
| Catalogs: region | **Coordinates** `*`, **Radius** `*`, **Catalog** | Catalog sources in the cone |
| Catalogs: criteria | **Catalog**, **Criteria** `*` | Catalog rows matching the criteria |

1. Choose the query mode.
2. **Criteria** takes one `key=value` per line. The keys are MAST column names; ranges are written as lists. The default is `obs_collection=HST` and `dataproduct_type=image`, and an example with a range is `t_exptime=[100, 1000]`. Catalog criteria look like `Tmag=[8, 10]`.
3. **Catalog** offers `hsc`, `tic`, `ctl`, `diskdetective`, `panstarrs`, `galex` and `gaia`.
4. To list the files of observations you found, either type their **Observation ids** (`obsid` values, comma separated) or store the observations table in the workspace first and select it in **...or workspace table**. If you fill in both, the typed ids are used.
5. Press **Run query**.

## Reading the results

Observation tables have one row per observation with columns such as collection, target name, instrument, filters, exposure time, position and an `obsid`. The `obsid` column is what the **data products** query needs. A product table has one row per file with its name, type, size and `dataURI`. Catalog queries return the columns of the chosen catalog. **Info** shows the counts.

## Tips and limits

- A search around a famous target in HST or JWST data can return thousands of rows. Use a small radius or the criteria mode.
- Criteria keys that MAST does not know give an error from the service. The [Astroquery Browser](astroquery_browser.md) (service `mast`, object `Observations`, method `get_metadata`) lists the valid column names.
- To fetch the files themselves, use the `download_products` method of `Observations` in the Browser or the MAST web portal; this page stops at the product list.
- **Timeout (s)** has no effect on MAST queries.
- MAST asks users to acknowledge it in publications; the wording is on the MAST website.
