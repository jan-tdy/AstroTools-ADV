## What it does

Groups and aggregates a table and combines tables: join, set difference, vstack, hstack and dstack.

## How to use

- **Group.** Choose the **Table**, give **Keys** (comma separated) and an **Aggregate** (`mean`, `sum`, `min`, `max`, `median`, `std`, `count`, `first`). **Aggregate groups** applies it; **Group sizes** lists rows per group.
- **Join.** Choose the **Table** (left), the **Right table**, **Keys**, **Join type** (`inner`, `outer`, `left`, `right`, `cartesian`) and **Suffixes** (`_1,_2`) for clashing names. Press **Join**. **Set difference (left - right)** keeps left rows that have no match.
- **Stack.** In the **Tables** list select two or more tables, choose **Join type** (`outer`, `inner`, `exact`: exact requires identical columns or row counts) and press **vstack (append rows)**, **hstack (side by side)** or **dstack (new axis)**.

## Reading the results

Grouping `a` = 3, 1, 2, 5 and `b` = 1.5, 2.5, 0.5, 4.0 by `g` = x, y, x, y with `mean` gives x: a 2.5, b 1.0 and y: a 3.0, b 3.25. The result is stored as `<name>_grouped`.

## Tips and limits

- Always check the **Table** drop-down before the next step: after an operation the selection can point at the new result, so **Group sizes** may count the aggregated table (one row per group) rather than the original.
- Aggregating text columns with `mean` drops or fails on them; keep only numeric columns.
- `inner` joins lose unmatched rows; `outer` fills them with masked values.
