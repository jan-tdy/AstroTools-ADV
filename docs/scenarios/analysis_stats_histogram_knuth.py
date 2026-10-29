"""Knuth's rule on two overlapping populations."""
from ._analysis_data import BIMODAL

TOOL_KEY = "stats_histogram"
NAME = "analysis-stats-hist-knuth"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "Data").set_text(BIMODAL)
    h.set(panel, "Binning", "knuth")
    h.click(panel, "Compute")
    assert "bin width (knuth)" in h.output_text(panel, "Summary")
    h.tab(panel, "Histogram")
