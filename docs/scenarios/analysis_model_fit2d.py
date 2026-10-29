"""Image fitting: a noisy elliptical Gaussian star on a flat background."""
import numpy as np
from astropy.modeling import models

TOOL_KEY = "model_fit2d"
NAME = "analysis-model-fit2d"
SIZE = (1380, 640)


def run(panel, ws, h):
    yy, xx = np.mgrid[:60, :80]
    star = models.Gaussian2D(50, 31.3, 24.6, 4.0, 2.5, theta=0.4)
    ws.put("star", star(xx, yy) + 10 + np.random.default_rng(3).normal(0, 1, xx.shape))
    h.set(panel, "Image", "star")
    h.set(panel, "Initial model", "Gaussian2D(40, 30, 25, 3, 3, theta=0.3) + Const2D(8)")
    h.click(panel, "Fit")
    h.tab(panel, "Image / model / residual")
    fit = panel._result["fit"]
    assert abs(fit.x_mean_0.value - 31.3) < 0.1 and abs(fit.y_mean_0.value - 24.6) < 0.1
    assert abs(fit.amplitude_1.value - 10.0) < 0.1
