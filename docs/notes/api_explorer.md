## What it does

Reaches every public astropy function and class through a generated form, for things that have no dedicated page. A tree of the API is on the left, the form and results on the right.

## How to use

1. Type in the search box (`sigma_clip`, `SkyCoord`, `fits.open`) and select an entry in the tree. The **Call** tab shows one field per parameter, with its default and a tooltip.
2. Fill the fields. Values are Python expressions (`2`, `[1, 2, 3]`, `u.deg`); `u`, `np` and `astropy` names are available.
3. Workspace objects are used as `ws_<name>`, e.g. `ws_flux` for an object called `flux`.
4. Press **Run**. **Store as** names the result (empty: a name is chosen); **Store result** keeps the last result in the workspace. **Copy as Python code** copies the equivalent script, e.g. `sigma_clip(data=ws_flux, sigma=2)`.
5. Tick the GUI-thread option for code that draws plots; the window blocks while it runs.
6. The tabs: **Call**, **Docs** (the docstring of the selected function), **Result**, **Table** (table results), **Figure**.

## Reading the results

Calling `astropy.stats.sigma_clip` with `data=ws_flux` (`[1, 2, 3, 4, 100, 5, 6]`) and `sigma=2` returns a masked array whose mask is `[False, False, False, False, True, False, False]`: only the value 100 is clipped. The **Result** tab prints the value and, when the call stored it, `Stored in workspace as '...'.`

## Tips and limits

- The page lists what astropy exposes; it cannot make a parameter that needs a Python object easier. Create the object in another page, store it, and refer to it as `ws_<name>`.
- Argument errors are reported in **Result** with the original traceback.
- Dedicated pages ([Sigma clipping](../analysis/stats_sigmaclip.md) for example) show more.
- See [API Explorer guide](../../guides/api-explorer.md).
