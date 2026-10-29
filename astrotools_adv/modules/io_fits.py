"""astropy.io.fits: open/inspect/edit/save FITS files, headers, images, tables, checksums."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.nddata import NDData
from astropy.table import Table
from astropy.wcs import WCS
from PyQt5.QtWidgets import QComboBox, QLabel

from ..core.parsing import ParseError, parse_float
from ..core.registry import ModuleSpec
from ..core.widgets import MplCanvas, ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace
from .table_tools import PathEdit, Section, capture_warnings, need

CATEGORY = "Data"
COMPRESSIONS = ["RICE_1", "GZIP_1", "GZIP_2", "HCOMPRESS_1", "PLIO_1"]
VERIFY_OPTIONS = ["exception", "fix", "silentfix", "fix+warn", "fix+exception",
                  "silentfix+warn", "warn", "ignore"]
STRETCHES = ["linear", "log", "sqrt", "asinh"]
CHECK_TEXT = {0: "FAILED", 1: "ok", 2: "absent"}
MAX_DISPLAY = 4096  # larger images are strided for display only


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def parse_header_value(text: str) -> Any:
    """``'5'`` -> int, ``'1.5'`` -> float, ``T``/``F`` -> bool, quotes force a string."""
    t = (text or "").strip()
    if not t:
        raise ParseError("Please give a value (use quotes for an empty string: '').")
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return t[1:-1]
    if t.upper() in ("T", "TRUE"):
        return True
    if t.upper() in ("F", "FALSE"):
        return False
    try:
        return int(t)
    except ValueError:
        pass
    try:
        val = float(t)
        if np.isfinite(val):
            return val
    except ValueError:
        pass
    return t


def parse_ext(text: str) -> Dict[str, Any]:
    """Keyword arguments selecting an extension: blank -> ext=0, digits -> ext=n, else extname."""
    t = (text or "").strip()
    if not t:
        return {"ext": 0}
    return {"ext": int(t)} if t.lstrip("-").isdigit() else {"extname": t}


def header_text(header: fits.Header, query: str = "") -> str:
    q = (query or "").strip().lower()
    lines = [f"{i:4d}  {card.image.rstrip()}" for i, card in enumerate(header.cards)
             if not q or q in card.image.lower()]
    return "\n".join(lines) or "(no matching cards)"


def hdu_overview(hdul: fits.HDUList) -> Table:
    cols: Dict[str, list] = {k: [] for k in
                             ("No.", "Name", "Ver", "Type", "Cards", "Dimensions", "Format")}
    for i, hdu in enumerate(hdul):
        dims, fmt = "", ""
        if isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            dims = f"{hdu.header.get('NAXIS2', 0)}R x {hdu.header.get('TFIELDS', 0)}C"
            fmt = "table"
        elif getattr(hdu, "is_image", False) or isinstance(hdu, fits.CompImageHDU):
            shape = hdu.shape
            dims = " x ".join(str(n) for n in reversed(shape)) if shape else ""
            fmt = str(hdu.header.get("ZBITPIX", hdu.header.get("BITPIX", "")))
        for key, val in zip(cols, (i, hdu.name, hdu.ver, type(hdu).__name__, len(hdu.header),
                                   dims, fmt)):
            cols[key].append(val)
    return Table(cols)


def columns_table(hdu: Any) -> Table:
    if not isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
        raise ParseError("The selected HDU is not a table.")
    info = hdu.columns.info(output=False)
    return Table({k: [str(x) for x in v] for k, v in info.items()})


def image_array(hdu: Any, plane: str = "") -> np.ndarray:
    """Float copy of the selected 1-D/2-D slice of an image HDU."""
    if isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)) or getattr(hdu, "data", None) is None:
        raise ParseError("The selected HDU has no image data.")
    data = hdu.data
    idx = [int(p) for p in plane.replace(";", ",").split(",") if p.strip()] if plane.strip() else []
    if data.ndim > 2:
        lead = data.ndim - 2
        idx = (idx + [0] * lead)[:lead]
        try:
            data = data[tuple(idx)]
        except IndexError:
            raise ParseError(f"Plane {tuple(idx)} is outside the data shape {hdu.data.shape}.") \
                from None
    return np.array(data, dtype=float)


def stats_text(arr: np.ndarray, header: Optional[fits.Header] = None) -> str:
    finite = arr[np.isfinite(arr)]
    lines = [f"shape      {arr.shape}", f"dtype      {arr.dtype}",
             f"pixels     {arr.size}", f"NaN        {int(np.isnan(arr).sum())}",
             f"+-inf      {int(np.isinf(arr).sum())}"]
    if header is not None:
        for key in ("BITPIX", "BSCALE", "BZERO", "BUNIT"):
            if key in header:
                lines.append(f"{key:<10} {header[key]}")
    if finite.size:
        p1, p99 = np.percentile(finite, [1, 99])
        lines += [f"min        {finite.min():.10g}", f"max        {finite.max():.10g}",
                  f"mean       {finite.mean():.10g}", f"median     {np.median(finite):.10g}",
                  f"std        {finite.std():.10g}", f"sum        {finite.sum():.10g}",
                  f"1%         {p1:.10g}", f"99%        {p99:.10g}"]
    else:
        lines.append("(no finite pixels)")
    return "\n".join(lines)


def display_limits(arr: np.ndarray, vmin: str = "", vmax: str = "", lo: float = 0.0,
                   hi: float = 100.0) -> Tuple[float, float]:
    """Explicit vmin/vmax win; otherwise the ``lo``..``hi`` percentiles of finite pixels."""
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        raise ParseError("The image has no finite pixels.")
    if not 0 <= lo < hi <= 100:
        raise ParseError("Percentiles must satisfy 0 <= low < high <= 100.")
    a, b = np.percentile(finite, [lo, hi])
    a = parse_float(vmin, "vmin") if vmin.strip() else float(a)
    b = parse_float(vmax, "vmax") if vmax.strip() else float(b)
    if a > b:
        raise ParseError("vmin must not exceed vmax.")
    if a == b:
        a, b = a - 0.5, b + 0.5
    return a, b


def make_norm(stretch: str, vmin: float, vmax: float, arr: Optional[np.ndarray] = None) -> Any:
    from matplotlib import colors

    if stretch == "linear":
        return colors.Normalize(vmin, vmax)
    if stretch == "log":
        if vmin <= 0:
            pos = arr[np.isfinite(arr) & (arr > 0)] if arr is not None else np.array([])
            vmin = float(pos.min()) if pos.size else 1e-3 * vmax
            if vmin >= vmax:
                raise ParseError("Log stretch needs positive pixel values.")
        return colors.LogNorm(vmin, vmax)
    if stretch == "sqrt":
        return colors.PowerNorm(0.5, vmin, vmax, clip=True)
    if stretch == "asinh":
        return colors.AsinhNorm(vmin=vmin, vmax=vmax)
    raise ParseError(f"Unknown stretch {stretch!r}.")


def plot_image(canvas: MplCanvas, arr: np.ndarray, stretch: str, vmin: float, vmax: float,
               cmap: str, title: str = "") -> None:
    """GUI-thread drawing of a 1-D or 2-D array."""
    ax = canvas.axes()
    if arr.ndim == 1:
        ax.plot(arr)
        ax.set_xlabel("index")
    else:
        step = max(1, int(np.ceil(max(arr.shape) / MAX_DISPLAY)))
        shown = arr[::step, ::step]
        im = ax.imshow(shown, origin="lower", cmap=cmap, interpolation="nearest",
                       norm=make_norm(stretch, vmin, vmax, shown),
                       extent=(-0.5, shown.shape[1] * step - 0.5, -0.5,
                               shown.shape[0] * step - 0.5))
        canvas.figure.colorbar(im, ax=ax)
        ax.set_xlabel("x [pix]")
        ax.set_ylabel("y [pix]")
        if step > 1:
            title = f"{title} (every {step}th pixel)".strip()
    if title:
        ax.set_title(title)
    canvas.redraw()


def _unit_str(unit: u.UnitBase) -> str:
    try:
        return unit.to_string("fits")
    except (ValueError, u.UnitsError):
        return unit.to_string()


def hdu_from_object(obj: Any, name: str = "", compress: Optional[str] = None,
                    quantize: float = 0.0, primary: bool = False) -> Any:
    """Build an HDU from a workspace object (Table, array/Quantity, NDData)."""
    if isinstance(obj, Table):
        if primary:
            raise ParseError("A table cannot be the primary HDU.")
        hdu = fits.table_to_hdu(obj)
        if name:
            hdu.name = name
        return hdu
    header = fits.Header()
    if isinstance(obj, NDData):
        data = obj.data
        if isinstance(obj.meta, Mapping):
            try:
                header.update(obj.meta)
            except (ValueError, TypeError, KeyError):
                pass
        if obj.wcs is not None:
            try:
                header.update(obj.wcs.to_header())
            except Exception:  # noqa: BLE001 - WCS without a FITS representation
                pass
        if obj.unit is not None:
            header["BUNIT"] = _unit_str(obj.unit)
    elif isinstance(obj, u.Quantity):
        data = obj.value
        header["BUNIT"] = _unit_str(obj.unit)
    elif isinstance(obj, np.ndarray):
        data = obj
    else:
        raise ParseError(f"Cannot turn a {type(obj).__name__} into an HDU.")
    data = np.asarray(data)
    if data.dtype.kind not in "biuf":
        raise ParseError(f"Image data of dtype {data.dtype} cannot be stored in FITS.")
    if primary:
        hdu = fits.PrimaryHDU(data, header=header)
    elif compress:
        hdu = fits.CompImageHDU(data, header=header, compression_type=compress,
                                quantize_level=quantize)
    else:
        hdu = fits.ImageHDU(data, header=header)
    if name:
        hdu.name = name
    return hdu


def hdu_to_ndata(hdu: Any) -> NDData:
    if getattr(hdu, "data", None) is None or isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
        raise ParseError("The selected HDU has no image data.")
    header = hdu.header.copy()
    wcs = None
    try:
        w, _ = capture_warnings(WCS, header)
        if any(w.wcs.ctype):
            wcs = w
    except Exception:  # noqa: BLE001 - unreadable WCS keywords: keep the data anyway
        wcs = None
    unit = None
    if "BUNIT" in header:
        try:
            unit = u.Unit(str(header["BUNIT"]), format="fits")
        except (ValueError, TypeError):
            unit = None
    return NDData(np.array(hdu.data), meta=header, wcs=wcs, unit=unit)


def save_hdulist(hdul: fits.HDUList, path: str, overwrite: bool = False, checksum: bool = False,
                 output_verify: str = "exception") -> str:
    """Write via a temporary file, so saving over an open (memory-mapped) file is safe."""
    path = os.path.abspath(need(path, "an output path"))
    if os.path.exists(path) and not overwrite:
        raise ParseError(f"{path} exists; tick 'Overwrite' to replace it.")
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".atadv-", suffix=os.path.basename(path), dir=directory)
    os.close(fd)
    try:
        hdul.writeto(tmp, overwrite=True, checksum=checksum, output_verify=output_verify)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def verify_checksums(path: str) -> Table:
    """CHECKSUM/DATASUM status of every HDU as stored on disk."""
    cols: Dict[str, list] = {k: [] for k in ("No.", "Name", "DATASUM", "CHECKSUM")}
    with fits.open(need(path, "a file path"), checksum=False, memmap=False) as hdul:
        for i, hdu in enumerate(hdul):
            for key, val in zip(cols, (i, hdu.name, CHECK_TEXT[hdu.verify_datasum()],
                                       CHECK_TEXT[hdu.verify_checksum()])):
                cols[key].append(val)
    return Table(cols)


def fitsdiff_report(a: str, b: str, rtol: float = 0.0, atol: float = 0.0,
                    ignore_keywords: str = "") -> Tuple[bool, str]:
    keys = [k.strip().upper() for k in ignore_keywords.replace(";", ",").split(",") if k.strip()]
    diff = fits.FITSDiff(need(a, "file A"), need(b, "file B"), ignore_keywords=keys,
                         rtol=rtol, atol=atol)
    return diff.identical, diff.report()


def verify_report(hdul: fits.HDUList, option: str) -> str:
    try:
        _, warns = capture_warnings(hdul.verify, option)
    except fits.VerifyError as exc:
        return f"Verification FAILED ({option}):\n{exc}"
    return "Verification passed." + ("\n" + "\n".join(warns) if warns else "")


def open_fits(path: str, memmap: bool, lazy: bool) -> Tuple[fits.HDUList, Table]:
    hdul = fits.open(need(path, "a file path"), memmap=memmap, lazy_load_hdus=lazy)
    try:
        return hdul, hdu_overview(hdul)  # touching every header surfaces corruption now
    except Exception:
        hdul.close()
        raise


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
def _close_quietly(hdul: Optional[fits.HDUList]) -> None:
    if hdul is not None:
        try:
            hdul.close()
        except Exception:  # noqa: BLE001
            pass


class FitsPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.hdul: Optional[fits.HDUList] = None
        self.path: Optional[str] = None
        self.dirty = False
        self._holder: List[Optional[fits.HDUList]] = [None]
        self.destroyed.connect(lambda *_: _close_quietly(self._holder[0]))

        self.state = QLabel("No file open")
        self.state.setWordWrap(True)
        self.form.add_widget("state", "State", self.state)
        self.hdu_combo = QComboBox()
        self.hdu_combo.setToolTip("HDU used by the header, image, data and checksum tools")
        self.hdu_combo.currentIndexChanged.connect(lambda _i: self.show_header())
        self.form.add_widget("hdu", "HDU", self.hdu_combo)

        self.overview = self.add_table("HDUs")
        self.header_view = self.add_output("Header")
        self.canvas = self.add_plot("Image")
        self.data_view = self.add_table("Data")
        self.log = self.add_output("Report")

        # -- open / new / close
        sec = Section(self, "File")
        self.open_path = PathEdit("open", "FITS (*.fits *.fit *.fts *.fz *.gz);;All files (*)")
        sec.form.add_widget("path", "Path", self.open_path)
        sec.form.add_check("memmap", "Memory-map", True,
                           "Map the data from disk instead of reading it all (large files)")
        sec.form.add_check("lazy", "Lazy HDU loading", True)
        sec.add_button("Open", lambda sec=sec: self.open_file(sec.form))
        sec.add_button("New (empty primary HDU)", self.new_file)
        sec.add_button("Close", self.close_file)
        self.file_sec = sec

        # -- save
        sec = Section(self, "Save")
        self.save_path = PathEdit("save", "FITS (*.fits *.fit *.fts *.gz);;All files (*)")
        sec.form.add_widget("path", "Path", self.save_path)
        sec.form.add_check("overwrite", "Overwrite", False)
        sec.form.add_check("checksum", "Write CHECKSUM/DATASUM", False)
        sec.form.add_combo("verify", "Output verify", VERIFY_OPTIONS)
        sec.add_button("Save as...", lambda sec=sec: self.save_as(sec.form))
        sec.add_button("Write back to opened file", lambda sec=sec: self.write_back(sec.form),
                       "Replaces the opened file (via a temporary file) and reloads it")
        self.save_sec = sec

        # -- header
        sec = Section(self, "Header")
        sec.form.add_text("search", "Search", tip="Case-insensitive filter on keyword/value/comment")
        sec.form.add_text("key", "Keyword")
        sec.form.add_text("value", "Value", tip="5, 1.5, T/F; wrap in quotes to force a string")
        sec.form.add_text("comment", "Comment")
        sec.add_button("Show header", self.show_header)
        sec.add_button("Set / add card", lambda sec=sec: self.set_card(sec.form))
        sec.add_button("Delete card", lambda sec=sec: self.delete_card(sec.form))
        sec.add_button("Add HISTORY (Value)", lambda sec=sec: self.add_text_card(sec.form, "HISTORY"))
        sec.add_button("Add COMMENT (Value)", lambda sec=sec: self.add_text_card(sec.form, "COMMENT"))
        self.header_sec = sec

        # -- image
        sec = Section(self, "Image preview")
        sec.form.add_text("plane", "Plane", tip="Indices of the leading axes for N-D data, "
                          "e.g. 2 or 1,0 (default: first)")
        sec.form.add_combo("stretch", "Stretch", STRETCHES)
        sec.form.add_combo("cmap", "Colormap", ["gray", "viridis", "magma", "inferno", "plasma",
                                                "cividis", "gray_r"])
        sec.form.add_float("lo", "Low percentile", 0.0, 0.0, 100.0, 2)
        sec.form.add_float("hi", "High percentile", 100.0, 0.0, 100.0, 2)
        sec.form.add_text("vmin", "vmin", tip="Overrides the low percentile")
        sec.form.add_text("vmax", "vmax", tip="Overrides the high percentile")
        sec.add_button("Preview", lambda sec=sec: self.preview(sec.form))
        sec.add_button("Pixel statistics", lambda sec=sec: self.pixel_stats(sec.form))
        self.image_sec = sec

        # -- data transfer
        sec = Section(self, "HDU data <-> workspace")
        sec.form.add_text("name", "Workspace name", "fits_data")
        self.obj_combo = WorkspaceCombo(ws, (Table, np.ndarray, NDData))
        sec.form.add_widget("obj", "Workspace object", self.obj_combo)
        sec.form.add_text("hduname", "New HDU name")
        sec.form.add_combo("compress", "Compression", ["none"] + COMPRESSIONS,
                           tip="Tile-compress image data (CompImageHDU)")
        sec.form.add_float("quantize", "Quantize level", 0.0, 0.0, 1e6, 2,
                           tip="Float images: RICE/HCOMPRESS are lossy (level 0 rounds to integers); "
                           "use GZIP_1/GZIP_2 with 0 for lossless storage")
        sec.add_button("HDU -> Table", lambda sec=sec: self.hdu_to_table(sec.form))
        sec.add_button("HDU -> NDData", lambda sec=sec: self.hdu_to_nddata(sec.form))
        sec.add_button("HDU -> array", lambda sec=sec: self.hdu_to_array(sec.form))
        sec.add_button("Table columns (FITS_rec)", self.show_columns)
        sec.add_button("Append object as new HDU", lambda sec=sec: self.append_hdu(sec.form))
        sec.add_button("Replace selected HDU with object", lambda sec=sec: self.replace_hdu(sec.form))
        sec.add_button("Delete selected HDU", self.delete_hdu)
        self.data_sec = sec

        # -- integrity
        sec = Section(self, "Integrity")
        sec.form.add_combo("verify", "verify() option", VERIFY_OPTIONS, current="fix")
        sec.form.add_check("all", "All HDUs (checksum)", True)
        sec.form.add_widget("other", "Compare with", PathEdit("open"))
        sec.form.add_float("rtol", "rtol", 0.0, 0.0, 1e6, 8)
        sec.form.add_float("atol", "atol", 0.0, 0.0, 1e6, 8)
        sec.form.add_text("ignore", "Ignore keywords", "", "comma-separated, e.g. DATE,CHECKSUM")
        sec.add_button("verify() in-memory file", lambda sec=sec: self.verify_memory(sec.form))
        sec.add_button("Add CHECKSUM + DATASUM", lambda sec=sec: self.add_checksum(sec.form))
        sec.add_button("Verify checksums on disk", self.verify_disk)
        sec.add_button("FITSDiff (opened file vs. other)", lambda sec=sec: self.diff(sec.form))
        self.int_sec = sec

        # -- quick functions
        sec = Section(self, "Quick functions (file on disk)")
        sec.form.add_text("ext", "Extension", "0", "Index or EXTNAME")
        sec.form.add_text("key", "Keyword")
        sec.form.add_text("value", "Value")
        sec.form.add_text("name", "Workspace name", "fits_getdata")
        sec.add_button("getval", lambda sec=sec: self.getval(sec.form))
        sec.add_button("setval (modifies file!)", lambda sec=sec: self.setval(sec.form),
                       "Writes the card straight into the file on disk")
        sec.add_button("getheader", lambda sec=sec: self.getheader(sec.form))
        sec.add_button("getdata -> workspace", lambda sec=sec: self.getdata(sec.form))
        self.quick_sec = sec
        self._refresh()

    # ---- state ---------------------------------------------------------------- #
    def _set_hdul(self, hdul: Optional[fits.HDUList], path: Optional[str], dirty: bool) -> None:
        old = self.hdul
        self.hdul, self.path, self.dirty = hdul, path, dirty
        self._holder[0] = hdul
        if old is not hdul:
            _close_quietly(old)
        self._refresh()

    def _need(self) -> fits.HDUList:
        if self.hdul is None:
            raise ParseError("Open or create a FITS file first.")
        return self.hdul

    def _hdu(self) -> Any:
        hdul = self._need()
        i = self.hdu_combo.currentData()
        if i is None or not 0 <= i < len(hdul):
            raise ParseError("No HDU selected.")
        return hdul[i]

    def _hdu_index(self) -> int:
        self._hdu()
        return int(self.hdu_combo.currentData())

    def _touch(self) -> None:
        self.dirty = True
        self._refresh(keep=self.hdu_combo.currentData())

    def _refresh(self, keep: Optional[int] = None) -> None:
        if keep is None:
            keep = self.hdu_combo.currentData()
        self.hdu_combo.blockSignals(True)
        self.hdu_combo.clear()
        if self.hdul is None:
            self.state.setText("No file open")
            self.overview.set_table(None)
            self.header_view.show_text("")
        else:
            for i, hdu in enumerate(self.hdul):
                self.hdu_combo.addItem(f"{i}: {hdu.name or '-'} ({type(hdu).__name__})", i)
            if keep is not None and 0 <= keep < self.hdu_combo.count():
                self.hdu_combo.setCurrentIndex(keep)
            where = self.path or "(new, unsaved)"
            self.state.setText(f"{where}{'  [modified]' if self.dirty else ''}")
            self.overview.set_table(hdu_overview(self.hdul))
        self.hdu_combo.blockSignals(False)
        if self.hdul is not None:
            self.show_header()

    # ---- file ----------------------------------------------------------------- #
    def open_file(self, f: Any) -> None:
        self._open(need(f.value("path"), "a file path"), f.value("memmap"), f.value("lazy"))

    def _open(self, path: str, mm: bool, lazy: bool) -> None:
        def done(res: Tuple[fits.HDUList, Table]) -> None:
            self._set_hdul(res[0], os.path.abspath(path), False)
            self.set_status(f"Opened {path}")
            self.tabs.setCurrentWidget(self.overview)

        self.run(open_fits, done, path, mm, lazy, busy_text=f"Opening {path}...")

    def new_file(self) -> None:
        self._set_hdul(fits.HDUList([fits.PrimaryHDU()]), None, True)

    def close_file(self) -> None:
        self._set_hdul(None, None, False)

    def _save(self, path: str, f: Any, reopen: bool) -> None:
        hdul = self._need()
        overwrite = True if reopen else f.value("overwrite")
        checksum, verify = f.value("checksum"), f.value("verify")

        mm, lazy = self.file_sec.form.value("memmap"), self.file_sec.form.value("lazy")

        def done(saved: str) -> None:
            self.log.show_text(f"Saved {saved}")
            self.set_status(f"Saved {saved}")
            if reopen:
                self._open(saved, mm, lazy)
            else:
                self.path, self.dirty = saved, False
                self._refresh()

        self.run(save_hdulist, done, hdul, path, overwrite, checksum, verify,
                 busy_text=f"Saving {path}...")

    def save_as(self, f: Any) -> None:
        self._save(need(f.value("path"), "an output path"), f, reopen=False)

    def write_back(self, f: Any) -> None:
        if not self.path:
            raise ParseError("The file has no path yet; use 'Save as...'.")
        self._save(self.path, f, reopen=True)

    # ---- header ----------------------------------------------------------------- #
    def show_header(self) -> None:
        if self.hdul is None or self.hdu_combo.currentData() is None:
            return
        hdu = self.hdul[self.hdu_combo.currentData()]
        self.header_view.show_text(header_text(hdu.header, self.header_sec.form.value("search")))

    def set_card(self, f: Any) -> None:
        hdu = self._hdu()
        raw = need(f.value("key"), "a keyword")
        key = raw if raw.upper().startswith("HIERARCH ") else raw.upper()
        value = parse_header_value(f.value("value"))
        _, warns = capture_warnings(hdu.header.set, key, value, f.value("comment") or None)
        if warns:
            self.log.show_text("\n".join(warns))
        self._touch()

    def delete_card(self, f: Any) -> None:
        hdu = self._hdu()
        key = need(f.value("key"), "a keyword").upper()
        if key not in hdu.header:
            raise ParseError(f"Keyword {key!r} not found in this HDU.")
        del hdu.header[key]
        self._touch()

    def add_text_card(self, f: Any, kind: str) -> None:
        hdu = self._hdu()
        text = need(f.value("value"), "the text")
        (hdu.header.add_history if kind == "HISTORY" else hdu.header.add_comment)(text)
        self._touch()

    # ---- image ------------------------------------------------------------------ #
    def preview(self, f: Any) -> None:
        hdu, idx = self._hdu(), self._hdu_index()
        plane, stretch, cmap = f.value("plane"), f.value("stretch"), f.value("cmap")
        vmin, vmax, lo, hi = f.value("vmin"), f.value("vmax"), f.value("lo"), f.value("hi")

        def work() -> Tuple[np.ndarray, float, float]:
            arr = image_array(hdu, plane)
            a, b = display_limits(arr, vmin, vmax, lo, hi)
            return arr, a, b

        def done(res: Tuple[np.ndarray, float, float]) -> None:
            arr, a, b = res
            plot_image(self.canvas, arr, stretch, a, b, cmap, f"HDU {idx} {hdu.name}")
            self.tabs.setCurrentWidget(self.canvas)

        self.run(work, done, busy_text="Reading pixels...")

    def pixel_stats(self, f: Any) -> None:
        hdu, plane = self._hdu(), f.value("plane")

        def done(text: str) -> None:
            self.log.show_text(text)
            self.tabs.setCurrentWidget(self.log)

        self.run(lambda: stats_text(image_array(hdu, plane), hdu.header), done)

    # ---- HDU <-> workspace -------------------------------------------------------- #
    def hdu_to_table(self, f: Any) -> None:
        hdu, name = self._hdu(), need(f.value("name"), "a workspace name")
        if not isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            raise ParseError("The selected HDU is not a table.")

        def done(table: Table) -> None:
            self.ws.put(name, table)
            self.data_view.set_table(table)
            self.tabs.setCurrentWidget(self.data_view)
            self.set_status(f"Stored table {name!r}")

        self.run(lambda: Table.read(hdu), done)

    def hdu_to_nddata(self, f: Any) -> None:
        nd = hdu_to_ndata(self._hdu())
        self.ws.put(need(f.value("name"), "a workspace name"), nd)
        self.set_status("Stored NDData")

    def hdu_to_array(self, f: Any) -> None:
        hdu = self._hdu()
        if getattr(hdu, "data", None) is None or isinstance(hdu, (fits.BinTableHDU,
                                                                  fits.TableHDU)):
            raise ParseError("The selected HDU has no image data.")
        self.ws.put(need(f.value("name"), "a workspace name"), np.array(hdu.data))
        self.set_status("Stored array")

    def show_columns(self) -> None:
        table = columns_table(self._hdu())
        self.data_view.set_table(table)
        self.tabs.setCurrentWidget(self.data_view)

    def _object_hdu(self, f: Any, primary: bool = False) -> Any:
        comp = f.value("compress")
        return hdu_from_object(self.obj_combo.selected(), f.value("hduname"),
                               None if comp == "none" else comp, f.value("quantize"), primary)

    def append_hdu(self, f: Any) -> None:
        if self.hdul is None:
            self._set_hdul(fits.HDUList([fits.PrimaryHDU()]), None, True)
        hdu = self._object_hdu(f)
        self.hdul.append(hdu)
        self._touch()
        self.hdu_combo.setCurrentIndex(len(self.hdul) - 1)

    def replace_hdu(self, f: Any) -> None:
        old, idx = self._hdu(), self._hdu_index()
        new = self._object_hdu(f, primary=(idx == 0))
        if not f.value("hduname"):
            new.name = old.name
        self.hdul[idx] = new
        self._touch()

    def delete_hdu(self) -> None:
        idx = self._hdu_index()
        del self.hdul[idx]
        self.dirty = True
        self._refresh(keep=max(0, idx - 1))

    # ---- integrity ---------------------------------------------------------------- #
    def verify_memory(self, f: Any) -> None:
        text = verify_report(self._need(), f.value("verify"))
        self.log.show_text(text)
        self.tabs.setCurrentWidget(self.log)
        self._touch()

    def add_checksum(self, f: Any) -> None:
        hdul = self._need()
        targets = list(hdul) if f.value("all") else [self._hdu()]
        for hdu in targets:
            hdu.add_checksum()
        self.log.show_text(f"CHECKSUM/DATASUM added to {len(targets)} HDU(s). "
                           "They are only valid until the header or data changes; tick "
                           "'Write CHECKSUM/DATASUM' when saving to recompute them.")
        self._touch()

    def verify_disk(self) -> None:
        path = need(self.path or "", "an opened file (checksums are verified on disk)")

        def done(table: Table) -> None:
            self.data_view.set_table(table)
            self.log.show_text("\n".join(table.pformat(max_lines=-1)))
            self.tabs.setCurrentWidget(self.data_view)

        self.run(verify_checksums, done, path)

    def diff(self, f: Any) -> None:
        a, b = self.path or "", f.value("other")
        rtol, atol, ign = f.value("rtol"), f.value("atol"), f.value("ignore")

        def done(res: Tuple[bool, str]) -> None:
            self.log.show_text(("IDENTICAL\n\n" if res[0] else "DIFFERENT\n\n") + res[1])
            self.tabs.setCurrentWidget(self.log)

        self.run(fitsdiff_report, done, need(a, "an opened file"), need(b, "a file to compare"),
                 rtol, atol, ign)

    # ---- quick functions ---------------------------------------------------------- #
    def getval(self, f: Any) -> None:
        path, key = need(self.open_path.text(), "a path in 'File'"), need(f.value("key"),
                                                                            "a keyword")
        ext = parse_ext(f.value("ext"))
        self.run(lambda: fits.getval(path, key, **ext),
                 lambda v: self.log.show_text(f"{key} = {v!r}"))

    def setval(self, f: Any) -> None:
        path, key = need(self.open_path.text(), "a path in 'File'"), need(f.value("key"),
                                                                            "a keyword")
        ext, value = parse_ext(f.value("ext")), parse_header_value(f.value("value"))

        def done(_: Any) -> None:
            self.log.show_text(f"Set {key} = {value!r} in {path}")
            if self.path and os.path.samefile(self.path, path):
                self._open(self.path, self.file_sec.form.value("memmap"),
                           self.file_sec.form.value("lazy"))

        self.run(lambda: fits.setval(path, key, value=value, **ext), done)

    def getheader(self, f: Any) -> None:
        path, ext = need(self.open_path.text(), "a path in 'File'"), parse_ext(f.value("ext"))

        def done(h: fits.Header) -> None:
            self.header_view.show_text(header_text(h))
            self.tabs.setCurrentWidget(self.header_view)

        self.run(lambda: fits.getheader(path, **ext), done)

    def getdata(self, f: Any) -> None:
        path, ext = need(self.open_path.text(), "a path in 'File'"), parse_ext(f.value("ext"))
        name = need(f.value("name"), "a workspace name")

        def work() -> Any:
            data = fits.getdata(path, **ext)
            return Table(data) if isinstance(data, fits.FITS_rec) else np.array(data)

        def done(obj: Any) -> None:
            self.ws.put(name, obj)
            if isinstance(obj, Table):
                self.data_view.set_table(obj)
                self.tabs.setCurrentWidget(self.data_view)
            self.set_status(f"Stored {type(obj).__name__} {name!r}")

        self.run(work, done)


SPECS = [ModuleSpec("fits", "FITS files", CATEGORY, lambda ws: FitsPanel(ws),
                    "Open, inspect, edit and save FITS files (headers, images, tables, checksums)")]
