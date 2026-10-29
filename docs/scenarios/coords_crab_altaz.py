"""Crab Nebula as seen from Cordoba, Spain, on 29 October 2026 at 21:00 UTC."""
TOOL_KEY = "coord_convert"
NAME = "coords-crab-altaz"


def run(panel, ws, h):
    h.set(panel, "Lines", "83.633 22.0145")
    h.set(panel, "Frame", "AltAz", nth=1)
    h.set(panel, "Obstime", "2026-10-29 21:00", nth=1)
    h.set(panel, "Mode", "Geodetic", nth=1)
    h.set(panel, "Longitude [deg]", "-4.78", nth=1)
    h.set(panel, "Latitude [deg]", "37.89", nth=1)
    h.set(panel, "Height", "120 m", nth=1)
    h.click(panel, "Convert")
    result = h.output_text(panel, "Result")
    print(result)
