## What it does

Opens and creates astropy Tables, inspects them and saves them to a file, and moves them to and from pandas.

## How to use

- **Open.** Enter the **File**, choose **Format** (`auto` identifies it; plain text falls back to a guess) and optional **Options** (`hdu=2; delimiter=','; path='data'`), set **Store as** (default `table1`), press **Open**.
- **Create.** Paste CSV or any text that `astropy.io.ascii` can guess into **Text**, set **Store as** (default `pasted`), press **Create**.
- **Inspect.** Choose the workspace **Table**. **Column info** shows dtype, unit, format, description and number of bad values; **Column statistics (info)**; **Describe** gives count, mean, std, min, quartiles and max; **Formatted text (pformat)**; **Row detail** shows one **Row**; **Table metadata** shows the `meta` dictionary.
- **pandas.** **Table -> pandas DataFrame** and **Workspace DataFrame -> Table**.
- **Save.** Set **File**, **Format**, **Overwrite**, press **Save**.

## Reading the results

For a 4-row table with columns `a` (3, 1, 2, 5) and `b` (1.5, 2.5, 0.5, 4.0), **Describe** gives count 4, mean 2.75 and 2.125, std 1.479 and 1.293, min 1 and 0.5, median 2.5 and 2.0, max 5 and 4. **Info** shows the text version and **Table** the grid.

## Tips and limits

- **Output name** blank keeps the source name, so operations may replace the table.
- Use `ecsv` or `fits` for files that must retain units.
- Continue with [Tables: Edit](table_edit.md), [Group / Join / Stack](table_combine.md) and [Plot](table_plot.md).
