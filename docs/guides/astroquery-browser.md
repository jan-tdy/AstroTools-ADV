---
title: Using services without a dedicated page
order: 52
lede: Read the documentation of any astroquery method offline, then call it from a generated form.
---

[Astroquery Browser](../reference/online/astroquery_browser.md) reaches every astroquery service. Opening it, and reading documentation, does not contact any server.

1. **Service**: `simbad`. **Method**: `query_region`.
2. Open the **Docs** tab.

![Docs tab for Simbad.query_region](../assets/guides/online-browser-docs.png "The signature and docstring of Simbad.query_region.")

The tab shows the signature, `query_region(coordinates, radius=<Quantity 2. arcmin>, *, criteria=None, ...)`, and the parameter descriptions: `coordinates` is an identifier or an `astropy.coordinates` object, `radius` defaults to 2 arcmin, `criteria` is an ADQL condition, and `get_query_payload=True` returns the request instead of running it.

3. Fill the arguments of the form. Values are Python expressions, so a radius can be `5*u.arcmin`.
4. Untick **Offline mode** and press **Run**.

Table results appear in **Table** and can be stored; other results and errors appear in **Info**. The **Config** tab shows the service's configuration items. For SIMBAD and VizieR prefer their [dedicated pages](../reference/online/index.md), which have forms for every query.
