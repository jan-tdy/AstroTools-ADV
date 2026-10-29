"""Signal-to-noise against exposure time for a faint source."""
TOOL_KEY = "stats_snr"
NAME = "analysis-stats-snr"
SIZE = (1280, 700)


def run(panel, ws, h):
    h.click(panel, "Compute")
    csv = h.output_text(panel, "S/N")
    assert csv.splitlines()[1].startswith("1,0.4335"), csv
    h.tab(panel, "S/N vs time")
