"""Barnard's Star moved from J2000 to J2025 with its proper motion."""
TOOL_KEY = "coord_motion"
NAME = "coords-proper-motion"
SIZE = (1280, 1000)


def run(panel, ws, h):
    # The page opens pre-filled with Barnard's Star (distance 1.83 pc, proper motion
    # -798.58 / +10328.12 mas/yr, radial velocity -110.51 km/s, epoch J2000).
    h.set(panel, "New epoch", "J2025.0")
    h.click(panel, "Apply space motion")
    table = h.output_text(panel, "Positions")
    assert "269.4444265" in table and "4.761833927" in table and "259.37" in table, table
    assert "moved" in ws
