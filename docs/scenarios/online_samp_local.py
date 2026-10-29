"""SAMP panel with the built-in hub started and this application connected to it.

Everything here is local: the hub listens on 127.0.0.1 and the lockfile is private to
the scenario, so no real SAMP application on the machine is involved.
"""
import shutil
import tempfile
from pathlib import Path

TOOL_KEY = "samp"
NAME = "online-samp-local"
SIZE = (1280, 800)


def run(panel, ws, h):
    folder = Path(tempfile.gettempdir()) / "astrotools-docs-samp"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    lock = folder / "samp-hub"
    h.set(panel, "Lockfile", str(lock))
    h.click(panel, "Start hub")
    h.click(panel, "Connect client")
    h.tab(panel, "Clients")
