"""Match a small target list against a reference catalog by sky position."""
import numpy as np
from astropy.table import Table

TOOL_KEY = "coord_match"
NAME = "coords-crossmatch"
SIZE = (1280, 1100)


def _tables():
    # Reference catalog: six stars around M31's field.
    reference = Table({
        "name": ["HD 1", "HD 2", "HD 3", "HD 4", "HD 5", "HD 6"],
        "RAJ2000": [10.6000, 10.6500, 10.7000, 10.7500, 10.8000, 11.2000],
        "DEJ2000": [41.2000, 41.2500, 41.3000, 41.3500, 41.4000, 41.6000],
        "Vmag": [8.1, 9.4, 10.2, 7.7, 11.0, 9.9],
    })
    # Our detections: three lie within half an arcsecond of a reference star (offsets in
    # arcsec along RA/Dec), one is 6 arcsec off its nearest star, one has no counterpart.
    offsets = [(0.30, -0.20), (-0.40, 0.10), (0.00, 6.00), (0.15, 0.25), (0.0, 0.0)]
    idx = [0, 1, 2, 3]
    ra = [reference["RAJ2000"][i] + dx / 3600 / np.cos(np.deg2rad(reference["DEJ2000"][i]))
          for i, (dx, _) in zip(idx, offsets[:4])]
    dec = [reference["DEJ2000"][i] + dy / 3600 for i, (_, dy) in zip(idx, offsets[:4])]
    ra.append(12.0)
    dec.append(42.0)
    sources = Table({"id": ["s1", "s2", "s3", "s4", "s5"], "ra": ra, "dec": dec,
                     "flux": [120.0, 85.5, 40.2, 310.7, 12.9]})
    return sources, reference


def run(panel, ws, h):
    sources, reference = _tables()
    ws.put("sources", sources)
    ws.put("reference", reference)
    h.set(panel, "Table", "sources", nth=0)
    h.set(panel, "Table", "reference", nth=1)
    h.set(panel, "Limit", "2 arcsec")
    h.click(panel, "Match")
    table = panel.tabs.widget(0).model
    assert list(table._table["matched"]) == [True, True, False, True, False], table._table
    assert abs(table._table["sep_arcsec"][2] - 6.0) < 0.05
    assert "3 within the limit" in h.output_text(panel, "Summary")
