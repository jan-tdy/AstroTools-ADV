## What it does

Plots table columns: scatter, line, error bar and histogram.

## How to use

1. Choose the **Table** and **Kind** (`scatter`, `line`, `errorbar`, `hist`).
2. Choose the **X column**. For all kinds except `hist` also the **Y column**; for `errorbar` the **Y error column**.
3. For `hist`, set **Histogram bins** (default 30).
4. Optional: **Log X**, **Log Y**, **Title**.
5. Press **Plot**. **Save figure...** writes PNG, PDF or SVG.

## Reading the results

The **Plot** tab shows the figure, **Table** the plotted data and **Info** a summary. Axis labels come from the column names.

## Tips and limits

- A log axis cannot show values <= 0; they are not drawn.
- For model fits to the same data use [1D model fitting](../analysis/model_fit1d.md).
