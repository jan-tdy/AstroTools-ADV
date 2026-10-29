"""Distances, magnitudes and a constant in one script."""
TOOL_KEY = "quantity_calculator"
NAME = "basics-quantity-calculator"
SIZE = (1180, 700)

SCRIPT = """# one expression per line; 'name = expr' assigns
d = 10 * u.pc
d.to(u.lyr)
m = Magnitude(5 * u.mag(u.AB))
m.to(u.Jy)
v_esc = sqrt(2 * const.G * 1 * u.Msun / (1 * u.AU))
v_esc.to(u.km / u.s)"""


def run(panel, ws, h):
    h.set(panel, "Expressions", SCRIPT)
    h.click(panel, "Evaluate")
    text = h.output_text(panel, "Result")
    assert "32.6156" in text, text
    assert "36.3078" in text, text
    assert "42.12" in text, text
