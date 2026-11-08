## What it does

Edits workspace tables: add, rename, convert and remove columns, mask, sort, filter, find unique rows and look up values, and make QTable, SkyCoord or Time columns.

## How to use

1. Choose the **Table** and optionally an **Output name** (blank: the table is changed under its own name, or the result gets a suffix such as `_filtered`).
2. Pick one operation:

| Button | Uses |
|---|---|
| Add / replace column | **Column name**, **Expression** (`a * u.m`, `sqrt(x**2 + y**2)`), **Unit** |
| Rename | **Column**, **New name** |
| Set unit / format / description | **Column**, **Unit**, **Format** (`%.3f`), **Description** (`-` clears) |
| Convert unit | **Column**, **Convert to unit** |
| Remove column(s) | **Remove columns** or the selected **Column** |
| Mask rows / Unmask / Fill masked values | **Mask where**, **Fill value** |
| Sort | **Keys**, **Reverse sort** |
| Filter rows | **Filter where** (`(a > 3) & (b < 9)`) |
| Unique rows | **Keys**, **Unique: keep** (`first`, `last`, `none`) |
| Lookup via index (loc) | **Column**, **Lookup value** |
| Table <-> QTable | converts between plain columns and Quantity columns |
| Make SkyCoord column (RA/Dec) | **New column**, **RA column**, **Dec column**, **RA unit**, **Frame** |
| Make Time column from selected | **Column**, **Time format**, **Time scale** |

## Reading the results

Starting from `a` = 3, 1, 2, 5: `c = a * 2` adds `6, 2, 4, 10`; Sort by `a` gives 1, 2, 3, 5; Filter `a > 1` stores `t_filtered` with 3 rows. The **Info** tab states `Stored table 't': 4 rows x 4 columns`.

## Tips and limits

- Expressions see the column names (use `c['odd name']` for other names) plus `u`, `np`, `const`, `sqrt`, `log10` and so on. Boolean logic with `&`, `|`, `~` (or `and`, `or`, `not`) works element-wise.
- Units stay on a column only when it is a Quantity column; use **Table <-> QTable** if arithmetic should respect units.
