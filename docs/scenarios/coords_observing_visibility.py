"""Altitude of M31 and the Orion Nebula from Cordoba on the night of 29 October 2026."""
TOOL_KEY = "coord_visibility"
NAME = "coords-visibility-altitude"
SIZE = (1280, 960)


def run(panel, ws, h):
    h.set(panel, "Longitude [deg]", "-4.78")
    h.set(panel, "Latitude [deg]", "37.89")
    h.set(panel, "Height", "120 m")
    h.set(panel, "Lines", "10.684 41.269\n83.822 -5.391")
    h.set(panel, "Start (UTC)", "2026-10-29 18:00")
    h.click(panel, "Compute")
    events = h.output_text(panel, "Rise / transit / set")
    assert "2026-10-29 22:30:17" in events and "86.47" in events, events
    assert "2026-10-30 03:21:53" in events and "46.73" in events, events
    h.tab(panel, "Altitude")
