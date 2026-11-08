---
title: Cross-matching two catalogs
order: 21
lede: Match a list of detections against a reference catalog by sky position and decide which pairs are real.
---

Put two tables in the workspace: `sources` (your detections, columns `id`, `ra`, `dec`, `flux`) and `reference` (columns `name`, `RAJ2000`, `DEJ2000`, `Vmag`). Load them with [Tables: Open / Inspect / Save](../reference/data/table_manager.md) (**Open** or **Create**).

Open [Catalog matching](../reference/coordinates/coord_match.md).

1. Choose **Table** `sources` for A and `reference` for B; the longitude and latitude columns are picked from their names (`ra`/`dec`, `RAJ2000`/`DEJ2000`).
2. **Operation**: `match_to_catalog_sky (nearest on sky)`.
3. **Limit**: `2 arcsec`.
4. Press **Match**.

![Catalog matching](../assets/guides/coords-crossmatch.png "Five detections matched against six reference stars.")

The **Matches** tab has one row per detection:

| id | nearest | separation | matched |
|---|---|---|---|
| s1 | HD 1 | 0.36" | True |
| s2 | HD 2 | 0.41" | True |
| s3 | HD 3 | 6.0" | False |
| s4 | HD 4 | 0.29" | True |
| s5 | HD 6 | 2585" | False |

**Summary** says `5 row(s). 3 within the limit.` The nearest neighbour of `s3` is a real star 6 arcsec away, beyond the limit, and `s5` has no counterpart: the nearest catalog star is 43 arcmin away. Both are flagged `matched = False` rather than dropped, because **Keep unmatched rows** is on.

Choose a **Limit** from the astrometric accuracy of the worse catalog and keep it well below the typical separation between neighbours. Press **Store table in workspace** to keep the joined table for further work.
