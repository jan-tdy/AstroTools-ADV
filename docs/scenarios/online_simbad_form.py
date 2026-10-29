"""SIMBAD panel with a region query filled in (not executed: it needs the network)."""
TOOL_KEY = "aq_simbad"
NAME = "online-simbad-form"
SIZE = (1280, 760)


def run(panel, ws, h):
    panel.select_query("region")
    panel.set_values(coord="10.68 41.27", radius="5 arcmin", votable="otype, sp_type", rows=50)
