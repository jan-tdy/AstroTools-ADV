"""MkDocs hook: keep literate-nav's SUMMARY.md files out of the published site."""


def on_nav(nav, config, files):  # noqa: ARG001 - MkDocs hook signature
    for f in [f for f in files if f.src_uri.rsplit("/", 1)[-1] == "SUMMARY.md"]:
        files.remove(f)
    return nav
