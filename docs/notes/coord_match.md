## What it does

Cross-matches two workspace tables by sky position or 3D position: nearest neighbour (`match_to_catalog_sky`, `match_to_catalog_3d`) or all pairs within a limit (`search_around_sky`, `search_around_3d`).

## How to use

1. Put both tables in the workspace (for example with [Table manager](../data/table_manager.md)).
2. Choose the **Table** for A (the list to match) and in the second panel for B (the reference catalog). Select the **Lon / RA column** and **Lat / Dec column**; the optional distance, proper-motion and RV columns improve 3D matching.
3. Choose the **Operation** and **Limit**: an angle for sky (`1 arcsec`), a length for 3D (`10 pc`). **n-th neighbour** 1 = nearest.
4. **Keep unmatched rows** keeps A rows whose nearest B is beyond the limit, flagged in the table.
5. Press **Match**; **Store table in workspace** saves it under **Workspace name** (default `matched`).

## Reading the results

The **Matches** tab joins both tables: `idx_a`, `idx_b`, `sep_arcsec`, `matched`, then A columns prefixed `a_` and B columns prefixed `b_`. Example from the guide: five detections against six reference stars with limit `2 arcsec`: separations 0.36, 0.41, 6.0, 0.29 and 2585 arcsec, `matched` True, True, False, True, False. **Summary**: `5 row(s). 3 within the limit.`

## Tips and limits

- With `search_around_*` a row can appear several times, or not at all.
- Nearest-neighbour always returns a nearest B, even a distant one; use `matched` rather than assuming every row is a real match.
- 3D operations need a distance for both tables, otherwise `3D matching needs a distance column/value for both A and B.`
- See [Catalog cross-match guide](../../guides/catalog-crossmatch.md).
