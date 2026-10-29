"""Fraction of 'successes' as a function of x, in five bins."""
TOOL_KEY = "stats_binned_binomial"
NAME = "analysis-stats-binned-binomial"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "x values").set_text("np.random.default_rng(4).uniform(0, 10, 400)")
    h.field(panel, "Success (0/1)").set_text(
        "np.random.default_rng(5).uniform(0, 1, 400) < np.random.default_rng(4).uniform(0, 10, 400)/10")
    h.set(panel, "Bins", "5")
    h.click(panel, "Compute")
    csv = h.output_text(panel, "Binned proportions")
    assert csv.count("\n") >= 5, csv
    h.tab(panel, "Plot")
