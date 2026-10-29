"""API Explorer: the Call tab filled in for astropy.stats.sigma_clip."""
import numpy as np

TOOL_KEY = "api_explorer"
NAME = "system-api-explorer-call"
SIZE = (1360, 720)


def run(panel, ws, h):
    from astrotools_adv.core import tasks

    tasks.wait_all()
    ws.put("flux", np.array([1.0, 2.0, 3.0, 4.0, 100.0, 5.0, 6.0]))
    panel.search.setText("sigma_clip")
    assert "astropy.stats.sigma_clip" in panel.visible_qualnames()
    panel.select_qualname("astropy.stats.sigma_clip")
    panel.search.setText("sigma_clip")
    panel.call_form.edits["data"].setText("ws_flux")
    panel.call_form.edits["sigma"].setText("2")
    panel.tabs.setCurrentIndex(panel.TAB_CALL)
    assert "sigma_clip(data=ws_flux, sigma=2)" in panel.python_code()
