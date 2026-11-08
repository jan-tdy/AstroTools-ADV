## What it does

Reads and writes text tables in every `astropy.io.ascii` format (CSV, ECSV, basic, fixed width, DAOphot, CDS, LaTeX and others) with a preview of the raw text.

## How to use

**Reading**

1. Enter the **File** path and press **Preview raw text** to see what the file really contains.
2. Leave **Format** at `auto` (with **Guess** on) or choose the format. If guessing picks the wrong one, set the format and then the details: **Delimiter**, **Header line** and **First data line** / **Last data line** (0-based; negative counts from the end), **Column names** (overrides the header), **Comment regex**, **Quote char**, **Fill values** (`NA:0; --:-1`) and **Extra options** (`key=value; key=value`, passed to `ascii.read`).
3. Press **Read**; the table goes to the workspace under **Store as** (default `ascii_table`).

**Writing**

1. Select the workspace **Table** and the output **Format** (default `ecsv`).
2. Optional: **Column formats** (`flux=%.3f; id=%d`), **Include columns**, **Exclude columns**, **Comment prefix**, **Overwrite**.
3. **Show as text (no file)** previews the text in **Written text**; **Write to file** saves it.

## Reading the results

**Raw text** is the file as it is; **Parsed table** the result; **Formats** lists every format with its read/write capability.

## Tips and limits

- Use `ecsv` for tables that must keep units, dtypes and metadata; `csv` keeps only the values.
- An existing file is not replaced unless **Overwrite** is ticked.
- For plain open/save use [Tables: Open / Inspect / Save](table_manager.md).
