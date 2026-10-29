"""MkDocs hooks.

* Keep literate-nav's ``SUMMARY.md`` files out of the published site.
* Give pages that only declare ``title:`` / ``lede:`` in their front matter a heading and
  a lead paragraph, so hand-written pages do not repeat them in the body.
"""
import re

_H1 = re.compile(r"^# ", re.M)


def on_nav(nav, config, files):  # noqa: ARG001 - MkDocs hook signature
    for f in [f for f in files if f.src_uri.rsplit("/", 1)[-1] == "SUMMARY.md"]:
        files.remove(f)
    return nav


def on_page_markdown(markdown, page, config, files):  # noqa: ARG001
    title = page.meta.get("title")
    if not title or _H1.search(markdown):
        return markdown
    lede = page.meta.get("lede")
    head = f"# {title}\n\n"
    if lede:
        head += f"{lede}\n{{ .lede }}\n\n"
    return head + markdown
