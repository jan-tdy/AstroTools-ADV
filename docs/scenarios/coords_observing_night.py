"""Twilight, astronomical night and Moon for Cordoba, 29 October 2026 (local time = UTC+1)."""
TOOL_KEY = "coord_sunmoon"
NAME = "coords-sunmoon-night"
SIZE = (1280, 960)


def run(panel, ws, h):
    h.set(panel, "Longitude [deg]", "-4.78")
    h.set(panel, "Latitude [deg]", "37.89")
    h.set(panel, "Height", "120 m")
    panel.form.set_value("start", "2026-10-29 12:00")
    panel.form.set_value("offset", 1.0)
    panel.targets.text.setPlainText("10.684 41.269\n83.822 -5.391")
    h.click(panel, "Compute")
    events = h.output_text(panel, "Events")
    assert "Astronomical dusk (Sun at -18 deg),2026-10-29 19:52:15" in events, events
    assert "Astronomical dawn (Sun at -18 deg),2026-10-30 06:13:47" in events, events
    night = h.output_text(panel, "Astronomical night")
    assert "2026-10-29 19:52:15,2026-10-30 06:13:47,10.35" in night, night
    assert "Waning Gibbous" in h.output_text(panel, "Moon phase")
    h.tab(panel, "Sun and Moon altitude")
