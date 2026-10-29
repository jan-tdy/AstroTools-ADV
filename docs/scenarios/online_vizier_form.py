"""VizieR panel with a box region query filled in (not executed: it needs the network)."""
TOOL_KEY = "aq_vizier"
NAME = "online-vizier-form"
SIZE = (1280, 760)


def run(panel, ws, h):
    panel.select_query("region")
    panel.set_values(coord="10.68 41.27", radius="", width="20 arcmin", height="10 arcmin",
                     catalog="I/239/hip_main", columns="*", filters="Vmag=<9", rows=25)
