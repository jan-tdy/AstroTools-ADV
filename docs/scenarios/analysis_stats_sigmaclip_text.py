"""Sigma clipping: the statistics tab (clipped vs unclipped mean, median, std)."""
from ._analysis_data import CLIP_DATA

TOOL_KEY = "stats_sigmaclip"
NAME = "analysis-stats-sigmaclip-text"
SIZE = (1280, 520)


def run(panel, ws, h):
    h.field(panel, "Data").set_text(CLIP_DATA)
    h.click(panel, "Compute")
    text = h.output_text(panel, "Statistics")
    assert "clipped: 4" in text and "100.1593" in text, text
