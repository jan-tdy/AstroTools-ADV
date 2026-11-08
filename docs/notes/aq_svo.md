## What it does

Searches the [SVO Filter Profile Service](http://svo2.cab.inta-csic.es/theory/fps/) for photometric filters and their transmission curves. Results come from the remote service; see [the category overview](index.md).

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Filters by wavelength | **Min effective wavelength** `*` (`4000 Angstrom`), **Max effective wavelength** `*` (`7000 Angstrom`) | All filters whose effective wavelength lies in the range |
| Filters of a facility | **Facility** `*` (`HST`, `2MASS`), optional **Instrument** | The filters of that facility |
| Transmission curve | **Filter id** `*` (`2MASS/2MASS.J`) | Wavelength and transmission table |

Press **Run query** after filling the fields.

## Reading the results

A filter list has one row per filter with its id, facility, effective wavelength and width. Use an id from it in **Transmission curve**.

## Tips and limits

- Wavelengths need a unit.
- **Timeout (s)** applies to this page.
