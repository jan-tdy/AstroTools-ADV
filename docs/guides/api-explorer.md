---
title: Calling any astropy function
order: 60
lede: Use the API Explorer for a function that has no dedicated page, and keep the code it generates.
---

[API Explorer](../reference/system/api_explorer.md) lists every public astropy function and class. This example sigma-clips a list that contains one gross outlier.

1. Store the data in the workspace under the name `flux`, for instance by creating a table or array with another tool. Here the array is `[1, 2, 3, 4, 100, 5, 6]`.
2. Type `sigma_clip` in the search box and select `astropy.stats.sigma_clip`.
3. In the **Call** tab set `data` to `ws_flux` (workspace objects are `ws_<name>`) and `sigma` to `2`.

![Call tab for sigma_clip](../assets/guides/system-api-explorer-call.png "The Call tab filled in for astropy.stats.sigma_clip.")

4. Press **Run**.

![Result tab](../assets/guides/system-api-explorer-result.png "The Result tab after running sigma_clip.")

The result is a masked array with `mask=[False, False, False, False,  True, False, False]`: only 100 is clipped. The **Docs** tab shows the function's docstring (what `sigma`, `cenfunc` and `maxiters` mean) without leaving the page.

**Copy as Python code** gives `sigma_clip(data=ws_flux, sigma=2)` with the imports, so you can move the call into a script. **Store result** keeps the masked array in the workspace for other tools.

The same result is available on [Sigma Clipping](../reference/analysis/stats_sigmaclip.md) with statistics and a plot; use the API Explorer for functions that have no such page.
