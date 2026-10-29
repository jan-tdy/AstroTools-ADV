The pages in this category talk to remote archives through [astroquery](https://astroquery.readthedocs.io/), plus **SAMP**, which talks to other programs on your own computer. Everything on the remote side (what exists, how fast it answers, how many rows it returns) is decided by the service, not by AstroTools-ADV. A query that worked yesterday can fail today because the archive is down or has changed its schema.

## Layout of an archive page

The fifteen dedicated pages (SIMBAD to Spectral Lines) share one layout. Reading it once covers all of them.

1. **Query selector.** The drop-down at the top of the form, directly under the one-line description, chooses *which* query the page runs: for SIMBAD, "Query object", "Query region", "ADQL (TAP)" and so on. This guide calls it the **query mode**. Each mode has its own fields; changing the mode swaps the whole form.
2. **Fields.** A field marked with `*` is required for the selected mode. Hover a field for its tooltip.
3. **Network** and **Timeout (s)**. The **Offline mode** check box and the timeout, described below.
4. **Result table**, **Store as** and the buttons **Store table in workspace**, **Store images/objects in workspace** and **Save table to file...**.
5. **Run query** at the bottom of the left column.

On the right, the **Table** tab shows the returned table and the **Info** tab shows a summary, or the explanation when something went wrong.

![SIMBAD page with a region query filled in](../../assets/guides/online-simbad-form.png "A filled-in form before pressing Run query: query mode 'Query region', an ICRS position, a 5 arcminute radius and two extra SIMBAD fields.")

## What is sent

Pressing **Run query** sends the values of the selected mode (object names, coordinates, radius, ADQL text, catalog ids, and so on) to the service's server over the internet. Two cases send more:

- A name typed into a field labelled **Coordinates** (for example `M31`) is first sent to the CDS Sesame name resolver, which returns a position. Fields labelled **Position** (SkyView, IRSA Dust) and **Object name** pass the name on unchanged and the service resolves it.
- [CDS XMatch](aq_xmatch.md) uploads a workspace table when you choose one as an input.

Nothing else from the workspace is transmitted. Typing a position as numbers (`10.68 41.27`) involves no name lookup.

## Offline mode

The **Offline mode (block all network access)** check box in the **Network** row switches off every online page at once, and its state is shared: ticking it on one page ticks it on all pages. With it on, **Run query** does not contact anything; the **Info** tab shows

```text
Offline mode is on - no network access is allowed. Untick 'Offline mode' to run queries.
```

and the status bar shows `Offline mode`. The switch is not saved; it is off every time the program starts.

## Timeout

**Timeout (s)** (default 30) is handed to the service object before each query. It limits the time to connect and receive an answer; it does not cap a query that the server accepted and is still computing. If a query times out you get a `Network error` message in the **Info** tab and can raise the value.

## Values the fields accept

- **Coordinates.** `10.68 41.27` (degrees), `00h42m44s +41d16m09s`, an object name (needs network), or the name of a coordinate list or table in the [workspace](../../concepts/workspace.md). A table needs RA and Dec columns with a recognisable name (`ra`, `ra_icrs`, `raj2000`, `_raj2000`, and the matching Dec names); degrees are assumed when the column has no unit.
- **Radius and other quantities.** A number with a unit, for example `2 arcmin`, `0.5 deg`, `10 arcsec`. A bare number is read in the field's default unit, usually degrees. A unit of the wrong kind, such as `1 m` for a radius, is refused with a message naming the field. See [entering values](../../concepts/entering-values.md).
- **Lists.** Fields that take several items (object names, catalogs, columns) accept one item per line or items separated by commas.
- **Key/value fields** (criteria, constraints, filters). One `key=value` per line, for example `Vmag=<10`. Values are evaluated as expressions where possible, so `t_exptime=[100, 1000]` becomes a list and `obs_collection=HST` stays text.

## Results

- Rows appear in the **Table** tab. **Copy CSV** copies what is shown.
- The **Info** tab always lists, for each returned table, its number of rows and columns and the column names. A query that matches nothing reports `(no rows returned)`; it is not an error.
- Some services return several tables at once (VizieR returns one per catalog). Choose which one to display and store in the **Result table** drop-down.
- **Store table in workspace** keeps the displayed table under the name in **Store as**, where other tools can use it; storing under an existing name replaces it. **Save table to file...** writes it as ECSV, CSV, FITS, VOTable or HTML according to the extension you pick.
- Images and other non-table objects (FITS images from SkyView, for example) are listed in the **Info** tab and kept with **Store images/objects in workspace**. With several objects the names get `_0`, `_1`, ... appended.
- Results that are not tables (the JPL Small-Body Database returns nested records) are printed in the **Info** tab as text.

## Errors you may see

| Message | Meaning |
|---|---|
| `Input error: 'Radius' is required.` | A `*` field is empty or could not be parsed. Nothing was sent. |
| `Network error: the service could not be reached or timed out.` | No connection, DNS or proxy problem, server down, or the timeout was too short. The details follow in the message. |
| `Error: SomeError: ...` | The service answered with an error: unknown object, malformed ADQL, no such catalog. The wording comes from the service. |

An answer that arrives after you started a newer query on the same page, or after the page was closed, is discarded.

## Citing and acknowledging

If you publish results, acknowledge the services you used; each archive states its own wording on its website. AstroTools-ADV itself is a front end, so cite the software it relies on:

- astroquery: Ginsburg et al. 2019, AJ 157, 98.
- astropy: see **System → About & Citation** for the version you are running.
- SIMBAD: Wenger et al. 2000, A&AS 143, 9. VizieR: Ochsenbein, Bauer & Marcout 2000, A&AS 143, 23.

Services not listed here (MAST, NED, Gaia, JPL, ...) publish their own acknowledgement text on their sites.

[Astroquery Browser](astroquery_browser.md) reaches every astroquery service that has no dedicated page; [SAMP](samp.md) connects to desktop tools such as TOPCAT, Aladin and DS9.
