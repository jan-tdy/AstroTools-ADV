---
title: Querying SIMBAD
order: 50
lede: Look up objects around a position with SIMBAD, choose extra columns and keep the result.
---

SIMBAD queries need a network connection, so this guide shows the form and describes what happens when you run it.

Open [SIMBAD](../reference/online/aq_simbad.md).

1. Choose the query mode **Query region**.
2. **Coordinates**: `10.68 41.27`. **Radius**: `5 arcmin`.
3. **Extra fields**: `otype, sp_type` (add object type and spectral type; **Show votable fields** lists the valid names).
4. **Max rows**: `50`.

![SIMBAD region query ready to run](../assets/guides/online-simbad-form.png "SIMBAD with 'Query region' selected and two extra fields requested.")

5. Make sure **Offline mode** is off and press **Run query**.

The **Table** tab then lists the objects within 5 arcmin of M31's core, one row per object: SIMBAD's default columns (main identifier, coordinates) followed by `otype` and `sp_type`. **Info** states the row and column counts; if exactly 50 rows come back, the limit may have cut the list.

Press **Store table in workspace** to keep the table (name in **Store as**), then use it in [Catalog matching](../reference/coordinates/coord_match.md) or [Table plot](../reference/data/table_plot.md). To restrict the result, put an ADQL condition such as `otype = 'G..'` into **ADQL criteria**.

If the network is unavailable the **Info** tab shows a `Network error` message; with **Offline mode** on it shows `Offline mode is on - no network access is allowed.`
