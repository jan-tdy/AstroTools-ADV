"""Model Builder: a compound model evaluated on a grid."""
TOOL_KEY = "model_builder"
NAME = "analysis-model-builder"
SIZE = (1280, 760)


def run(panel, ws, h):
    h.set(panel, "Model expression", "Gaussian1D(1, 0, 1) + Gaussian1D(0.5, 2.5, 0.4) + Const1D(0.1)")
    h.click(panel, "Build / describe")
    assert panel.table.rowCount() == 7
    h.click(panel, "Evaluate and plot")
    h.tab(panel, "Evaluation")
