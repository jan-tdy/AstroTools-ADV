"""Main-window screenshot for the home page: an observing night for two targets."""
TOOL_KEY = "coord_visibility"
NAME = "hero"
FULL_WINDOW = True


def run(panel, ws, h):
    h.set(panel, "Longitude [deg]", "-4.78")
    h.set(panel, "Latitude [deg]", "37.89")
    h.set(panel, "Height", "120 m")
    h.set(panel, "Lines", "10.684 41.269\n83.822 -5.391")
    h.set(panel, "Start (UTC)", "2026-10-29 18:00")
    h.click(panel, "Compute")
    h.tab(panel, "Altitude")
