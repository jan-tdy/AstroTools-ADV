## What it does

Joins two or more workspace `SkyCoord` objects into one.

## How to use

1. Select the objects in the **SkyCoords** list (at least two; the list refreshes when the workspace changes).
2. Set **Result name** (default `combined`).
3. Press **Concatenate**.

## Reading the results

The **Result** tab reports `<name>: N coordinates in <Frame> from <names>`. The new object is stored in the workspace.

## Tips and limits

- Inputs in a different frame are transformed to the frame of the first selected object, so the output frame depends on the selection order. Convert explicitly with [Frame converter](coord_convert.md) if you want control.
- Fewer than two selected gives `Select at least two SkyCoord objects.`
- A single coordinate is accepted as a one-element list.
