"""Sigma clipping: kept and clipped values, with the clip bounds."""
from ._analysis_data import CLIP_DATA

TOOL_KEY = "stats_sigmaclip"
NAME = "analysis-stats-sigmaclip"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.field(panel, "Data").set_text(CLIP_DATA)
    h.click(panel, "Compute")
    text = h.output_text(panel, "Statistics")
    assert "Values: 203" in text and "clipped: 4" in text, text
    h.tab(panel, "Plot")
