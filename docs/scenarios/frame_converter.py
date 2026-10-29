"""Transform M31 from ICRS to Galactic coordinates."""
TOOL_KEY = "coord_convert"
NAME = "frame-converter"


def run(panel, ws, h):
    h.set(panel, "Lines", "10.684 41.269")
    h.set(panel, "Frame", "ICRS", nth=0)
    h.set(panel, "Frame", "Galactic", nth=1)
    h.click(panel, "Convert")
    text = h.output_text(panel, "Result")
    assert "121.17" in text and "-21.57" in text, text
