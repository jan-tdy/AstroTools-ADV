"""Radio Doppler velocity of an H I line observed at 1400 MHz."""
TOOL_KEY = "unit_converter"
NAME = "basics-unit-converter"
SIZE = (1180, 620)


def run(panel, ws, h):
    h.set(panel, "Value", "1400 MHz")
    h.set(panel, "Convert to", "km/s")
    h.set(panel, "Equivalency", "doppler_radio")
    h.set(panel, "Parameter 1", "1420.405751 MHz")
    h.click(panel, "Convert")
    text = h.output_text(panel, "Result")
    assert "4306.86" in text, text
    assert "Equivalencies: doppler_radio" in text, text
