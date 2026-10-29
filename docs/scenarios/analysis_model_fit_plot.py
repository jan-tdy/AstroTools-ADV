"""Fit plot: data with error bars, initial and fitted model, residuals."""
from ._analysis_data import GAUSS_X, GAUSS_Y

TOOL_KEY = "model_fit1d"
NAME = "analysis-model-fit-plot"
SIZE = (1280, 760)


def run(panel, ws, h):
    h.field(panel, "x").set_text(GAUSS_X)
    h.field(panel, "y").set_text(GAUSS_Y)
    h.field(panel, "y uncertainty (sigma)").set_text("np.full(101, 0.1)")
    h.set(panel, "Initial model", "Gaussian1D(2, 0, 1) + Const1D(0.4)")
    h.click(panel, "Fit")
    h.tab(panel, "Fit")
    assert panel._result is not None and panel._result["stats"]["n_used"] == 101
