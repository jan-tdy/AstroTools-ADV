"""Splines & Polynomials: a cubic smoothing spline with its first derivative."""
TOOL_KEY = "model_curves"
NAME = "analysis-model-curves"
SIZE = (1280, 760)


def run(panel, ws, h):
    h.field(panel, "x").set_text("np.linspace(0, 10, 40)")
    h.field(panel, "y").set_text("np.sin(np.linspace(0, 10, 40)) + np.random.default_rng(5).normal(0, 0.1, 40)")
    h.set(panel, "Method", "Spline: smoothing")
    h.set(panel, "Smoothing s", "0.4")
    h.set(panel, "Derivative order", 1)
    h.click(panel, "Fit / interpolate")
    h.tab(panel, "Curve")
    assert panel.model is not None
