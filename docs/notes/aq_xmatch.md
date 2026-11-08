## What it does

Cross-matches two catalogues with the [CDS XMatch](http://cdsxmatch.u-strasbg.fr/) service. Each side is either a CDS table or a table from your workspace. Results come from the remote service; see [the category overview](index.md).

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Cross-match | Catalog 1 and Catalog 2, **Max distance** `*` (default `5 arcsec`) | The matched rows |
| Available CDS tables | nothing | The tables XMatch knows |

1. For each side either enter a CDS id (`vizier:II/246/out`, `simbad`) in **Catalog 1 (CDS id)** / **Catalog 2 (CDS id)**, or choose a table in **...or workspace table 1** / **2**. A filled CDS id wins over a table.
2. For workspace tables the **RA column** and **Dec column** may be left empty and are detected; set them when there are several candidates. Coordinates must be in degrees.
3. Set **Max distance** and press **Run query**.

## Reading the results

The result lists the matched rows with the columns of both catalogues and the angular distance between them.

## Tips and limits

- A workspace table is **uploaded** to CDS when you run the query (see "What is sent" in the category overview).
- Default catalog 2 is `vizier:II/246/out` (2MASS).
- For local matching without upload use [Catalog matching](../coordinates/coord_match.md).
