## What it does

Converts a quantity to another unit, optionally through an astropy equivalency (wavelength to frequency, Doppler conventions and so on), and shows its SI and CGS forms and physical type.

## How to use

1. Enter **Value** as a quantity: `100 km/s`, `2*u.pc`, or an array such as `np.linspace(1, 5, 5) * u.m`.
2. Enter **Convert to** (default `m/s`). Empty shows only the SI and CGS forms.
3. Choose an **Equivalency** when the units are of different kinds: `spectral`, `spectral_density`, `doppler_radio`, `doppler_optical`, `doppler_relativistic`. Equivalencies that need values use **Parameter 1** / **Parameter 2**; the tooltips say what each means, or `Not used by this equivalency`.
4. **Always-on** adds parameter-free equivalencies, comma separated (for example `spectral, parallax`).
5. Press **Convert**; **Store result in workspace** keeps the quantity under **Store as** (default `converted`).

## Reading the results

`100 km/s` to `m/s` gives `Result: 100000.0 m / s`, `CGS: 10000000.0 cm / s`, `Physical type: speed/velocity`. With **Equivalency** `spectral`, `500 nm` to `GHz` gives `599584.916 GHz`, physical type frequency.

## Tips and limits

- Without the right equivalency a conversion between unlike units is refused with a message from astropy naming both units.
- The Doppler equivalencies and `spectral_density` need **Parameter 1** (a rest frequency or wavelength, or the wavelength/frequency of the density); a missing one gives `<name> needs parameter 1: ...`.
- Custom units from [Unit explorer](unit_explorer.md) work here too.
