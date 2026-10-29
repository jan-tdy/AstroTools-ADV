"""Binomial confidence intervals for three measured fractions, all four methods."""
TOOL_KEY = "stats_binomial"
NAME = "analysis-stats-binomial"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.set(panel, "k (successes)", "0, 3, 10, 50")
    h.set(panel, "n (trials)", "10, 10, 20, 100")
    h.set(panel, "Confidence level", 0.95)
    h.click(panel, "Compute")
    assert "binomial_intervals" in ws.names()
    h.tab(panel, "Intervals")
