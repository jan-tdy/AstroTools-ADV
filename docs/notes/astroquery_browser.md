## What it does

Calls any method of any astroquery service from a generated form, for services without a dedicated page, and edits a service's configuration. Results come from remote services; see [the category overview](index.md).

## How to use

1. Choose the **Service** (any astroquery package, e.g. `simbad`, `alma`, `esa.hubble`) and the **Object** (the class inside it) and **Method**.
2. The form below shows the arguments of the method with their defaults. Fill them as Python values.
3. Read the **Docs** tab for the method's signature and docstring before you run it. It is built from the class, so no network is used.
4. Press **Run**. The **Table** tab shows a returned table; **Info** shows other results and errors; **Config** shows the configuration items of the service.
5. **Store table in workspace**, **Store images/objects in workspace** and **Save table to file...** keep results.

## Reading the results

The **Docs** tab for `Simbad.query_region` begins with its signature (`query_region(coordinates, radius=<Quantity 2. arcmin>, *, criteria=None, ...)`) followed by the parameter descriptions.

## Tips and limits

- Prefer the dedicated pages ([SIMBAD](aq_simbad.md), [VizieR](aq_vizier.md)...) when they exist.
- Opening the browser does not contact any server; only **Run** does.
- Offline mode and **Timeout (s)** work as on the other online pages; **Timeout (s)** is passed on when the service supports it.
- Some services (the experimental ALFALFA, for example) print warnings.
