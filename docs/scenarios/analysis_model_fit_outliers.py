"""Sigma-clipped fit: spikes are marked with red crosses and excluded."""
from ._analysis_data import GAUSS_X, GAUSS_Y_SPIKES

TOOL_KEY = "model_fit1d"
NAME = "analysis-model-fit-outliers"
SIZE = (1280, 760)


def run(panel, ws, h):
    h.field(panel, "x").set_text(GAUSS_X)
    h.field(panel, "y").set_text(GAUSS_Y_SPIKES)
    h.set(panel, "Initial model", "Gaussian1D(2, 0, 1) + Const1D(0.4)")
    h.set(panel, "Sigma-clip outliers", True)
    h.click(panel, "Fit")
    h.tab(panel, "Fit")
    r = panel._result
    assert int(r["mask"].sum()) == 4, int(r["mask"].sum())
    assert abs(r["fit"].amplitude_0.value - 3.0) < 0.1
