"""One UTC instant in every time scale."""
TOOL_KEY = "time_converter"
NAME = "basics-time-scales"
SIZE = (1320, 700)


def run(panel, ws, h):
    h.set(panel, "Time(s)", "2024-03-10 22:00:00")
    h.set(panel, "Output scale", "tdb")
    h.set(panel, "Output format", "jd")
    h.set(panel, "Precision", 6)
    h.click(panel, "Convert")
    summary = h.output_text(panel, "Result")
    assert "scale=tdb" in summary, summary
    h.tab(panel, "All scales")
    scales = h.output_text(panel, "All scales")
    assert "0,tt,2024-03-10 22:01:09.184000" in scales, scales
    assert "0,tai,2024-03-10 22:00:37.000000" in scales, scales
