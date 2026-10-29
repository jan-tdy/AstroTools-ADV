"""Crab Nebula: ICRS to the old FK4 B1950 system, in sexagesimal form."""
TOOL_KEY = "coord_convert"
NAME = "coords-crab-b1950"


def run(panel, ws, h):
    h.set(panel, "Lines", "83.633 22.0145")
    h.set(panel, "Frame", "FK4", nth=1)
    h.set(panel, "Equinox", "B1950", nth=1)
    h.set(panel, "Angle format", "hmsdms")
    h.set(panel, "Precision", 2)
    h.click(panel, "Convert")
    result = h.output_text(panel, "Result")
    assert "05:31:31.38" in result and "+21:58:54.51" in result, result
    assert "equinox=B1950.000" in h.output_text(panel, "Info")
