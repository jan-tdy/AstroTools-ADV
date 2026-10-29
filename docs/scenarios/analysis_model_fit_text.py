"""Fit a Gaussian line on a continuum with 1-sigma uncertainties (text result)."""
from ._analysis_data import GAUSS_X, GAUSS_Y

TOOL_KEY = "model_fit1d"
NAME = "analysis-model-fit-text"
SIZE = (1280, 760)


def run(panel, ws, h):
    h.field(panel, "x").set_text(GAUSS_X)
    h.field(panel, "y").set_text(GAUSS_Y)
    h.field(panel, "y uncertainty (sigma)").set_text("np.full(101, 0.1)")
    h.set(panel, "Initial model", "Gaussian1D(2, 0, 1) + Const1D(0.4)")
    h.click(panel, "Fit")
    text = h.output_text(panel, "Fit result")
    assert "points used: 101" in text and "reduced chi2" in text, text
    fitted = panel._result["fit"]
    assert abs(fitted.amplitude_0.value - 3.0) < 0.1
    assert abs(fitted.mean_0.value - 0.7) < 0.05
    assert abs(fitted.stddev_0.value - 1.2) < 0.05
    assert abs(fitted.amplitude_1.value - 0.5) < 0.05
