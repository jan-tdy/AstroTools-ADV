"""Astroquery Browser showing the signature and docstring of Simbad.query_region (offline)."""
TOOL_KEY = "astroquery_browser"
NAME = "online-browser-docs"
SIZE = (1280, 820)


def run(panel, ws, h):
    h.set(panel, "Service", "simbad")
    h.set(panel, "Method", "query_region")
    h.tab(panel, "Docs")
