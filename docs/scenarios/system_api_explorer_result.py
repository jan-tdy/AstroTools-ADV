"""API Explorer: the Result tab after running astropy.stats.sigma_clip."""
import numpy as np

TOOL_KEY = "api_explorer"
NAME = "system-api-explorer-result"
SIZE = (1360, 560)


def run(panel, ws, h):
    from astrotools_adv.core import tasks

    tasks.wait_all()
    ws.put("flux", np.array([1.0, 2.0, 3.0, 4.0, 100.0, 5.0, 6.0]))
    panel.select_qualname("astropy.stats.sigma_clip")
    panel.call_form.edits["data"].setText("ws_flux")
    panel.call_form.edits["sigma"].setText("2")
    panel.on_run()
    text = panel.result.toPlainText()
    assert "mask=[False, False, False, False,  True, False, False]" in text, text
    panel.tabs.setCurrentIndex(panel.TAB_RESULT)
