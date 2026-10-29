"""astropy.io.ascii, astropy.io.votable and astropy.io.misc (HDF5, Parquet, YAML, ASDF)."""
from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Optional, Tuple

from astropy.io import ascii as aascii
from astropy.io import registry, votable
from astropy.table import Table

from ..core.parsing import ParseError, parse_int
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace
from .table_tools import (
    OPTIONAL_DEPS, PathEdit, Section, capture_warnings, check_optional_format, display_table,
    module_available, need, parse_kwargs, split_names, table_formats,
)

CATEGORY = "Data"
PREVIEW_BYTES = 64 * 1024
VOTABLE_FORMATS = ["tabledata", "binary", "binary2"]
DEPENDENCIES = [  # (import name, pip name, what it enables)
    ("h5py", "h5py", "HDF5 tables (Table.read/write format='hdf5')"),
    ("pyarrow", "pyarrow", "Parquet tables (format='parquet')"),
    ("asdf", "asdf", "ASDF object files"),
    ("yaml", "pyyaml", "astropy YAML object serialization"),
    ("pandas", "pandas", "Table.to_pandas / from_pandas, pandas.* formats"),
    ("bs4", "beautifulsoup4", "Reading HTML tables (ascii.html)"),
    ("lxml", "lxml", "Faster/more tolerant HTML & XML parsing"),
]


# --------------------------------------------------------------------------- #
# Format registry helpers
# --------------------------------------------------------------------------- #
def ascii_formats(write: bool = False) -> List[str]:
    """Registered ``astropy.io.ascii`` formats (without the ``ascii.`` prefix)."""
    return sorted(f[6:] for f in table_formats(write) if f.startswith("ascii."))


def formats_table() -> Table:
    """All registered Table I/O formats with their optional-dependency status."""
    fmts = registry.get_formats(Table)
    out = Table()
    out["Format"] = [str(f) for f in fmts["Format"]]
    out["Read"] = [str(f).strip() for f in fmts["Read"]]
    out["Write"] = [str(f).strip() for f in fmts["Write"]]
    out["Auto-identify"] = [str(f).strip() for f in fmts["Auto-identify"]]
    out["Deprecated"] = [str(f).strip() for f in fmts["Deprecated"]]
    requires, available = [], []
    for fmt in out["Format"]:
        dep = next((d for p, d in OPTIONAL_DEPS.items() if fmt == p or fmt.startswith(p + ".")),
                   "")
        requires.append(dep)
        available.append("yes" if not dep or module_available(dep) else "NO")
    out["Requires"] = requires
    out["Available"] = available
    return out


def dependency_table() -> Table:
    return Table({
        "Package": [d[1] for d in DEPENDENCIES],
        "Installed": ["yes" if module_available(d[0]) else "no" for d in DEPENDENCIES],
        "Enables": [d[2] for d in DEPENDENCIES],
    })


# --------------------------------------------------------------------------- #
# ASCII
# --------------------------------------------------------------------------- #
def parse_fill_values(text: str) -> List[Tuple[str, str]]:
    """``'NA:0; --:-1'`` -> ``[('NA', '0'), ('--', '-1')]`` (replace text by value)."""
    pairs = []
    for part in (text or "").replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        old, sep, new = part.rpartition(":")
        if not sep or not old:
            raise ParseError(f"Bad fill value {part!r}; expected text:replacement, e.g. NA:0")
        pairs.append((old.strip(), new.strip()))
    return pairs


def parse_formats(text: str) -> Dict[str, str]:
    """``'a=%.2f; b=%.1e'`` -> ``{'a': '%.2f', 'b': '%.1e'}`` (column output formats)."""
    out = {}
    for part in (text or "").replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        name, sep, fmt = part.partition("=")
        if not sep or not name.strip() or not fmt.strip():
            raise ParseError(f"Bad column format {part!r}; expected name=%.3f")
        out[name.strip()] = fmt.strip()
    return out


def read_preview(path: str, limit: int = PREVIEW_BYTES) -> str:
    with open(need(path, "a file path"), "rb") as fh:
        raw = fh.read(limit + 1)
    text = raw[:limit].decode("utf-8", "replace")
    return text + ("\n... (truncated)" if len(raw) > limit else "")


def ascii_read(path: str, fmt: str = "auto", guess: bool = True, delimiter: str = "",
               header_start: str = "", data_start: str = "", data_end: str = "",
               names: str = "", comment: str = "", quotechar: str = "", fill_values: str = "",
               extra: Optional[Dict[str, Any]] = None) -> Table:
    """``astropy.io.ascii.read`` with GUI-style text options (blank = default)."""
    path = need(path, "a file path")
    kw: Dict[str, Any] = dict(extra or {})
    if fmt and fmt != "auto":
        kw["format"] = fmt
        kw["guess"] = False
    else:
        kw["guess"] = guess
    if delimiter != "":
        kw["delimiter"] = delimiter.replace("\\t", "\t")
    for key, val in (("header_start", header_start), ("data_start", data_start),
                     ("data_end", data_end)):
        if val.strip():
            kw[key] = parse_int(val, key)
    if names.strip():
        kw["names"] = split_names(names)
    if comment.strip():
        kw["comment"] = comment.strip()
    if quotechar.strip():
        kw["quotechar"] = quotechar.strip()
    if fill_values.strip():
        kw["fill_values"] = parse_fill_values(fill_values)
    return aascii.read(path, **kw)


def ascii_write(table: Table, fmt: str = "ecsv", path: str = "", overwrite: bool = False,
                delimiter: str = "", formats: str = "", include: str = "", exclude: str = "",
                fill_values: str = "", comment: str = "",
                extra: Optional[Dict[str, Any]] = None) -> str:
    """Write ``table``; returns the text (``path`` blank) or the written path."""
    kw: Dict[str, Any] = dict(extra or {})
    if delimiter != "":
        kw["delimiter"] = delimiter.replace("\\t", "\t")
    if formats.strip():
        kw["formats"] = parse_formats(formats)
    if include.strip():
        kw["include_names"] = split_names(include)
    if exclude.strip():
        kw["exclude_names"] = split_names(exclude)
    if fill_values.strip():
        kw["fill_values"] = parse_fill_values(fill_values)
    if comment.strip():
        kw["comment"] = comment.strip()
    if fmt and fmt != "auto":
        kw["format"] = fmt
    if path.strip():
        aascii.write(table, path.strip(), overwrite=overwrite, **kw)
        return path.strip()
    buf = io.StringIO()
    aascii.write(table, buf, **kw)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# VOTable
# --------------------------------------------------------------------------- #
def _s(value: Any) -> str:
    return "" if value is None else str(value)


def votable_tables(vot: Any) -> List[Any]:
    return list(vot.iter_tables())


def describe_votable(vot: Any) -> str:
    lines = [f"VOTable version {vot.version}"]
    if vot.description:
        lines.append(f"description: {vot.description}")
    for info in vot.infos:
        lines.append(f"INFO {info.name} = {info.value}")
    for p in vot.params:
        lines.append(f"PARAM {p.name} = {p.value} {_s(p.unit)}")
    n = 0
    for r, resource in enumerate(vot.resources):
        lines.append(f"RESOURCE[{r}] name={_s(resource.name)!r} type={resource.type}")
        for info in resource.infos:
            lines.append(f"  INFO {info.name} = {info.value}")
        for p in resource.params:
            lines.append(f"  PARAM {p.name} = {p.value} {_s(p.unit)}")
        for tbl in resource.tables:
            rows = tbl.nrows if tbl.nrows is not None else len(tbl.array)
            lines.append(f"  TABLE[{n}] name={_s(tbl.name)!r} ID={_s(tbl.ID)!r} "
                         f"rows={rows} fields={len(tbl.fields)} params={len(tbl.params)}")
            if tbl.description:
                lines.append(f"    description: {tbl.description}")
            for g in tbl.groups:
                lines.append(f"    GROUP {_s(g.name)!r} ID={_s(g.ID)!r}")
            n += 1
    if n == 0:
        lines.append("(no tables)")
    return "\n".join(lines)


def fields_table(tbl: Any) -> Table:
    """FIELD attributes of a VOTable ``TableElement``."""
    keys = ["ID", "name", "datatype", "unit", "ucd", "utype", "arraysize", "width", "precision",
            "ref", "description"]
    cols = {k: [_s(getattr(f, k, "")) for f in tbl.fields] for k in keys}
    return Table(cols)


def params_table(tbl: Any) -> Table:
    keys = ["ID", "name", "datatype", "value", "unit", "ucd", "utype", "arraysize"]
    return Table({k: [_s(getattr(p, k, "")) for p in tbl.params] for k in keys})


def votable_to_table(vot: Any, index: int = 0) -> Table:
    tables = votable_tables(vot)
    if not tables:
        raise ParseError("The VOTable contains no tables.")
    if not 0 <= index < len(tables):
        raise ParseError(f"Table index {index} out of range (0..{len(tables) - 1}).")
    return tables[index].to_table(use_names_over_ids=True)


def validate_votable(path: str) -> Tuple[bool, str]:
    path = need(path, "a file path")
    buf = io.StringIO()
    try:
        ok = votable.validate(path, output=buf)
    except (OSError, ValueError) as exc:  # not even well-formed XML
        return False, f"{buf.getvalue()}{exc}"
    return bool(ok), buf.getvalue()


def write_votable(table: Table, path: str, fmt: str = "tabledata", overwrite: bool = False) -> str:
    path = need(path, "an output path")
    if os.path.exists(path) and not overwrite:
        raise ParseError(f"{path} exists; tick 'Overwrite' to replace it.")
    if fmt not in VOTABLE_FORMATS:
        raise ParseError(f"Unknown VOTable serialization {fmt!r}.")
    votable.writeto(votable.from_table(table), path, tabledata_format=fmt)
    return path


# --------------------------------------------------------------------------- #
# YAML / ASDF object serialization
# --------------------------------------------------------------------------- #
def yaml_dump(obj: Any) -> str:
    from astropy.io.misc import yaml as ayaml
    return ayaml.dump(obj)


def yaml_load(text: str) -> Any:
    from astropy.io.misc import yaml as ayaml
    try:
        return ayaml.load(need(text, "YAML text"))
    except Exception as exc:  # noqa: BLE001 - yaml raises many parser/constructor types
        raise ParseError(f"Cannot load YAML: {exc}") from None


def asdf_write(obj: Any, path: str, overwrite: bool = False) -> str:
    check_optional_format("asdf")
    import asdf
    path = need(path, "an output path")
    if os.path.exists(path) and not overwrite:
        raise ParseError(f"{path} exists; tick 'Overwrite' to replace it.")
    asdf.AsdfFile({"object": obj}).write_to(path)
    return path


def asdf_read(path: str) -> Any:
    check_optional_format("asdf")
    import asdf
    with asdf.open(need(path, "a file path"), lazy_load=False) as af:
        if "object" not in af.tree:
            raise ParseError("The ASDF file has no 'object' entry; keys: "
                             + ", ".join(k for k in af.tree if not k.startswith("asdf")))
        return af.tree["object"]


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class AsciiPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.raw = self.add_output("Raw text")
        self.view = self.add_table("Parsed table")
        self.formats = self.add_table("Formats")
        self.formats.set_table(formats_table())
        self.text = self.add_output("Written text")

        sec = Section(self, "Read")
        self.read_path = PathEdit("open")
        sec.form.add_widget("path", "File", self.read_path)
        sec.form.add_combo("fmt", "Format", ["auto"] + ascii_formats(),
                           tip="'auto' guesses the format and its parameters")
        sec.form.add_check("guess", "Guess (auto only)", True)
        sec.form.add_text("delimiter", "Delimiter", tip=r"e.g. , or | or \t (blank = default)")
        sec.form.add_text("header_start", "Header line", tip="0-based line of the column names")
        sec.form.add_text("data_start", "First data line")
        sec.form.add_text("data_end", "Last data line", tip="negative counts from the end")
        sec.form.add_text("names", "Column names", tip="comma-separated; overrides the header")
        sec.form.add_text("comment", "Comment regex", tip="e.g. \\s*#")
        sec.form.add_text("quotechar", "Quote char")
        sec.form.add_text("fill_values", "Fill values", tip="text:replacement; e.g. NA:0; --:-1")
        sec.form.add_text("extra", "Extra options", tip="key=value; key=value (ascii.read kwargs)")
        sec.form.add_text("name", "Store as", "ascii_table")
        sec.add_button("Preview raw text", self.preview_raw)
        sec.add_button("Read", self.read)
        self.read_sec = sec

        sec = Section(self, "Write")
        self.table_combo = WorkspaceCombo(ws, Table)
        sec.form.add_widget("table", "Table", self.table_combo)
        self.write_path = PathEdit("save")
        sec.form.add_widget("path", "File", self.write_path)
        sec.form.add_combo("fmt", "Format", ascii_formats(write=True), current="ecsv")
        sec.form.add_check("overwrite", "Overwrite", False)
        sec.form.add_text("delimiter", "Delimiter")
        sec.form.add_text("formats", "Column formats", tip="name=%.3f; other=%.2e")
        sec.form.add_text("include", "Include columns", tip="comma-separated")
        sec.form.add_text("exclude", "Exclude columns", tip="comma-separated")
        sec.form.add_text("fill_values", "Fill values", tip="masked text:replacement")
        sec.form.add_text("comment", "Comment prefix")
        sec.form.add_text("extra", "Extra options",
                          tip="e.g. latexdict={'caption': 'My table'}; header_start=1")
        sec.add_button("Show as text (no file)", lambda: self.write(to_file=False))
        sec.add_button("Write to file", lambda: self.write(to_file=True))
        self.write_sec = sec

    def _read_args(self) -> Dict[str, Any]:
        f = self.read_sec.form
        return dict(path=need(f.value("path"), "a file path"), fmt=f.value("fmt"),
                    guess=f.value("guess"), delimiter=f.value("delimiter"),
                    header_start=f.value("header_start"), data_start=f.value("data_start"),
                    data_end=f.value("data_end"), names=f.value("names"),
                    comment=f.value("comment"), quotechar=f.value("quotechar"),
                    fill_values=f.value("fill_values"), extra=parse_kwargs(f.value("extra")))

    def preview_raw(self) -> None:
        path = need(self.read_sec.form.value("path"), "a file path")

        def done(text: str) -> None:
            self.raw.show_text(text)
            self.tabs.setCurrentWidget(self.raw)

        self.run(read_preview, done, path)

    def read(self) -> None:
        args, name = self._read_args(), need(self.read_sec.form.value("name"),
                                              "a workspace name")

        def work() -> Tuple[str, Table, List[str]]:
            try:
                preview = read_preview(args["path"])
            except OSError:
                preview = ""
            table, warns = capture_warnings(ascii_read, **args)
            return preview, table, warns

        def done(res: Tuple[str, Table, List[str]]) -> None:
            preview, table, warns = res
            self.raw.show_text(preview)
            self.ws.put(name, table)
            self.view.set_table(display_table(table))
            self.tabs.setCurrentWidget(self.view)
            self.text.show_text("\n".join(sorted(set(warns))))
            self.set_status(f"Read {len(table)} rows x {len(table.colnames)} columns"
                            + (f" ({len(warns)} warning(s))" if warns else ""))

        self.run(work, done, busy_text="Reading...")

    def write(self, to_file: bool) -> None:
        f = self.write_sec.form
        table = self.table_combo.selected()
        path = need(f.value("path"), "an output path") if to_file else ""
        kwargs = dict(fmt=f.value("fmt"), path=path, overwrite=f.value("overwrite"),
                      delimiter=f.value("delimiter"), formats=f.value("formats"),
                      include=f.value("include"), exclude=f.value("exclude"),
                      fill_values=f.value("fill_values"), comment=f.value("comment"),
                      extra=parse_kwargs(f.value("extra")))

        def done(res: Tuple[str, List[str]]) -> None:
            out, warns = res
            if to_file:
                self.text.show_text(f"Wrote {out}" + ("\n" + "\n".join(warns) if warns else ""))
                self.set_status(f"Wrote {out}")
            else:
                self.text.show_text(out)
            self.tabs.setCurrentWidget(self.text)

        self.run(lambda: capture_warnings(ascii_write, table, **kwargs), done)


class VotablePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.vot: Optional[Any] = None
        self.structure = self.add_output("Structure")
        self.fields = self.add_table("Fields")
        self.params = self.add_table("Params")
        self.data = self.add_table("Data")
        self.report = self.add_output("Validation")

        sec = Section(self, "Open")
        self.open_path = PathEdit("open", "VOTable (*.xml *.vot *.votable);;All files (*)")
        sec.form.add_widget("path", "File", self.open_path)
        sec.form.add_combo("verify", "Verify", ["warn", "ignore", "exception"],
                           tip="How strictly the VOTable spec is enforced while parsing")
        sec.add_button("Open", lambda sec=sec: self.open_file(sec.form))
        sec.add_button("Validate against the spec", self.validate)
        self.open_sec = sec

        sec = Section(self, "Table")
        sec.form.add_int("index", "Table #", 0, 0, 10**6)
        sec.form.add_text("name", "Store as", "votable_table")
        sec.add_button("Show fields / params", lambda sec=sec: self.show_fields(sec.form))
        sec.add_button("Table -> workspace", lambda sec=sec: self.to_workspace(sec.form))
        self.table_sec = sec

        sec = Section(self, "Write workspace table")
        self.table_combo = WorkspaceCombo(ws, Table)
        sec.form.add_widget("table", "Table", self.table_combo)
        self.write_path = PathEdit("save")
        sec.form.add_widget("path", "File", self.write_path)
        sec.form.add_combo("fmt", "Serialization", VOTABLE_FORMATS)
        sec.form.add_check("overwrite", "Overwrite", False)
        sec.add_button("Write VOTable", lambda sec=sec: self.write(sec.form))
        self.write_sec = sec

    def open_file(self, f: Any) -> None:
        path, verify = need(f.value("path"), "a file path"), f.value("verify")

        def work() -> Tuple[Any, List[str]]:
            return capture_warnings(votable.parse, path, verify=verify)

        def done(res: Tuple[Any, List[str]]) -> None:
            self.vot, warns = res
            text = describe_votable(self.vot)
            if warns:
                text += "\n\nWarnings:\n" + "\n".join(sorted(set(warns)))
            self.structure.show_text(text)
            self.tabs.setCurrentWidget(self.structure)
            self.set_status(f"Opened {path}")

        self.run(work, done, busy_text=f"Parsing {path}...")

    def _tables(self) -> List[Any]:
        if self.vot is None:
            raise ParseError("Open a VOTable first.")
        return votable_tables(self.vot)

    def show_fields(self, f: Any) -> None:
        tables, i = self._tables(), f.value("index")
        if not 0 <= i < len(tables):
            raise ParseError(f"Table index {i} out of range (found {len(tables)} table(s)).")
        self.fields.set_table(fields_table(tables[i]))
        self.params.set_table(params_table(tables[i]))
        self.tabs.setCurrentWidget(self.fields)

    def to_workspace(self, f: Any) -> None:
        vot, i, name = self.vot, f.value("index"), need(f.value("name"), "a workspace name")
        if vot is None:
            raise ParseError("Open a VOTable first.")

        def done(table: Table) -> None:
            self.ws.put(name, table)
            self.data.set_table(display_table(table))
            self.tabs.setCurrentWidget(self.data)
            self.set_status(f"Stored table {name!r}")

        self.run(votable_to_table, done, vot, i)

    def validate(self) -> None:
        path = need(self.open_sec.form.value("path"), "a file path")

        def done(res: Tuple[bool, str]) -> None:
            ok, text = res
            self.report.show_text(("VALID\n\n" if ok else "NOT VALID\n\n") + text)
            self.tabs.setCurrentWidget(self.report)

        self.run(validate_votable, done, path)

    def write(self, f: Any) -> None:
        table = self.table_combo.selected()
        path, fmt, ow = f.value("path"), f.value("fmt"), f.value("overwrite")
        self.run(lambda: capture_warnings(write_votable, table, path, fmt, ow),
                 lambda res: self.report.show_text(f"Wrote {res[0]}"))


class MiscPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.deps = self.add_table("Dependencies")
        self.deps.set_table(dependency_table())
        self.formats = self.add_table("All table formats")
        self.formats.set_table(formats_table())
        self.view = self.add_table("Table")
        self.out = self.add_output("Messages")

        sec = Section(self, "HDF5 / Parquet tables")
        self.table_combo = WorkspaceCombo(ws, Table)
        sec.form.add_widget("table", "Table", self.table_combo)
        self.path = PathEdit("open", "All files (*)")
        sec.form.add_widget("path", "File", self.path)
        sec.form.add_combo("fmt", "Format", ["hdf5", "parquet"])
        sec.form.add_text("h5path", "HDF5 path", "data", "Group/dataset inside the HDF5 file")
        sec.form.add_check("serialize_meta", "Serialize meta (HDF5)", True)
        sec.form.add_check("overwrite", "Overwrite", False)
        sec.form.add_check("append", "Append (HDF5)", False)
        sec.form.add_text("name", "Store as", "misc_table")
        sec.add_button("Write", lambda sec=sec: self.write_table(sec.form))
        sec.add_button("Read", lambda sec=sec: self.read_table(sec.form))
        self.table_sec = sec

        sec = Section(self, "YAML / ASDF objects")
        self.obj_combo = WorkspaceCombo(ws)
        sec.form.add_widget("obj", "Workspace object", self.obj_combo)
        sec.form.add_multiline("yaml", "YAML text", height=150,
                               tip="astropy.io.misc.yaml: Quantity, Time, SkyCoord, units, ...")
        self.yaml_path = PathEdit("open", "YAML (*.yaml *.yml);;ASDF (*.asdf);;All files (*)")
        sec.form.add_widget("path", "File", self.yaml_path)
        sec.form.add_check("overwrite", "Overwrite", False)
        sec.form.add_text("name", "Store as", "yaml_object")
        sec.add_button("Object -> YAML text", lambda sec=sec: self.dump_yaml(sec.form))
        sec.add_button("YAML text -> workspace", lambda sec=sec: self.load_yaml(sec.form))
        sec.add_button("Save YAML text to file", lambda sec=sec: self.save_yaml(sec.form))
        sec.add_button("Load YAML file -> workspace", lambda sec=sec: self.load_yaml_file(sec.form))
        sec.add_button("Object -> ASDF file", lambda sec=sec: self.write_asdf(sec.form))
        sec.add_button("ASDF file -> workspace", lambda sec=sec: self.read_asdf(sec.form))
        self.obj_sec = sec

    # ---- tables ---------------------------------------------------------------- #
    def write_table(self, f: Any) -> None:
        table, fmt = self.table_combo.selected(), f.value("fmt")
        path = need(f.value("path"), "an output path")
        check_optional_format(fmt)
        kw: Dict[str, Any] = {}
        if fmt == "hdf5":
            kw = dict(path=need(f.value("h5path"), "an HDF5 path"),
                      serialize_meta=f.value("serialize_meta"), append=f.value("append"))
        ow = f.value("overwrite")
        self.run(lambda: capture_warnings(table.write, path, format=fmt, overwrite=ow, **kw),
                 lambda res: self.out.show_text(f"Wrote {path}"))

    def read_table(self, f: Any) -> None:
        fmt, path = f.value("fmt"), need(f.value("path"), "a file path")
        name = need(f.value("name"), "a workspace name")
        check_optional_format(fmt)
        kw = {"path": need(f.value("h5path"), "an HDF5 path")} if fmt == "hdf5" else {}

        def done(res: Tuple[Table, List[str]]) -> None:
            table = res[0]
            self.ws.put(name, table)
            self.view.set_table(display_table(table))
            self.tabs.setCurrentWidget(self.view)

        self.run(lambda: capture_warnings(Table.read, path, format=fmt, **kw), done)

    # ---- objects --------------------------------------------------------------- #
    def dump_yaml(self, f: Any) -> None:
        obj = self.obj_combo.selected()

        def done(text: str) -> None:
            f.set_value("yaml", text)

        self.run(lambda: yaml_dump(obj), done)

    def load_yaml(self, f: Any) -> None:
        self._store(yaml_load(f.value("yaml")), f)

    def _store(self, obj: Any, f: Any) -> None:
        name = need(f.value("name"), "a workspace name")
        self.ws.put(name, obj)
        self.out.show_text(f"Stored {type(obj).__name__} as {name!r}:\n\n{obj!r}")
        self.tabs.setCurrentWidget(self.out)

    def save_yaml(self, f: Any) -> None:
        path, text = need(f.value("path"), "an output path"), need(f.value("yaml"), "YAML text")
        if os.path.exists(path) and not f.value("overwrite"):
            raise ParseError(f"{path} exists; tick 'Overwrite' to replace it.")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        self.out.show_text(f"Wrote {path}")

    def load_yaml_file(self, f: Any) -> None:
        path = need(f.value("path"), "a file path")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        f.set_value("yaml", text)
        self._store(yaml_load(text), f)

    def write_asdf(self, f: Any) -> None:
        obj, path, ow = self.obj_combo.selected(), f.value("path"), f.value("overwrite")
        check_optional_format("asdf")
        self.run(lambda: asdf_write(obj, path, ow), lambda p: self.out.show_text(f"Wrote {p}"))

    def read_asdf(self, f: Any) -> None:
        path = need(f.value("path"), "a file path")
        check_optional_format("asdf")
        self.run(lambda: asdf_read(path), lambda obj: self._store(obj, f))


SPECS = [
    ModuleSpec("io_ascii", "ASCII tables (io.ascii)", CATEGORY, lambda ws: AsciiPanel(ws),
               "Read and write every astropy.io.ascii format with a raw-text preview"),
    ModuleSpec("io_votable", "VOTable (io.votable)", CATEGORY, lambda ws: VotablePanel(ws),
               "Inspect, validate, convert and write VOTable files"),
    ModuleSpec("io_misc", "HDF5 / Parquet / YAML / ASDF", CATEGORY, lambda ws: MiscPanel(ws),
               "astropy.io.misc formats and the list of all registered table formats"),
]
