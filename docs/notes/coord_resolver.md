## What it does

Looks up object names in the CDS Sesame service (`SkyCoord.from_name`) and returns their ICRS positions. It needs a network connection.

## How to use

1. Write one object name per line in **Object names** (default `M31` and `Vega`).
2. Press **Resolve**.
3. The positions appear in **Resolved** and are stored in the workspace under **Workspace name** (default `resolved`).

## Reading the results

**Resolved** lists each name with its coordinates; **Messages** reports names that could not be resolved. One failing name does not discard the others.

## Tips and limits

- Sesame searches SIMBAD, NED and VizieR; the first hit wins, so ambiguous names (`NGC 1`, `HD 1`) can resolve to an unexpected object. Check the result against a known position.
- With no connection every name fails and the messages tab says the service could not be reached. Offline mode of the Online pages does not apply here.
- The stored `SkyCoord` can be used by [Frame converter](coord_convert.md), [Separations & geometry](coord_geometry.md) and the visibility tools through **Source** = `Workspace SkyCoord`.
