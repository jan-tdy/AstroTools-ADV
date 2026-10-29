"""Bootstrap and jackknife error estimates for the median of 40 values."""
TOOL_KEY = "stats_resampling"
NAME = "analysis-stats-resampling"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "Data").set_text("np.random.default_rng(3).normal(100, 5, 40)")
    h.set(panel, "Statistic", "median")
    h.set(panel, "Random seed", "42")
    h.click(panel, "Run bootstrap + jackknife")
    text = h.output_text(panel, "Result")
    assert "Jackknife resamples      : 40 x 39" in text, text
    h.tab(panel, "Bootstrap distribution")
