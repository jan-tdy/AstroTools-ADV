## What it does

Queries the [NASA/IPAC Extragalactic Database (NED)](https://ned.ipac.caltech.edu/) for galaxies and other extragalactic objects by name, position or reference. Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Query object | **Object name** `*` | The NED record of the object |
| Query region | **Coordinates** `*`, **Radius** `*` (default `1 arcmin`) | Objects inside the cone |
| Object data table | **Object name** `*`, **Table** | One data table for the object |
| Image list | **Object name** `*` | A one-column table `url` of FITS image URLs |
| Objects of a reference | **Reference code** `*` | Objects in that publication |

1. Choose the query mode and fill in its fields.
2. For **Object data table**, choose the table: `photometry`, `positions`, `diameters`, `redshifts`, `references` or `object_notes`.
3. For **Objects of a reference**, enter NED's 19-digit reference code (it is the bibcode written in NED's own form; the object's NED page shows it).
4. Press **Run query**.

## Reading the results

The **Table** tab lists the NED columns returned: object name, position, type, redshift and so on for object and region searches; photometry points, redshift measurements or other records for the data tables. **Info** shows the row and column counts.

**Image list** only lists addresses. The page does not download the images. To get a picture of a field use [SkyView](aq_skyview.md), or open the URLs in a browser or with the [Astroquery Browser](astroquery_browser.md) method `get_images`.

## Tips and limits

- Object names are resolved by NED itself, so use the names NED knows (`NGC 224`, `M31`). An unknown name returns an error or an empty table, depending on the query.
- A region search on a crowded field can return thousands of rows. Start with a small radius.
- **Timeout (s)** applies to NED queries.
