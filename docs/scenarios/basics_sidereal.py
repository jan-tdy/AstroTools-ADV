"""Local sidereal time and barycentric correction for one observing session."""
TOOL_KEY = "sidereal_light_time"
NAME = "basics-sidereal"
SIZE = (1360, 700)


def run(panel, ws, h):
    h.set(panel, "Time(s)", "2024-03-10 22:00:00\n2024-03-10 23:00:00\n2024-03-11 00:00:00")
    h.set(panel, "Longitude", "-4.78")
    h.set(panel, "Latitude", "37.89")
    h.set(panel, "Height", "120 m")
    h.set(panel, "Kind", "mean")
    h.set(panel, "Light travel time", True)
    h.set(panel, "Source", "12.5 -45.2")
    h.set(panel, "Correction", "barycentric")
    h.click(panel, "Compute")
    text = h.output_text(panel, "Result")
    assert "08:57:08.5853" in text, text
    assert "-350.44" in text, text
    h.tab(panel, "Table")
