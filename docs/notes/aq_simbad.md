## What it does

Queries [SIMBAD](https://simbad.cds.unistra.fr/), the astronomical database run by CDS Strasbourg, for objects by name, position, catalog designation or bibliographic reference, or with free ADQL. Results come from the remote service; see [the category overview](index.md) for the shared layout, offline mode and error messages.

## How to use

Pick a **query mode** in the drop-down under the description. Required fields are marked `*`.

| Query mode | Fill in | Returns |
|---|---|---|
| Query object | **Object name** `*`; optionally **Wildcard**, **ADQL criteria** | One row per matching object |
| Query several objects | **Object names** `*` (one per line or comma separated); optionally **Wildcard**, **ADQL criteria** | Rows for all names |
| Query region | **Coordinates** `*`, **Radius** `*`; optionally **ADQL criteria** | Objects inside the cone |
| Query catalog | **Catalog id** `*` (a prefix such as `M`, `NGC`, `HD`); optionally **ADQL criteria** | Members of that catalog |
| Objects of a bibcode | **Bibcode** `*`, for example `2005A&A...430..165F` | Objects cited in that paper |
| Reference by bibcode | **Bibcode** `*`; optionally **Wildcard**, **Abstract** | The reference record |
| Identifiers of object | **Object name** `*` | All identifiers of one object |
| Hierarchy (parents/children) | **Object name** `*`, **Relation** (`parents`, `children`, `siblings`), **Detailed** | Related objects |
| ADQL (TAP) | **ADQL query** `*`, **Max records** | Whatever your query selects |
| Show tables | nothing | The tables of the SIMBAD TAP service |
| Show columns | **Tables** `*`, **Keyword** | Column names and descriptions |
| Show votable fields | nothing | Extra fields you can add with **Extra fields** |
| Show linked tables | **Table** `*` | Tables joinable to that table |

1. Choose the query mode.
2. Fill in its fields. For a region search, type the position as `10.68 41.27` or `00h42m44s +41d16m09s`, or the name of a coordinate list in the workspace. Give the radius with a unit, for example `5 arcmin`.
3. Optional on most modes: **Extra fields** adds SIMBAD output columns, comma separated (`otype, sp_type, V`). Run **Show votable fields** first to see the valid names. **Max rows** limits the result; **-1** asks for SIMBAD's maximum.
4. Press **Run query**.
5. Use **Store table in workspace** to keep the result.

![Region query ready to run](../../assets/guides/online-simbad-form.png "SIMBAD with 'Query region' selected and two extra fields requested.")

## Reading the results

The **Table** tab holds one row per object. The default columns identify the object and give its position and a few basic properties; the columns you add through **Extra fields** follow them. **Info** shows the row and column counts. A search with no hits shows `(no rows returned)`.

**ADQL criteria** is an extra condition written in the ADQL syntax and added to the query, for example `otype = 'G..'` to keep only galaxies. Column names are those of SIMBAD's `basic` table; **Show columns** with Tables set to `basic` lists them.

## Tips and limits

- **Max rows** defaults to 100 and is applied as SIMBAD's row limit. A large cone around a dense field is cut at that number without any warning, so check the row count.
- In **Query region** the **Coordinates** field resolves a typed object name through CDS Sesame before the query is sent. In **Query object** the name goes to SIMBAD unchanged.
- **Wildcard** makes `*` and `?` in the name act as wildcards.
- **ADQL (TAP)** sends your text as written. **Max records** (default 10000) caps the number of rows the server returns. The default query is `SELECT TOP 10 main_id, ra, dec FROM basic`.
- Creating the SIMBAD client contacts the server to read its limits, so even an invalid query fails with a `Network error` when you are not connected.
- The page creates a fresh client for every query, so **Extra fields** never carry over to the next run.
- Other SIMBAD functionality is reachable from the [Astroquery Browser](astroquery_browser.md) (service `simbad`).
