## What it does

Queries [VizieR](https://vizier.cds.unistra.fr/), the CDS library of published astronomical catalogs, by object, region or column constraints, and can search the catalog list or download a whole catalog. Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Query object | **Object name** `*`; optionally **Radius**, **Catalogs**, **Columns**, **Column filters**, **Max rows** | Catalog rows around the object |
| Query region | **Coordinates** `*`, and either **Radius** or both **Box width** and **Box height**; optionally **Catalogs**, **Columns**, **Column filters**, **Max rows** | Catalog rows inside the cone or box |
| Query constraints | **Constraints** `*`; optionally **Catalogs**, **Columns**, **Max rows** | Rows satisfying the constraints, with no position search |
| Find catalogs | **Keywords** `*`, **Max catalogs** | A table of catalog ids and descriptions |
| Download catalog | **Catalog id** `*`, **Max rows** | The tables of that catalog |
| Catalog metadata | **Catalog id** `*` | Column descriptions of that catalog |

1. Choose the query mode.
2. To search a particular catalog, type its id in **Catalogs** (`I/239/hip_main`, one per line or comma separated). Leave it empty to search every catalog that has rows there. If you do not know the id, run **Find catalogs** first with keywords such as `hipparcos`.
3. **Columns** selects the output columns: `*` is VizieR's default set, `**` is all columns, and `+_r` adds the distance to the search centre.
4. **Column filters** and **Constraints** take one condition per line in VizieR syntax: `Vmag=<10`, `SpType=~K*`.
5. Press **Run query**.

![VizieR region query with a box](../../assets/guides/online-vizier-form.png "'Query region' with a 20 by 10 arcminute box, one catalog and a Vmag filter.")

## Reading the results

VizieR returns one table per catalog table that matched. The **Result table** drop-down lists them by catalog id; choose the one to display, store or save. The **Info** tab lists the row and column counts of each.

**Find catalogs** returns two columns, the catalog `name` and its `description`. **Catalog metadata** returns the column descriptions of the catalog.

## Tips and limits

- **Max rows** defaults to 50 and is passed to VizieR as its row limit; **-1** means unlimited. A catalog bigger than the limit is truncated silently. Always compare the row count with what you expect.
- In **Query region**, when both **Box width** and **Box height** are filled in the box is used and the **Radius** is ignored. If neither a radius nor a complete box is given the page refuses with `Give a radius, or both width and height.`
- In **Query constraints** there is no search position; the constraints must be selective enough for the catalog you named, or you will retrieve the first rows of a large table.
- **Query object** passes the name to VizieR, which resolves it. **Coordinates** in **Query region** is parsed here; a name typed there is resolved through CDS Sesame first.
- VizieR catalog ids have the form `I/239/hip_main` (catalog/table). The id of a catalog is shown on its VizieR web page.
- For catalogs with multiple tables **Download catalog** returns all of them.
