## What it does

Inspects, validates, converts and writes VOTable files, the XML table format of the Virtual Observatory.

## How to use

1. Enter the **File** path, choose **Verify** (`warn`, `ignore`, `exception`: how strictly the spec is enforced) and press **Open**. The **Structure** tab shows resources and tables.
2. **Show fields / params** fills the **Fields** (columns with datatype, unit, UCD) and **Params** tabs.
3. **Validate against the spec** writes a report to **Validation**.
4. Choose **Table #** (default 0) and press **Table -> workspace**; the table is kept under **Store as** (default `votable_table`).
5. To write, select a workspace **Table**, choose the **Serialization** (`tabledata` text, `binary`, `binary2`) and press **Write VOTable** (**Overwrite** to replace a file).

## Reading the results

**Data** shows the table. **Validation** holds the report of `astropy.io.votable.validate`: a verdict and the warnings or errors it found, quoted from the file.

## Tips and limits

- `binary2` supports masked values and is the most compact; `tabledata` is readable in an editor.
- Files from archives often produce warnings but still load; use `exception` only when you want to find the problems.
- Units in the VOTable are kept on the columns when converted to the workspace.
