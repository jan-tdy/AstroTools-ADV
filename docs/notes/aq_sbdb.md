## What it does

Looks up an object in the [JPL Small-Body Database](https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html): orbital elements, physical parameters, discovery circumstances and close approaches. Results come from the remote service; see [the category overview](index.md).

## How to use

1. Enter the **Target** `*`: a name, number or designation.
2. **Search mode**: `search` (default), `spk` (SPK-ID), `designation` or `name`.
3. Tick what to include: **Physical parameters**, **Discovery circumstances**, **Close approaches**; **NEO only** restricts the search to near-Earth objects.
4. Press **Run query**.

## Reading the results

The answer is a nested record, not a table, so it appears as text in the **Info** tab (the table tab stays empty). It lists the object, orbit elements and the blocks you ticked.

## Tips and limits

- **Timeout (s)** has no effect on this page; the client uses its own built-in timeout.
- Unknown names return an error message from JPL.
