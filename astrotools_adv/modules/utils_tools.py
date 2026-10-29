"""System pages: IERS/leap seconds, download cache, configuration, utilities, About."""
from __future__ import annotations

import contextlib
import importlib
import importlib.metadata
import io
import json
import os
import platform
import sys
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.table import Table
from astropy.time import Time
from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import (
    QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.parsing import (
    ParseError, format_exception, parse_float, parse_int, parse_time, safe_eval,
)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, OutputPane, ParamForm, TableView
from ..core.workspace import Workspace

IERS_CONFIG_ITEMS = ("auto_download", "auto_max_age", "iers_degraded_accuracy", "remote_timeout")


def _confirm(parent: QWidget, text: str) -> bool:
    return QMessageBox.question(parent, "Confirm", text) == QMessageBox.Yes


def _capture(fn: Callable[[], Any]) -> Tuple[Any, str, List[str]]:
    """Run ``fn`` returning ``(value, stdout, warnings)``."""
    buf = io.StringIO()
    with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(buf):
        warnings.simplefilter("always")
        value = fn()
    return value, buf.getvalue(), [f"{w.category.__name__}: {w.message}" for w in caught]


# --------------------------------------------------------------------------- #
# IERS and leap seconds
# --------------------------------------------------------------------------- #
def parse_optional_float(text: str, name: str) -> Optional[float]:
    return None if text.strip().lower() in ("", "none") else parse_float(text, name)


def iers_table_summary(table: Any, label: str) -> str:
    """Range/size of an IERS table as text."""
    mjd = np.asarray(getattr(table["MJD"], "value", table["MJD"]), dtype=float)
    t0, t1 = Time(mjd.min(), format="mjd"), Time(mjd.max(), format="mjd")
    return (f"{label}: {type(table).__name__}, {len(table)} rows\n"
            f"  MJD {mjd.min():.1f} .. {mjd.max():.1f}  ({t0.iso[:10]} .. {t1.iso[:10]})\n"
            f"  columns: {', '.join(table.colnames)}")


def leap_second_table() -> Table:
    """Leap seconds known to ERFA (offline); ``meta['expires']`` is when the list is stale."""
    from astropy.utils import iers

    ls = iers.LeapSeconds.from_erfa()
    out = Table([list(map(int, ls["year"])), list(map(int, ls["month"])),
                 list(map(float, ls["tai_utc"]))], names=("year", "month", "tai_utc"))
    out["tai_utc"].unit = u.s
    out.meta["expires"] = ls.expires.iso
    return out


class IersPanel(ModulePanel):
    SOURCES = ["IERS-B (bundled)", "IERS-A (bundled)", "Active table"]

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        from astropy.utils import iers

        self._restore_table: Any = None  # context returned by earth_orientation_table.set
        f = self.form
        f.add_combo("source", "Lookup table", self.SOURCES,
                    tip="'Active table' may download data if auto_download is on.")
        f.add_text("time", "UTC time", "2020-06-01 00:00:00", "ISO string, 'now', ...")
        f.add_check("auto_download", "auto_download", bool(iers.conf.auto_download),
                    "Download current IERS-A data when needed (network).")
        f.add_text("auto_max_age", "auto_max_age [days]", str(iers.conf.auto_max_age),
                   "Maximum age before a refresh; 'none' disables the age check.")
        f.add_combo("degraded", "iers_degraded_accuracy", ["error", "warn", "ignore"],
                    tip="What to do when a time is outside the table (lower accuracy).",
                    current=str(iers.conf.iers_degraded_accuracy))
        f.add_text("remote_timeout", "remote_timeout [s]", str(iers.conf.remote_timeout))
        f.add_combo("eop", "Earth orientation table", ["IERS-B (bundled)", "IERS-A (bundled)"],
                    tip="Session-wide table used by astropy.time / coordinates.")
        self.info = self.add_output("Info")
        self.table_view = self.add_table("Leap seconds")
        self.add_button("Show table ranges", self.show_info)
        self.add_button("Look up UT1-UTC / polar motion", self.lookup)
        self.add_button("Show leap seconds", self.show_leap_seconds)
        self.add_button("Apply configuration", self.apply_config)
        self.add_button("Reset configuration", self.reset_config)
        self.add_button("Use selected Earth orientation table", self.select_table)
        self.add_button("Restore default Earth orientation table", self.restore_table)
        self.add_button("Update IERS-A from network ...", self.update_online,
                        "Downloads data from the IERS servers. Needs internet access.")
        self.show_info()

    # ---- tables ---------------------------------------------------------- #
    def _table(self, which: str) -> Any:
        from astropy.utils import iers

        if which.startswith("IERS-B"):
            return iers.IERS_B.open()
        if which.startswith("IERS-A"):
            return iers.IERS_A.open()
        return iers.earth_orientation_table.get()

    def show_info(self) -> None:
        def work() -> str:
            from astropy.utils import iers

            parts = [iers_table_summary(iers.IERS_B.open(), "IERS-B (bundled)"),
                     iers_table_summary(iers.IERS_A.open(), "IERS-A (bundled)")]
            parts.append("\nConfiguration:\n" + "\n".join(
                f"  {n} = {getattr(iers.conf, n)!r}" for n in IERS_CONFIG_ITEMS))
            parts.append(f"  iers_auto_url = {iers.conf.iers_auto_url}")
            parts.append("\nSession Earth orientation table: " + (
                "changed by this page" if self._restore_table is not None
                else "default (IERS-A, auto-updated if enabled)"))
            return "\n".join(parts)

        self.run(work, self.info.show_text, busy_text="Reading IERS tables ...")

    def lookup(self) -> None:
        self.guard(self._lookup)

    def _lookup(self) -> None:
        source = self.form.value("source")
        t = parse_time(self.form.value("time"), scale="utc")

        def work() -> str:
            tab = self._table(source)
            ut1_utc, status = tab.ut1_utc(t.jd1, t.jd2, return_status=True)
            x, y = tab.pm_xy(t.jd1, t.jd2)
            return (f"Time (UTC): {t.iso}   MJD {t.mjd:.6f}\nSource: {source}\n"
                    f"UT1-UTC = {ut1_utc.to(u.s):.6f}\n"
                    f"polar motion x = {x.to(u.arcsec):.6f}, y = {y.to(u.arcsec):.6f}\n"
                    f"status code: {np.asarray(status).tolist()} (0 = inside the table)")

        self.run(work, self.info.show_text, busy_text="Looking up ...")
        self.tabs.setCurrentWidget(self.info)

    def show_leap_seconds(self) -> None:
        def done(table: Table) -> None:
            self.table_view.set_table(table)
            self.tabs.setCurrentWidget(self.table_view)
            self.info.show_text(f"{len(table)} leap-second entries; "
                                f"list valid until {table.meta['expires']}")

        self.run(leap_second_table, done)

    # ---- configuration -------------------------------------------------- #
    def apply_config(self) -> None:
        def go() -> None:
            from astropy.utils import iers

            v = self.form.values()
            new = {
                "auto_download": bool(v["auto_download"]),
                "auto_max_age": parse_optional_float(v["auto_max_age"], "auto_max_age"),
                "iers_degraded_accuracy": v["degraded"],
                "remote_timeout": parse_float(v["remote_timeout"], "remote_timeout"),
            }
            for name, value in new.items():
                setattr(iers.conf, name, value)
            self.set_status("IERS configuration applied (this session only)")
            self.show_info()

        self.guard(go)

    def reset_config(self) -> None:
        def go() -> None:
            from astropy.utils import iers

            for name in IERS_CONFIG_ITEMS:
                getattr(type(iers.conf), name).set(getattr(type(iers.conf), name).defaultvalue)
            self.form.set_value("auto_download", iers.conf.auto_download)
            self.form.set_value("auto_max_age", str(iers.conf.auto_max_age))
            self.form.set_value("degraded", iers.conf.iers_degraded_accuracy)
            self.form.set_value("remote_timeout", str(iers.conf.remote_timeout))
            self.show_info()

        self.guard(go)

    def select_table(self) -> None:
        def go() -> None:
            from astropy.utils import iers

            table = self._table(self.form.value("eop"))
            ctx = iers.earth_orientation_table.set(table)
            if self._restore_table is None:  # remember the original state only once
                self._restore_table = ctx
            self.set_status(f"Earth orientation table: {self.form.value('eop')}")
            self.show_info()

        self.guard(go)

    def restore_table(self) -> None:
        def go() -> None:
            if self._restore_table is not None:
                self._restore_table.__exit__(None, None, None)
                self._restore_table = None
            self.show_info()

        self.guard(go)

    def update_online(self) -> None:
        def go() -> None:
            if not self.confirm("This contacts the IERS servers to download current "
                                "Earth-orientation data.\n\nContinue?"):
                return

            def work() -> str:
                from astropy.utils import iers

                return iers_table_summary(iers.IERS_Auto.open(), "IERS-Auto (updated)")

            self.run(work, self.info.show_text, busy_text="Downloading IERS data ...")
            self.tabs.setCurrentWidget(self.info)

        self.guard(go)

    def confirm(self, text: str) -> bool:
        return _confirm(self, text)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.restore_table()
        super().closeEvent(event)


# --------------------------------------------------------------------------- #
# Download cache
# --------------------------------------------------------------------------- #
def cache_table(pkgname: str = "astropy") -> Table:
    """Cache listing: URL/key, local file, size in bytes."""
    from astropy.utils import data

    contents = data.cache_contents(pkgname, on_missing="ignore")
    rows = [(url, path, os.path.getsize(path) if os.path.exists(path) else 0)
            for url, path in sorted(contents.items())]
    cols = list(zip(*rows)) if rows else [(), (), ()]
    table = Table([list(cols[0]), list(cols[1]), np.array(cols[2], dtype=np.int64)],
                  names=("url", "file", "size"), dtype=[str, str, np.int64])
    table["size"].unit = u.byte
    return table


class DataCachePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("pkg", "Package cache", "astropy", "Cache namespace (astropy, astroquery, ...).")
        f.add_text("url", "URL / key", "", "URL for download / lookup / import key / single-entry clear.")
        f.add_float("timeout", "Download timeout [s]", 10.0, 1.0, 600.0, 1)
        self.info = self.add_output("Info")
        self.listing = self.add_table("Cache contents")
        self.add_button("Refresh listing", self.refresh)
        self.add_button("Verify cache", self.verify, "astropy.utils.data.check_download_cache")
        self.add_button("Is URL cached?", self.check_url)
        self.add_button("Download URL into cache", self.download,
                        "Network access; runs in the background.")
        self.add_button("Import local file under URL key ...", self.import_file_dialog)
        self.add_button("Export cache to ZIP ...", self.export_dialog)
        self.add_button("Import cache from ZIP ...", self.import_zip_dialog)
        self.add_button("Clear URL entry", self.clear_entry)
        self.add_button("Clear whole cache ...", self.clear_all)
        self.refresh()

    def _pkg(self) -> str:
        return self.form.value("pkg") or "astropy"

    def confirm(self, text: str) -> bool:
        return _confirm(self, text)

    def refresh(self) -> None:
        pkg = self._pkg()

        def work() -> Tuple[Table, int, str]:
            from astropy import config
            from astropy.utils import data

            return cache_table(pkg), data.cache_total_size(pkg), str(config.get_cache_dir_path())

        def done(result: Tuple[Table, int, str]) -> None:
            table, total, where = result
            self.listing.set_table(table)
            self.info.show_text(f"Cache directory: {where}\nEntries: {len(table)}\n"
                                f"Total size: {total} bytes")

        self.run(work, done, busy_text="Reading cache ...")

    def verify(self) -> None:
        pkg = self._pkg()

        def work() -> str:
            from astropy.utils import data

            data.check_download_cache(pkg)
            return "Cache verified: all entries are consistent."

        self.run(work, self.info.show_text, busy_text="Verifying cache ...")
        self.tabs.setCurrentWidget(self.info)

    def check_url(self) -> None:
        pkg, url = self._pkg(), self.form.value("url")
        if not url:
            self.fail(ParseError("Enter a URL / key first."))
            return

        def work() -> str:
            from astropy.utils import data

            return f"{url}\n  in cache: {data.is_url_in_cache(url, pkg, on_missing='ignore')}"

        self.run(work, self.info.show_text)
        self.tabs.setCurrentWidget(self.info)

    def download(self) -> None:
        pkg, url, timeout = self._pkg(), self.form.value("url"), self.form.value("timeout")
        if not url:
            self.fail(ParseError("Enter a URL first."))
            return

        def work() -> str:
            from astropy.utils import data

            path = data.download_file(url, cache=True, show_progress=False, timeout=timeout,
                                      pkgname=pkg)
            return f"Downloaded {url}\n  -> {path}"

        def done(text: str) -> None:
            self.info.show_text(text)
            self.refresh()

        self.run(work, done, busy_text="Downloading ...")

    def import_file(self, path: str) -> None:
        pkg, key = self._pkg(), self.form.value("url")
        if not key:
            self.fail(ParseError("Enter the URL / key to store the file under first."))
            return

        def work() -> str:
            from astropy.utils import data

            return data.import_file_to_cache(key, path, remove_original=False, pkgname=pkg)

        def done(cached: str) -> None:
            self.info.show_text(f"Imported {path}\n  key: {key}\n  cache file: {cached}")
            self.refresh()

        self.run(work, done)

    def import_file_dialog(self) -> None:
        path = self.ask_open_path("File to import")
        if path:
            self.import_file(path)

    def export_cache(self, path: str, overwrite: bool = False) -> None:
        pkg = self._pkg()

        def work() -> str:
            from astropy.utils import data

            data.export_download_cache(path, overwrite=overwrite, pkgname=pkg)
            return f"Exported cache to {path} ({os.path.getsize(path)} bytes)"

        self.run(work, self.info.show_text)
        self.tabs.setCurrentWidget(self.info)

    def export_dialog(self) -> None:
        path = self.ask_save_path("Export cache", "ZIP (*.zip)", "astropy-cache.zip")
        if path:  # the save dialog already asked about overwriting
            self.export_cache(path, overwrite=True)

    def import_zip(self, path: str) -> None:
        pkg = self._pkg()

        def work() -> str:
            from astropy.utils import data

            data.import_download_cache(path, update_cache=False, pkgname=pkg)
            return f"Imported cache entries from {path}"

        def done(text: str) -> None:
            self.info.show_text(text)
            self.refresh()

        self.run(work, done)

    def import_zip_dialog(self) -> None:
        path = self.ask_open_path("Cache ZIP", "ZIP (*.zip);;All files (*)")
        if path:
            self.import_zip(path)

    def clear_entry(self) -> None:
        pkg, key = self._pkg(), self.form.value("url")
        if not key:
            self.fail(ParseError("Enter the URL / key of the entry to remove."))
            return

        def work() -> str:
            from astropy.utils import data

            data.clear_download_cache(key, pkg, on_missing="ignore")
            return f"Removed {key} from the cache."

        def done(text: str) -> None:
            self.info.show_text(text)
            self.refresh()

        self.run(work, done)

    def clear_all(self) -> None:
        if not self.confirm(f"Delete the entire '{self._pkg()}' download cache?\n"
                            "Data will be downloaded again when needed."):
            return
        pkg = self._pkg()

        def work() -> str:
            from astropy.utils import data

            data.clear_download_cache(pkgname=pkg)
            return "Download cache cleared."

        def done(text: str) -> None:
            self.info.show_text(text)
            self.refresh()

        self.run(work, done)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, eq=False)
class ConfigEntry:
    module: str
    name: str
    item: Any  # astropy.config.ConfigItem

    @property
    def key(self) -> str:
        return f"{self.module}.{self.name}"

    @property
    def value(self) -> Any:
        return self.item()

    @property
    def default(self) -> Any:
        return self.item.defaultvalue


def collect_config() -> List[ConfigEntry]:
    """Every ``ConfigItem`` of every imported astropy configuration namespace."""
    from astropy.config import ConfigNamespace

    from .api_explorer import collect_api

    collect_api()  # imports every public astropy module so all namespaces exist
    seen, out = set(), []
    for modname, mod in sorted(list(sys.modules.items())):
        if mod is None or not (modname == "astropy" or modname.startswith("astropy.")):
            continue
        conf = getattr(mod, "conf", None)
        if isinstance(conf, ConfigNamespace) and id(conf) not in seen:
            seen.add(id(conf))
            out.extend(ConfigEntry(item.module, name, item) for name, item in conf.items())
    return sorted(out, key=lambda e: e.key)


_TRUE, _FALSE = {"true", "1", "yes", "on"}, {"false", "0", "no", "off"}


def parse_config_value(entry: ConfigEntry, text: str) -> Any:
    """Convert ``text`` to the item's declared type (``cfgtype``)."""
    cfgtype, s = str(entry.item.cfgtype), text.strip()
    if cfgtype == "boolean":
        if s.lower() in _TRUE:
            return True
        if s.lower() in _FALSE:
            return False
        raise ParseError(f"{entry.key}: expected true/false, got {text!r}.")
    if cfgtype == "integer":
        return parse_int(s, entry.key)
    if cfgtype == "float":
        return parse_float(s, entry.key)
    if cfgtype == "string_list":
        return [p.strip() for p in s.split(",") if p.strip()]
    return s


class ConfigPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.entries: List[ConfigEntry] = []
        f = self.form
        self.item_combo = f.add_combo("item", "Item", [])
        self.item_combo.setMinimumContentsLength(24)
        self.item_combo.currentIndexChanged.connect(self._show_item)
        f.add_text("value", "New value", "", "Typed according to the item's type.")
        f.add_text("pkg", "Config package", "astropy", "For 'Show default config file'.")
        self.detail = self.add_output("Item")
        self.listing = self.add_table("All items")
        self.paths = self.add_output("Paths / defaults")
        self.add_button("Set value (this session)", self.set_value,
                        "Changes the running session only; nothing is written to disk.")
        self.add_button("Reset item to default", self.reset_item)
        self.add_button("Reload config file for item's package", self.reload_file)
        self.add_button("Show config locations", self.show_paths)
        self.add_button("Show default config file text", self.show_default_file)
        self.run(collect_config, self._on_entries, busy_text="Collecting configuration ...")

    def _on_entries(self, entries: List[ConfigEntry]) -> None:
        self.entries = entries
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        self.item_combo.addItems([e.key for e in entries])
        self.item_combo.blockSignals(False)
        self._refresh_listing()
        self._show_item()
        self.show_paths()

    def _refresh_listing(self) -> None:
        rows = [(e.module, e.name, repr(e.value), repr(e.default), str(e.item.cfgtype),
                 " ".join(str(e.item.description).split())) for e in self.entries]
        cols = list(zip(*rows)) if rows else [()] * 6
        self.listing.set_table(Table([list(c) for c in cols],
                                     names=("module", "name", "value", "default", "type",
                                            "description"), dtype=[str] * 6))

    def current_entry(self) -> ConfigEntry:
        key = self.item_combo.currentText()
        for e in self.entries:
            if e.key == key:
                return e
        raise ParseError("No configuration item selected.")

    def _show_item(self) -> None:
        try:
            e = self.current_entry()
        except ParseError:
            self.detail.show_text("")
            return
        self.detail.show_text(
            f"{e.key}\n\ntype: {e.item.cfgtype}\nvalue: {e.value!r}\ndefault: {e.default!r}\n"
            + (f"options: {e.item.options}\n" if getattr(e.item, "options", None) else "")
            + f"\n{' '.join(str(e.item.description).split())}")

    def set_value(self) -> None:
        def go() -> None:
            e = self.current_entry()
            e.item.set(parse_config_value(e, self.form.value("value")))
            self.set_status(f"{e.key} = {e.value!r}")
            self._refresh_listing()
            self._show_item()

        self.guard(go)

    def reset_item(self) -> None:
        def go() -> None:
            e = self.current_entry()
            e.item.set(e.default)
            self._refresh_listing()
            self._show_item()

        self.guard(go)

    def reload_file(self) -> None:
        def go() -> None:
            from astropy import config

            e = self.current_entry()
            config.reload_config(e.module)
            self._refresh_listing()
            self._show_item()

        self.guard(go)

    def show_paths(self) -> None:
        def go() -> None:
            from astropy import config

            cfg = config.get_config_dir_path()
            self.paths.show_text(
                f"Config directory: {cfg}\nConfig file: {cfg / 'astropy.cfg'} "
                f"({'exists' if (cfg / 'astropy.cfg').exists() else 'not created'})\n"
                f"Cache directory: {config.get_cache_dir_path()}")

        self.guard(go)

    def show_default_file(self) -> None:
        pkg = self.form.value("pkg") or "astropy"

        def work() -> str:
            from astropy import config

            buf = io.StringIO()  # a file-like target keeps the user's config file untouched
            _v, _out, _w = _capture(lambda: config.generate_config(pkg, buf))
            return buf.getvalue() or "(no configuration items)"

        def done(text: str) -> None:
            self.paths.show_text(text)
            self.tabs.setCurrentWidget(self.paths)

        self.run(work, done, busy_text="Generating default configuration ...")


# --------------------------------------------------------------------------- #
# Utility tools (inline results, no dialogs)
# --------------------------------------------------------------------------- #
class ToolPage(QWidget):
    """Mini form + 'Run' + text output. Errors are shown inline."""

    def __init__(self, button: str, func: Callable[[Dict[str, Any]], str],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.func = func
        self.form = ParamForm()
        self.output = OutputPane()
        self.button = QPushButton(button)
        self.button.clicked.connect(lambda _c=False: self.run())
        lay = QVBoxLayout(self)
        lay.addWidget(self.form)
        lay.addWidget(self.button)
        lay.addWidget(self.output, 1)

    def run(self) -> None:
        try:
            text, _out, warns = _capture(lambda: self.func(self.form.values()))
            if warns:
                text += "\n\n--- warnings ---\n" + "\n".join(dict.fromkeys(warns))
            self.output.show_text(text)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self.output.setPlainText(f"Error: {format_exception(exc)}")


def tool_masked(v: Dict[str, Any]) -> str:
    from astropy.utils.masked import Masked

    data = safe_eval(v["data"])
    mask = np.asarray(safe_eval(v["mask"]), dtype=bool)
    m = Masked(data, mask=mask)
    result = safe_eval(v["op"], {"m": m, "Masked": Masked})
    return (f"m = {m!r}\n\nmask:     {m.mask.tolist()}\nunmasked: {m.unmasked!r}\n\n"
            f"{v['op']}  ->  {result!r}")


def tool_merge(v: Dict[str, Any]) -> str:
    from astropy.utils.metadata import merge

    left, right = safe_eval(v["left"], {"dict": dict}), safe_eval(v["right"], {"dict": dict})
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise ParseError("Both inputs must be dicts.")
    return f"merged = {dict(merge(left, right, metadata_conflicts=v['conflicts']))!r}"


def tool_introspect(v: Dict[str, Any]) -> str:
    from astropy.utils.introspection import minversion, resolve_name

    lines = []
    if v["name"]:
        obj = resolve_name(v["name"])
        doc = (getattr(obj, "__doc__", None) or "").strip().splitlines()
        lines += [f"resolve_name({v['name']!r}) -> {obj!r}", f"  {doc[0] if doc else '(no doc)'}"]
    if v["module"]:
        mod_version = getattr(importlib.import_module(v["module"]), "__version__", "unknown")
        ok = minversion(v["module"], v["version"]) if v["version"] else None
        lines += [f"{v['module']} version: {mod_version}"]
        if ok is not None:
            lines.append(f"minversion({v['module']!r}, {v['version']!r}) -> {ok}")
    return "\n".join(lines) or "Enter a dotted name and/or a module and version."


def tool_format(v: Dict[str, Any]) -> str:
    from astropy.utils.console import human_file_size, human_time

    lines = []
    if v["size"]:
        lines.append(f"human_file_size({v['size']}) -> {human_file_size(parse_float(v['size']))!r}")
    if v["seconds"]:
        lines.append(f"human_time({v['seconds']}) -> {human_time(parse_float(v['seconds']))!r}")
    return "\n".join(lines) or "Enter a byte count and/or a number of seconds."


def tool_json(v: Dict[str, Any]) -> str:
    from astropy.utils.misc import JsonCustomEncoder

    return json.dumps(safe_eval(v["expr"]), cls=JsonCustomEncoder, indent=2)


class UtilsPanel(QWidget):
    """Small astropy.utils helpers as tabs."""

    def __init__(self, ws: Workspace) -> None:
        super().__init__()
        self.ws = ws
        self.tabs = QTabWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        self.pages: Dict[str, ToolPage] = {}

        p = self._page("Masked", "Evaluate", tool_masked)
        p.form.add_text("data", "Data", "np.arange(6.) * u.m", "Expression: array or Quantity.")
        p.form.add_text("mask", "Mask", "[0, 1, 0, 0, 1, 0]", "True = masked.")
        p.form.add_text("op", "Operation on m", "m.mean()", "e.g. m.sum(), m * 2, m.max()")

        p = self._page("Metadata merge", "Merge", tool_merge)
        p.form.add_text("left", "Left", "{'a': 1, 'b': 2}")
        p.form.add_text("right", "Right", "{'b': 3, 'c': 4}")
        p.form.add_combo("conflicts", "On conflict", ["warn", "silent", "error"])

        p = self._page("Introspection", "Inspect", tool_introspect)
        p.form.add_text("name", "resolve_name", "astropy.units.Quantity", "Dotted path to an object.")
        p.form.add_text("module", "Module", "numpy")
        p.form.add_text("version", "Minimum version", "1.20")

        p = self._page("Formatting", "Format", tool_format)
        p.form.add_text("size", "Bytes", "123456789")
        p.form.add_text("seconds", "Seconds", "3725")

        p = self._page("JSON encoder", "Encode", tool_json)
        p.form.add_text("expr", "Expression", "{'d': 3 * u.m, 'a': np.arange(3)}",
                        "Quantities, arrays, times ... via JsonCustomEncoder.")

    def _page(self, title: str, button: str, func: Callable[[Dict[str, Any]], str]) -> ToolPage:
        page = ToolPage(button, func)
        self.pages[title] = page
        self.tabs.addTab(page, title)
        return page


# --------------------------------------------------------------------------- #
# About / versions / citation
# --------------------------------------------------------------------------- #
COMPONENTS = [  # (distribution, license)
    ("astropy", "BSD-3-Clause"), ("astroquery", "BSD-3-Clause"), ("pyvo", "BSD-3-Clause"),
    ("pyerfa", "BSD-3-Clause"), ("numpy", "BSD-3-Clause"), ("scipy", "BSD-3-Clause"),
    ("matplotlib", "Matplotlib License (PSF-based)"), ("PyQt5", "GPLv3 or commercial"),
]


def version_table() -> Table:
    rows = [("Python", platform.python_version(), "PSF"),
            ("Platform", platform.platform(), ""),
            ("Qt", QT_VERSION_STR, "LGPLv3 / GPL / commercial")]
    for dist, lic in COMPONENTS:
        try:
            ver = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            ver = "not installed"
        rows.append((dist, ver, lic))
    cols = list(zip(*rows))
    return Table([list(c) for c in cols], names=("component", "version", "license"), dtype=[str] * 3)


class AboutPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.versions = self.add_table("Versions")
        self.system = self.add_output("System info")
        self.citation = self.add_output("Citation / BibTeX")
        self.add_button("Refresh", self.refresh)
        self.add_button("Copy BibTeX", self.copy_bibtex)
        self.refresh()

    def refresh(self) -> None:
        def go() -> None:
            import astropy

            self.versions.set_table(version_table())
            _v, text, _w = _capture(astropy.system_info)
            self.system.show_text(f"PyQt5 {PYQT_VERSION_STR}\n\n{text}")
            self.citation.show_text(f"Please cite astropy:\n\n{astropy.__citation__}\n\n"
                                    f"BibTeX:\n{astropy.__bibtex__}")

        self.guard(go)

    def copy_bibtex(self) -> None:
        def go() -> None:
            import astropy

            QGuiApplication.clipboard().setText(astropy.__bibtex__)
            self.set_status("BibTeX copied to clipboard")

        self.guard(go)


SPECS = [
    ModuleSpec("iers", "IERS & Leap Seconds", "System", lambda ws: IersPanel(ws),
               "Earth orientation tables, leap seconds, astropy.utils.iers configuration"),
    ModuleSpec("data_cache", "Data Cache", "System", lambda ws: DataCachePanel(ws),
               "Inspect, verify, import/export and clear astropy's download cache"),
    ModuleSpec("config", "Configuration", "System", lambda ws: ConfigPanel(ws),
               "View and change every astropy configuration item for this session"),
    ModuleSpec("utils_misc", "Utilities", "System", lambda ws: UtilsPanel(ws),
               "Masked arrays, metadata merging, introspection, formatting, JSON"),
    ModuleSpec("about", "About & Citation", "System", lambda ws: AboutPanel(ws),
               "Versions, licenses, system info and astropy citation"),
]
