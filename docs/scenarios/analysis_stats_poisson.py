"""Poisson intervals for small counts with the frequentist-confidence method."""
TOOL_KEY = "stats_poisson"
NAME = "analysis-stats-poisson"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.set(panel, "Counts", "0 1 5 20 100")
    h.set(panel, "Interval", "frequentist-confidence")
    h.click(panel, "Compute")
    csv = h.output_text(panel, "Intervals")
    assert "0,0,1.84" in csv, csv
    h.tab(panel, "Plot")
