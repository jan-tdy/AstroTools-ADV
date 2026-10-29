"""Filter the constants table and compute a mass ratio."""
TOOL_KEY = "constants"
NAME = "basics-constants"
SIZE = (1300, 640)


def run(panel, ws, h):
    h.set(panel, "Filter", "IAU")
    h.click(panel, "List constants")
    table = h.output_text(panel, "Constants")
    assert "Nominal solar mass parameter,GM_sun" in table, table
    assert "IAU 2015 Resolution B 3" in table, table
    h.set(panel, "Calculator", "(const.M_sun / const.M_earth).decompose()")
    h.click(panel, "Evaluate")
    result = h.output_text(panel, "Calculator")
    assert "332946" in result, result
    h.tab(panel, "Constants")
