## What it does

Browses `astropy.modeling` models, composes them with operators, edits parameters and constraints, evaluates and plots them and saves the result to the workspace.

## How to use

1. Pick a **Group** (`1D`, `2D`, `Mappings / other`, `Projections`), optionally filter by name in **Filter**, choose a **Model class** and press **Insert class into expression**.
2. In **Model expression** combine models with `+ - * / **`, `|` (compose) and `&` (join); workspace models can be used by name. The default is `Gaussian1D(1, 0, 1) + Const1D(0.1)`.
3. **Build / describe** shows the model. Edit the parameters in the **Parameters** tab (value, fixed, min, max, tied) and press **Apply parameter edits**.
4. **Evaluate and plot** uses the grid **Grid x min/max** (and **Grid y min/max** for 2-D) with **Grid points / axis** and optional **Input unit**. **Render (bounding box)** renders 2-D models.
5. **Save model to workspace** (name in **Workspace name**, default `model`) and **Save inverse to workspace**.
6. **Custom model**: set **Custom: name**, **Custom: formula** (`a*np.sin(b*x) + c`), **Custom: parameters** (`a=1, b=2, c=0`) and **Custom: inputs**, then **Create custom model**.

## Reading the results

For `Gaussian1D(1, 0, 1) + Gaussian1D(0.5, 2.5, 0.4) + Const1D(0.1)`: `CompoundModel`, `submodels=3`, `fittable=True`, `linear=False`, parameters `amplitude_0` ... `amplitude_2`, `stddev` with lower bound 1.1754943508222875e-38 (the default positive bound). `inverse: not available` for sums.

## Tips and limits

- Parameter names carry the index of their submodel (`mean_1`).
- Stored models are the starting point for [1-D fitting](model_fit1d.md).
