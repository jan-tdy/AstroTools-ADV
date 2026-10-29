"""Bayesian blocks on the same data: few, uneven bins."""
from ._analysis_data import BIMODAL

TOOL_KEY = "stats_histogram"
NAME = "analysis-stats-hist-blocks"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "Data").set_text(BIMODAL)
    h.set(panel, "Binning", "blocks")
    h.click(panel, "Compute")
    assert " bins, 550 values in range" in h.output_text(panel, "Summary")
    h.tab(panel, "Histogram")
