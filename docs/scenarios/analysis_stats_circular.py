"""Circular statistics for position angles scattered around 40 degrees."""
TOOL_KEY = "stats_circular"
NAME = "analysis-stats-circular"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "Angles").set_text(
        "np.random.default_rng(1).vonmises(np.radians(40), 4, 100) * 180/np.pi % 360")
    h.click(panel, "Compute")
    text = h.output_text(panel, "Statistics")
    assert "circular mean          : 41.00" in text, text
    h.tab(panel, "Polar plot")
