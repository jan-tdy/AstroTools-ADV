## What it does

Fetches image cut-outs from [NASA SkyView](https://skyview.gsfc.nasa.gov/), which serves surveys from radio to gamma rays (DSS, 2MASS, SDSS, WISE, GALEX, NVSS and many more) in one interface. Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Download images | **Position** `*`, **Survey** `*`, **Radius**, **Pixels** | FITS images |
| Image URLs | the same four fields | A one-column table `url`; nothing is downloaded |
| List surveys | nothing | A table of survey names and their categories |

1. Run **List surveys** once to see the exact survey names SkyView accepts (`DSS`, `DSS2 Red`, `2MASS-J`, `SDSSg`, ...). The **Survey** drop-down offers common ones and also accepts any name you type.
2. Choose **Download images** and fill in **Position**: a name (`M31`) or coordinates (`10.68 41.27`). The name is passed on unchanged; SkyView resolves it.
3. **Radius** is the half-size of the field (for example `0.5 deg`). Empty uses SkyView's default size for the survey.
4. **Pixels** sets the image size in pixels; 0 uses the default.
5. Press **Run query**. Downloading takes a few seconds per image.
6. Press **Store images/objects in workspace**. A single image is stored under the **Store as** name; several get `_0`, `_1`, ... appended.

## Reading the results

An image query puts nothing in the **Table** tab. The **Info** tab lists each returned FITS file with its HDUs and shapes. The images live in the workspace after you store them: open them in the [FITS](../data/fits.md) page, the [Image viewer](../images/viz_viewer.md) or the [WCS](../images/wcs_inspect.md) tools.

## Tips and limits

- Choosing a survey that does not cover the position returns an error or an empty image set from SkyView.
- Large **Pixels** values and wide fields make slow, large downloads. Start small.
- **Timeout (s)** has no effect on SkyView queries; the astroquery client uses its own.
- Images are retrieved from SkyView's servers; the survey archives behind it (DSS, 2MASS, ...) carry their own acknowledgement requirements.
