"""Ripley's K and L for a clustered point pattern, with an explicit study region."""
TOOL_KEY = "stats_ripley"
NAME = "analysis-stats-ripley"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "x").set_text(
        "np.clip(np.repeat(np.random.default_rng(1).uniform(0.1, 0.9, 10), 15)"
        " + np.random.default_rng(2).normal(0, 0.02, 150), 0, 1)")
    h.field(panel, "y").set_text(
        "np.clip(np.repeat(np.random.default_rng(3).uniform(0.1, 0.9, 10), 15)"
        " + np.random.default_rng(4).normal(0, 0.02, 150), 0, 1)")
    h.set(panel, "Region x0,x1,y0,y1", "0, 1, 0, 1")
    h.set(panel, "Edge correction", "ohser")
    h.click(panel, "Compute K and L")
    text = h.output_text(panel, "Summary")
    assert "150 points" in text and "n/a" not in text, text
    h.tab(panel, "K / L")
