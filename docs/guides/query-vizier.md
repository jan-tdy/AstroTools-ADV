---
title: Querying VizieR
order: 51
lede: Search a catalog in a box on the sky with filters on a column.
---

VizieR queries need a network connection, so this guide shows the form.

Open [VizieR](../reference/online/aq_vizier.md).

1. Choose the query mode **Query region**.
2. **Coordinates**: `10.68 41.27`. Leave **Radius** empty and use a box: **Width** `20 arcmin`, **Height** `10 arcmin`.
3. **Catalogs**: `I/239/hip_main` (the Hipparcos main catalog).
4. **Columns**: `*`. **Filters**: `Vmag=<9` (stars brighter than 9th magnitude). **Max rows**: `25`.

![VizieR box query ready to run](../assets/guides/online-vizier-form.png "VizieR with a box region query and a magnitude filter.")

5. Press **Run query**.

VizieR can return one table per catalog. Choose the one to show in **Result table**; all returned tables are listed in **Info** with their rows and columns. Store the shown table with **Store table in workspace**. Use **Find catalogs** with a keyword (for example `hipparcos`) to find a catalog id first.
