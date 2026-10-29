"""Bayesian blocks on event times: a burst between t = 50 and t = 60."""
TOOL_KEY = "stats_blocks"
NAME = "analysis-stats-blocks"
SIZE = (1280, 700)

EVENTS = ("np.concatenate([np.random.default_rng(1).uniform(0, 50, 100),"
          " np.random.default_rng(2).uniform(50, 60, 200),"
          " np.random.default_rng(3).uniform(60, 100, 100)])")


def run(panel, ws, h):
    h.field(panel, "t (times / values)").set_text(EVENTS)
    h.click(panel, "Compute blocks")
    text = h.output_text(panel, "Edges")
    assert text.startswith("3 block(s)"), text
    h.tab(panel, "Blocks")
