"""Robust statistics: biweight location sits with the bulk of the data, the mean does not."""
from ._analysis_data import CLIP_DATA

TOOL_KEY = "stats_robust"
NAME = "analysis-stats-robust"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "Data").set_text(CLIP_DATA)
    h.click(panel, "Compute")
    text = h.output_text(panel, "Statistics")
    assert "biweight_location      100.2545" in text, text
    h.tab(panel, "Histogram")
