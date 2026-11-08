## What it does

Looks up spectral lines in Splatalogue (radio and millimetre) and NIST (atomic). Results come from the remote services; see [the category overview](index.md).

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Splatalogue (radio/mm lines) | **Min frequency** `*` (`100 GHz`), **Max frequency** `*` (`101 GHz`), **Chemical name** (regular expression, `CO`, ` H2CO `) | Lines in that range |
| NIST atomic spectra | **Min wavelength** `*` (`4000 Angstrom`), **Max wavelength** `*` (`7000 Angstrom`), **Spectrum** `*` (`H I`, `Fe II`), **Energy unit** (`eV`, `cm-1`, `Rydberg`), **Wavelength type** (`vacuum`, `vac+air`) | Lines and energy levels |

Press **Run query**.

## Reading the results

Rows give the species, the line frequency or wavelength, and transition data. Compare line positions with the unit set in **Wavelength type**.

## Tips and limits

- Chemical names are regular expressions; surrounding spaces make the match exact, so ` H2CO ` does not match `HCOOH`.
- Choose the wavelength type that matches your data: vacuum values differ from air values by about 0.03%.
