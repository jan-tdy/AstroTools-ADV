"""Executable documentation scenarios.

Each module defines::

    TOOL_KEY = "coord_convert"       # registry key of the tool page to drive
    NAME = "frame-converter"         # output file name: img/guides/<NAME>.png

    def run(panel, ws, helpers) -> None:
        ...  # fill fields, press buttons, leave the panel in the state to photograph

``helpers`` is :class:`tools.scenario_helpers.Helpers`. A scenario that raises
fails the documentation build, so every guide step is exercised against the
real application.
"""
