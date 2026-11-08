## What it does

Opens, creates, inspects, edits and saves FITS files in memory: headers, image HDUs, table HDUs, checksums and file comparison. Nothing is written to disk until you save.

## How to use

The page is a stack of sections, all working on the **HDU** selected in the drop-down at the top (entries look like `0: PRIMARY (PrimaryHDU)`).

1. **File.** Type a **Path** and press **Open**, or press **New (empty primary HDU)**. **Memory-map** and **Lazy HDU loading** suit large files. **Save as...** writes a new file (tick **Overwrite** to replace one); **Write back to opened file** saves to the original path; **Write CHECKSUM/DATASUM** and **Output verify** control what is written.
2. **Header.** **Show header** lists the cards; **Search** filters keyword, value and comment. Fill **Keyword**, **Value** (`5`, `1.5`, `T`, or `"text"` in quotes to force a string) and **Comment**, then **Set / add card**, **Delete card**, **Add HISTORY (Value)** or **Add COMMENT (Value)**.
3. **Image.** **Preview** draws the image with **Stretch** (`linear`, `log`, `sqrt`, `asinh`), **Colormap**, **Low percentile** / **High percentile** and optional **vmin** / **vmax**; **Plane** selects the slice of N-D data (for example `2` or `1,0`). **Pixel statistics** reports the numbers.
4. **Convert.** **HDU -> Table**, **HDU -> NDData** and **HDU -> array** copy the HDU into the [workspace](../../concepts/workspace.md) under **Workspace name**. **Append object as new HDU** and **Replace selected HDU with object** take a **Workspace object** (image, table, NDData) and may use **New HDU name**, **Compression** and **Quantize level**. **Delete selected HDU** removes one.
5. **Check.** **verify() in-memory file**, **Add CHECKSUM + DATASUM**, **Verify checksums on disk** and **FITSDiff (opened file vs. other)** (**Compare with** a path, with **rtol**, **atol**, **Ignore keywords** such as `DATE,CHECKSUM`).
6. **Convenience functions.** **getval**, **getheader**, **getdata -> workspace** and **setval (modifies file!)** act directly on a file on disk, without opening it.

## Reading the results

- **HDUs** is the file structure. A new file shows `0, PRIMARY, PrimaryHDU, 4 cards`; after appending a 3 x 4 array the table adds `1, ImageHDU, 7 cards, 4 x 3, format -64` (float64).
- **Header** shows the card list with indices, **Image** the preview, **Data** a table HDU, **Report** every message and statistic.
- Setting `OBJECT` to `"M31"` stores the string padded to 8 characters (`'M31     '`), as FITS requires.

## Tips and limits

- Dimensions read `NAXIS1 x NAXIS2`, so a NumPy array of shape (3, 4) is shown as `4 x 3`.
- A table cannot be the primary HDU; a plain array can.
- Lossy compression (`RICE_1`, `HCOMPRESS_1`) with a **Quantize level** of 0 rounds float data to integers.
- **setval (modifies file!)** writes immediately, with no undo.
