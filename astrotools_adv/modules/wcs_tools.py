"""astropy.wcs: build, transform, inspect, fit, compare and plot world coordinate systems."""
from __future__ import annotations

import os
import re
import tempfile
from typing import Any, List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord, SpectralCoord
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS, WCSSUB_CELESTIAL, WCSSUB_LATITUDE, WCSSUB_LONGITUDE, WCSSUB_SPECTRAL
from astropy.wcs.utils import (
    celestial_frame_to_wcs, fit_wcs_from_points, is_proj_plane_distorted,
    local_partial_pixel_derivatives, proj_plane_pixel_area, proj_plane_pixel_scales,
    wcs_to_celestial_frame,
)
from astropy.wcs import validate as wcs_validate

from ..core.parsing import (ParseError, parse_angle, parse_float, parse_int, parse_skycoord,
                            safe_eval, split_lines)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace
from ._images import ImageSelector, image_data, unique_name, wcs_of
from .visualization_tools import draw_sky_overlays

CATEGORY = "Images"
PROJECTIONS = ["AZP", "SZP", "TAN", "STG", "SIN", "ARC", "ZPN", "ZEA", "AIR", "CYP", "CEA", "CAR",
               "MER", "COP", "COE", "COD", "COO", "SFL", "PAR", "MOL", "AIT", "BON", "PCO", "TSC",
               "CSC", "QSC", "HPX", "XPH"]
PV_DEFAULTS = {**{p: "2_1=45" for p in ("COP", "COE", "COD", "COO", "BON")}, "ZPN": "2_0=0, 2_1=1"}
FRAMES = {"ICRS (RA/Dec)": ("RA", "DEC", "ICRS"), "Galactic (l/b)": ("GLON", "GLAT", None),
          "Ecliptic (lon/lat)": ("ELON", "ELAT", None)}


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def parse_pv(text: str) -> List[Tuple[int, int, float]]:
    """``'2_1=45, 2_2=0'`` -> ``[(2, 1, 45.0), (2, 2, 0.0)]`` (axis_index=value)."""
    out = []
    for tok in re.split(r"[,;\s]+", text.strip()):
        if not tok:
            continue
        m = re.fullmatch(r"(\d+)_(\d+)=(.+)", tok)
        if not m:
            raise ParseError(f"PV entry {tok!r}: expected AXIS_INDEX=VALUE, e.g. 2_1=45.")
        out.append((int(m.group(1)), int(m.group(2)), parse_float(m.group(3), "PV value")))
    return out


def lon_lat_ctype(lon: str, lat: str, proj: str) -> Tuple[str, str]:
    return f"{lon:-<4}-{proj}", f"{lat:-<4}-{proj}"


def _apply_geometry(w: WCS, crval: Tuple[float, float], crpix: Tuple[float, float],
                    scale_arcsec: float, rotation_deg: float, east_left: bool,
                    shape: Optional[Tuple[int, int]], pv_text: str, proj: str) -> WCS:
    if not np.isfinite(scale_arcsec) or scale_arcsec <= 0:
        raise ParseError("Pixel scale must be positive.")
    if not (-90 <= crval[1] <= 90):
        raise ParseError("Reference latitude must be within [-90, 90] degrees.")
    w.wcs.crval = list(crval)
    w.wcs.crpix = list(crpix)
    w.wcs.cunit = ["deg", "deg"]
    s, r = scale_arcsec / 3600.0, np.radians(rotation_deg)
    c, sn = np.cos(r), np.sin(r)
    w.wcs.cd = s * (np.array([[-c, sn], [sn, c]]) if east_left else np.array([[c, sn], [-sn, c]]))
    pv = parse_pv(pv_text or PV_DEFAULTS.get(proj, ""))
    if pv:
        w.wcs.set_pv(pv)
    if shape is not None:
        w.pixel_shape = (int(shape[0]), int(shape[1]))
    try:
        w.wcs.set()
    except Exception as exc:  # noqa: BLE001 - wcslib raises several exception types
        raise ParseError(f"Invalid WCS for {proj}: {str(exc).splitlines()[0] if str(exc) else exc}") from exc
    return w


def build_wcs(proj: str = "TAN", frame: str = "ICRS (RA/Dec)", crval: Tuple[float, float] = (0.0, 0.0),
              crpix: Tuple[float, float] = (1.0, 1.0), scale_arcsec: float = 1.0,
              rotation_deg: float = 0.0, east_left: bool = True,
              shape: Optional[Tuple[int, int]] = None, pv_text: str = "") -> WCS:
    """Celestial 2-D WCS from scratch (CD matrix). ``shape`` is ``(nx, ny)``."""
    if proj not in PROJECTIONS:
        raise ParseError(f"Unknown projection {proj!r}.")
    if frame not in FRAMES:
        raise ParseError(f"Unknown frame {frame!r}.")
    lon, lat, radesys = FRAMES[frame]
    w = WCS(naxis=2)
    w.wcs.ctype = list(lon_lat_ctype(lon, lat, proj))
    if radesys:
        w.wcs.radesys = radesys
    return _apply_geometry(w, crval, crpix, scale_arcsec, rotation_deg, east_left, shape, pv_text, proj)


def build_wcs_from_frame(frame_name: str, proj: str = "TAN", **geometry: Any) -> WCS:
    """Like :func:`build_wcs` but the axes come from ``celestial_frame_to_wcs`` for any named frame."""
    from astropy.coordinates import frame_transform_graph

    if proj not in PROJECTIONS:
        raise ParseError(f"Unknown projection {proj!r}.")
    cls = frame_transform_graph.lookup_name(frame_name.strip().lower())
    if cls is None:
        raise ParseError(f"Unknown frame {frame_name!r} (supported: icrs, fk5, fk4, fk4noeterms, "
                         "galactic, itrs).")
    try:
        w = celestial_frame_to_wcs(cls(), projection=proj)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"No WCS representation for frame {frame_name!r} (supported: icrs, fk5, fk4, "
                         f"fk4noeterms, galactic, itrs): {exc}") from exc
    return _apply_geometry(w, geometry.get("crval", (0.0, 0.0)), geometry.get("crpix", (1.0, 1.0)),
                           geometry.get("scale_arcsec", 1.0), geometry.get("rotation_deg", 0.0),
                           geometry.get("east_left", True), geometry.get("shape"),
                           geometry.get("pv_text", ""), proj)


_CARD_RE = re.compile(r"^\s*([A-Za-z0-9_-]{1,8})\s*=\s*(.*)$")
_CARD_FREE_RE = re.compile(r"^(END|COMMENT|HISTORY|HIERARCH)\b|^$", re.IGNORECASE)


def _standard_card(line: str) -> str:
    """Rewrite ``KEY = value`` (any spacing) as a fixed-format 80-character card."""
    line = line.rstrip("\r\n")
    m = _CARD_RE.match(line)
    if m:
        return f"{m.group(1).upper():<8}= {m.group(2)}".ljust(80)
    if _CARD_FREE_RE.match(line.strip()):
        return line.ljust(80)
    raise ParseError(f"Header line {line.strip()!r} is not a FITS card (expected 'KEYWORD = value').")


def wcs_from_header_text(text: str, relax: bool = True, key: str = " ") -> WCS:
    if not text.strip():
        raise ParseError("Header text is empty.")
    cards = [_standard_card(ln) for ln in text.strip().splitlines()]
    try:
        header = fits.Header.fromstring("\n".join(cards), sep="\n")
        return WCS(header, relax=relax, key=key or " ")
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Cannot build a WCS from this header: {exc}") from exc


def wcs_from_fits(path: str, ext: int = 0, relax: bool = True, key: str = " ") -> WCS:
    try:
        with fits.open(path) as hdul:
            return WCS(hdul[ext].header, fobj=hdul, relax=relax, key=key or " ")
    except (OSError, IndexError, KeyError) as exc:
        raise ParseError(f"Cannot read WCS from {os.path.basename(path)}[{ext}]: {exc}") from exc
    except ValueError as exc:
        raise ParseError(f"Invalid WCS in {os.path.basename(path)}: {exc}") from exc


def rotation_angle(w: WCS) -> float:
    """Angle of the +y pixel axis from north towards east, degrees in (-180, 180]."""
    m = w.pixel_scale_matrix
    return float(np.degrees(np.arctan2(m[0, 1], m[1, 1])))


def parity_east_left(w: WCS) -> bool:
    return bool(np.linalg.det(w.pixel_scale_matrix) < 0)


def wcs_summary(w: WCS) -> str:
    wc = w.wcs
    lines = [f"WCS name   : {wc.name or '-'}",
             f"axes       : {w.naxis} (pixel shape {w.pixel_shape})",
             f"CTYPE      : {list(wc.ctype)}", f"CRVAL      : {list(wc.crval)}",
             f"CRPIX      : {list(wc.crpix)}", f"CUNIT      : {[str(x) for x in wc.cunit]}"]
    if wc.has_cd():
        lines.append(f"CD         : {wc.cd.tolist()}")
    else:
        lines += [f"CDELT      : {list(wc.cdelt)}", f"PC         : {wc.get_pc().tolist()}"]
    if w.has_celestial:
        try:
            lines.append(f"frame      : {wcs_to_celestial_frame(w).__class__.__name__}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"frame      : unavailable ({exc})")
        if wc.lng >= 0 and w.naxis >= 2:
            try:
                scales = np.asarray(proj_plane_pixel_scales(w.celestial)) * 3600.0
                lines += [f"pixel scale: {scales[0]:.6g} x {scales[1]:.6g} arcsec/pix",
                          f"pixel area : {proj_plane_pixel_area(w.celestial) * 3600.0 ** 2:.6g} arcsec^2"]
                if w.naxis == 2:
                    lines += [f"rotation   : {rotation_angle(w):.6g} deg (N through E)",
                              f"parity     : {'east left' if parity_east_left(w) else 'east right'}"]
            except Exception as exc:  # noqa: BLE001
                lines.append(f"pixel scale: unavailable ({exc})")
        lines.append(f"distortion : SIP={w.sip is not None}  lookup={w.cpdis1 is not None or w.det2im1 is not None}")
    lines.append(f"physical   : {w.world_axis_physical_types}")
    return "\n".join(lines)


def header_text(w: WCS, relax: bool = True, key: Optional[str] = None) -> str:
    try:
        return w.to_header(relax=relax, key=key).tostring(sep="\n", padding=False)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Cannot write header: {exc}") from exc


def points_from_text(text: str, n: int) -> np.ndarray:
    """Lines of ``n`` numbers each -> array ``(N, n)``."""
    rows = []
    for ln in split_lines(text):
        parts = [p for p in re.split(r"[\s,;]+", ln) if p]
        if len(parts) != n:
            raise ParseError(f"Line {ln!r}: expected {n} numbers.")
        rows.append([parse_float(p, "coordinate") for p in parts])
    if not rows:
        raise ParseError("No points given.")
    return np.asarray(rows, dtype=float)


def points_from_table(table: Table, cols: List[str], n: int) -> np.ndarray:
    if len(cols) != n:
        raise ParseError(f"Give {n} column names.")
    missing = [c for c in cols if c not in table.colnames]
    if missing:
        raise ParseError(f"Table has no column(s) {missing}.")
    if len(table) == 0:
        raise ParseError("Table is empty.")
    out = []
    for c in cols:
        col = table[c]
        out.append(np.asarray(col.value if hasattr(col, "value") else col, dtype=float))
    return np.column_stack(out)


def axis_names(w: WCS) -> List[str]:
    names, seen = [], {}
    for i, ct in enumerate(w.wcs.ctype):
        base = (str(ct).split("-")[0] or f"world{i}").lower()
        seen[base] = seen.get(base, 0) + 1
        names.append(base if seen[base] == 1 else f"{base}{seen[base]}")
    return names


def transform_points(w: WCS, pts: np.ndarray, direction: str, origin: int = 0, method: str = "all",
                     tolerance: float = 1e-6, maxiter: int = 20) -> np.ndarray:
    """``direction``: 'pix2world' | 'world2pix'; ``method``: 'all' (with distortion) | 'wcs' (core only)."""
    if pts.ndim != 2 or pts.shape[1] != w.naxis:
        raise ParseError(f"Points must have {w.naxis} columns for this {w.naxis}-axis WCS.")
    if origin not in (0, 1):
        raise ParseError("Origin must be 0 or 1.")
    try:
        if direction == "pix2world":
            fn = w.all_pix2world if method == "all" else w.wcs_pix2world
            return np.asarray(fn(pts, origin))
        if method == "all":
            return np.asarray(w.all_world2pix(pts, origin, tolerance=tolerance, maxiter=maxiter,
                                              quiet=False))
        return np.asarray(w.wcs_world2pix(pts, origin))
    except ParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - NoConvergence, InvalidTransform, ...
        raise ParseError(f"Transformation failed: {exc}") from exc


def highlevel_transform(w: WCS, text: str, direction: str) -> Table:
    """High-level API for celestial (SkyCoord) and 1-D spectral (SpectralCoord) WCS."""
    try:
        w.wcs.set()
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Invalid WCS: {exc}") from exc
    celestial = w.naxis == 2 and w.has_celestial
    spectral = w.naxis == 1 and w.has_spectral
    if not (celestial or spectral):
        raise ParseError("High-level conversion supports 2-D celestial and 1-D spectral WCS; "
                         "use the low-level method for this WCS.")
    lines = split_lines(text)
    if not lines:
        raise ParseError("No points given.")
    try:
        if direction == "pix2world":
            pts = points_from_text(text, w.naxis)
            if celestial:
                sc = w.pixel_to_world(pts[:, 0], pts[:, 1])
                return Table({"x": pts[:, 0], "y": pts[:, 1], "lon_deg": sc.data.lon.deg,
                              "lat_deg": sc.data.lat.deg, "frame": [sc.frame.name] * len(pts)})
            sp = w.pixel_to_world(pts[:, 0])
            return Table({"pix": pts[:, 0], "value": sp.value, "unit": [str(sp.unit)] * len(pts)})
        if celestial:
            frame = wcs_to_celestial_frame(w)
            x, y = [], []
            for ln in lines:
                px = w.world_to_pixel(parse_skycoord(ln, frame=frame))
                x.append(float(px[0]))
                y.append(float(px[1]))
            return Table({"x": x, "y": y})
        vals = []
        for ln in lines:
            q = u.Quantity(ln) if re.search(r"[A-Za-z]", ln) else float(ln) * u.Unit(w.wcs.cunit[0])
            vals.append(float(w.world_to_pixel(SpectralCoord(q))))
        return Table({"pix": vals})
    except ParseError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"High-level transformation failed: {exc}") from exc


def apply_operation(w: WCS, op: str, arg: str) -> WCS:
    """Slice / sub / swapaxes / reorient / dropaxis / rename on a copy of ``w``."""
    try:
        if op == "slice":
            if not arg.strip():
                raise ParseError("Slice is empty (e.g. '10:50, 20:60').")
            return w.slice(safe_eval(f"s_[{arg}]", {"s_": np.s_}))
        if op == "sub":
            keys = {"celestial": WCSSUB_CELESTIAL, "spectral": WCSSUB_SPECTRAL,
                    "longitude": WCSSUB_LONGITUDE, "latitude": WCSSUB_LATITUDE}
            toks = [t for t in re.split(r"[\s,;]+", arg.strip()) if t]
            if not toks:
                raise ParseError("Give axes (1-based) or celestial/spectral/longitude/latitude.")
            axes = [keys[t.lower()] if t.lower() in keys else parse_int(t, "axis") for t in toks]
            return w.sub(axes)
        if op == "swapaxes":
            a, b = (parse_int(t, "axis") for t in re.split(r"[\s,;]+", arg.strip()) if t)
            return w.swapaxes(a, b)
        if op == "reorient_celestial_first":
            return w.reorient_celestial_first()
        if op == "dropaxis":
            return w.dropaxis(parse_int(arg, "axis"))
        if op == "rename":
            new = w.deepcopy()
            new.wcs.name = arg.strip()
            return new
        if op == "copy":
            return w.deepcopy()
    except ParseError:
        raise
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise ParseError(f"{op} failed: {exc}") from exc
    raise ParseError(f"Unknown operation {op!r}.")


def validate_wcs(w: WCS) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "wcs.fits")
        hdr = w.to_header(relax=True)
        fits.PrimaryHDU(data=np.zeros((2,) * w.naxis, dtype=np.uint8), header=hdr).writeto(path)
        result = wcs_validate(path)
    return str(result) if len(result) else "(no WCS validation messages)"


def fit_wcs(x: np.ndarray, y: np.ndarray, sky: SkyCoord, projection: str = "TAN",
            sip_degree: int = 0, proj_point: Any = "center") -> Tuple[WCS, Table]:
    n = len(x)
    need = max(3, (sip_degree + 1) * (sip_degree + 2) // 2 + 3 if sip_degree else 3)
    if n < need:
        raise ParseError(f"Need at least {need} points, got {n}.")
    try:
        w = fit_wcs_from_points((x, y), sky, proj_point=proj_point, projection=projection,
                                sip_degree=sip_degree or None)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"WCS fit failed: {exc}") from exc
    px, py = w.world_to_pixel(sky)
    pred = w.pixel_to_world(x, y)
    res = Table({"x": x, "y": y, "dx_pix": px - x, "dy_pix": py - y,
                 "sep_arcsec": pred.separation(sky).arcsec})
    return w, res


def compare_wcs_objects(a: WCS, b: WCS, shape_a: Optional[Tuple[int, int]] = None, n: int = 21,
                        tolerance: float = 0.0) -> str:
    lines = [f"core structures equal (WCS.compare): {a.wcs.compare(b.wcs, tolerance=tolerance)}",
             f"ctype A / B : {list(a.wcs.ctype)} / {list(b.wcs.ctype)}"]
    if a.naxis != 2 or b.naxis != 2 or not (a.has_celestial and b.has_celestial):
        return "\n".join(lines + ["(grid comparison needs two 2-D celestial WCS)"])
    sa, sb = np.asarray(proj_plane_pixel_scales(a)) * 3600, np.asarray(proj_plane_pixel_scales(b)) * 3600
    lines.append(f"pixel scale A / B (arcsec): {sa[0]:.6g} / {sb[0]:.6g}  (ratio {sa[0] / sb[0]:.6g})")
    lines.append(f"rotation A / B (deg): {rotation_angle(a):.6g} / {rotation_angle(b):.6g}")
    shape = shape_a or a.pixel_shape
    if shape is None:
        return "\n".join(lines + ["(give an image shape to compare pixel grids)"])
    gx, gy = np.meshgrid(np.linspace(0, shape[0] - 1, n), np.linspace(0, shape[1] - 1, n))
    sky = a.pixel_to_world(gx.ravel(), gy.ravel())
    bx, by = b.world_to_pixel(sky)
    shift = np.hypot(bx - gx.ravel(), by - gy.ravel())
    shift = shift[np.isfinite(shift)]
    lines.append(f"grid {n}x{n} over {shape[0]}x{shape[1]} px: A pixel -> B pixel offset "
                 f"mean {shift.mean():.6g}, max {shift.max():.6g} px" if shift.size
                 else "grid comparison: no finite points")
    if b.pixel_shape is not None:
        inside = (bx >= -0.5) & (bx <= b.pixel_shape[0] - 0.5) & (by >= -0.5) & (by <= b.pixel_shape[1] - 0.5)
        lines.append(f"fraction of A's grid inside B's footprint: {np.mean(inside):.3f}")
    return "\n".join(lines)


def draw_wcs_plot(canvas: Any, w: WCS, data: Optional[np.ndarray], shape: Tuple[int, int],
                  grid: bool = True, overlay_frame: str = "none", points: str = "", circles: str = "",
                  cmap: str = "gray") -> None:
    """GUI-thread drawing on a WCSAxes (extra WCS axes sliced at 0)."""
    from ._images import nice_limits

    canvas.figure.clear()
    slices = ("x", "y") + (0,) * (w.naxis - 2) if w.naxis > 2 else None
    ax = canvas.figure.add_subplot(111, projection=w, slices=slices)
    if data is None:
        data = np.zeros((shape[1], shape[0]))
        vmin, vmax = 0.0, 1.0
    else:
        vmin, vmax = nice_limits(data)
    ax.imshow(data, origin="lower", cmap=cmap, vmin=vmin, vmax=vmax)
    if grid:
        ax.coords.grid(True, color="white", ls=":", alpha=0.8)
    if overlay_frame != "none":
        ov = ax.get_coords_overlay(overlay_frame)
        ov.grid(color="cyan", ls="--", alpha=0.7)
    if points.strip() or circles.strip():
        draw_sky_overlays(ax, points, circles)
    canvas.redraw()


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class WcsBuilderPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("source", "Source", ["scratch", "celestial frame", "header text", "FITS file",
                                         "workspace image"])
        f.add_combo("proj", "Projection", PROJECTIONS, "scratch: celestial projection code",
                    current="TAN")
        f.add_combo("frame", "Frame", list(FRAMES))
        f.add_text("fname", "Frame name", "galactic",
                   "'celestial frame' source: icrs, fk5, fk4, fk4noeterms, galactic or itrs")
        f.add_text("crval", "CRVAL (lon lat)", "150.0 2.0", "reference sky position; angles allowed")
        f.add_text("crpix", "CRPIX (x y)", "50.5 50.5", "FITS 1-based reference pixel")
        f.add_float("scale", "Pixel scale (arcsec)", 1.0, 1e-9, 1e9, 6)
        f.add_float("rot", "Rotation (deg)", 0.0, -360.0, 360.0, 4, "angle of +y from north through east")
        f.add_check("east_left", "East left", True, "standard sky orientation (RA increases to the left)")
        f.add_text("shape", "Image size (nx ny)", "100 100", "sets pixel_shape; empty for none")
        f.add_text("pv", "PV parameters", "", "AXIS_INDEX=VALUE list; defaults for conic/BON/ZPN")
        f.add_multiline("header", "Header text", "", "FITS header cards, one per line", 120)
        f.add_text("path", "FITS path", "", "path of a FITS file")
        f.add_int("ext", "HDU", 0, 0, 999)
        f.add_check("relax", "relax", True, "accept non-standard WCS keywords")
        f.add_combo("key", "Alt key", [" ", *"ABCDEFGHIJKLMNOPQRSTUVWXYZ"], "alternate WCS key")
        self.img = ImageSelector(ws)
        f.add_widget("img", "Workspace image", self.img)
        f.add_text("name", "Store as", "wcs")
        self.out = self.add_output("Summary")
        self.hdr = self.add_output("Header")
        self.add_button("Build WCS", self.build)
        f.fields["proj"].currentTextChanged.connect(lambda p: f.set_value("pv", PV_DEFAULTS.get(p, "")))

    def build(self) -> None:
        self.guard(self._build)

    def _build(self) -> None:
        v, src = self.form, self.form.value("source")
        if src in ("scratch", "celestial frame"):
            crval = [parse_angle(t, u.deg, "CRVAL").deg for t in v.value("crval").replace(",", " ").split()]
            crpix = [parse_float(t, "CRPIX") for t in v.value("crpix").replace(",", " ").split()]
            if len(crval) != 2 or len(crpix) != 2:
                raise ParseError("CRVAL and CRPIX need two values each.")
            shp = [parse_int(t, "size") for t in v.value("shape").replace(",", " ").split()]
            if shp and (len(shp) != 2 or min(shp) < 1):
                raise ParseError("Image size needs two positive integers.")
            geometry = dict(crval=tuple(crval), crpix=tuple(crpix), scale_arcsec=v.value("scale"),
                            rotation_deg=v.value("rot"), east_left=v.value("east_left"),
                            shape=tuple(shp) if shp else None, pv_text=v.value("pv"))
            if src == "scratch":
                w = build_wcs(v.value("proj"), v.value("frame"), **geometry)
            else:
                w = build_wcs_from_frame(v.value("fname"), v.value("proj"), **geometry)
        elif src == "header text":
            w = wcs_from_header_text(v.value("header"), v.value("relax"), v.value("key"))
        elif src == "FITS file":
            if not v.value("path"):
                raise ParseError("Give a FITS path.")
            w = wcs_from_fits(v.value("path"), v.value("ext"), v.value("relax"), v.value("key"))
        else:
            w = wcs_of(self.img.obj())
            if w is None:
                raise ParseError("The selected workspace image has no WCS.")
            w = w.deepcopy()
        name = self.ws.put(unique_name(self.ws, v.value("name") or "wcs"), w)
        note = ""
        if not any(w.wcs.ctype):
            note = ("Note: the source has no WCS keywords (CTYPE is empty), so this is the default "
                    "linear WCS.\n\n")
        self.out.show_text(f"stored as {name!r}\n\n{note}{wcs_summary(w)}")
        self.hdr.show_text(header_text(w, v.value("relax")))


class _WcsPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.wcs_combo = WorkspaceCombo(ws, WCS)
        self.form.add_widget("wcs", "WCS", self.wcs_combo)

    def wcs(self) -> WCS:
        return self.wcs_combo.selected()


class TransformPanel(_WcsPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("dir", "Direction", [("pixel -> world", "pix2world"), ("world -> pixel", "world2pix")])
        f.add_combo("api", "Method", ["all_*2* (with distortion)", "wcs_*2* (core only)",
                                     "high-level (SkyCoord / SpectralCoord)"])
        f.add_combo("origin", "Origin", ["0", "1"], "0: first pixel is 0 (numpy); 1: FITS convention")
        f.add_multiline("pts", "Points", "50 50\n10 20\n100 100",
                        "one point per line (naxis numbers); high-level world->pixel accepts sky text", 110)
        f.add_check("use_table", "Use workspace table", False)
        self.table_combo = WorkspaceCombo(ws, Table)
        f.add_widget("table", "Table", self.table_combo)
        f.add_text("cols", "Columns", "x, y", "column names, one per WCS axis")
        f.add_float("tol", "Tolerance", 1e-6, 1e-15, 1.0, 12, "all_world2pix iteration tolerance (pixels)")
        f.add_int("maxiter", "Max iterations", 20, 1, 1000)
        f.add_text("name", "Store as", "wcs_points")
        self.view = self.add_table("Result")
        self.out = self.add_output("Info")
        self.add_button("Transform", self.go)

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v, w = self.form, self.wcs()
        direction, api = v.value("dir"), v.value("api")
        origin = int(v.value("origin"))
        if api.startswith("high"):
            if v.value("use_table"):
                raise ParseError("The high-level method reads points from the text box only.")
            if origin != 0:
                raise ParseError("High-level methods always use 0-based pixel origin.")
            table = highlevel_transform(w, v.value("pts"), direction)
        else:
            if v.value("use_table"):
                cols = [c.strip() for c in v.value("cols").split(",") if c.strip()]
                pts = points_from_table(self.table_combo.selected(), cols, w.naxis)
            else:
                pts = points_from_text(v.value("pts"), w.naxis)
            res = transform_points(w, pts, direction, origin, "all" if api.startswith("all") else "wcs",
                                   v.value("tol"), v.value("maxiter"))
            in_names = [f"pix{i}" for i in range(w.naxis)] if direction == "pix2world" else axis_names(w)
            out_names = axis_names(w) if direction == "pix2world" else [f"pix{i}" for i in range(w.naxis)]
            table = Table()
            for i, n in enumerate(in_names):
                table[f"in_{n}"] = pts[:, i]
            for i, n in enumerate(out_names):
                table[n] = res[:, i]
        self.ws.put(unique_name(self.ws, v.value("name") or "wcs_points"), table)
        self.view.set_table(table)
        self.out.show_text(f"{len(table)} point(s) converted; NaN results: "
                           f"{int(sum(np.isnan(np.asarray(table[c], float)).sum() for c in table.colnames if table[c].dtype.kind == 'f'))}")


class InspectPanel(_WcsPanel):
    OPS = ["slice", "sub", "swapaxes", "reorient_celestial_first", "dropaxis", "rename", "copy"]

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("op", "Operation", self.OPS, "creates a new WCS in the workspace")
        f.add_text("arg", "Argument", "10:50, 20:60",
                   "slice: numpy-order view; sub: 1,2 or celestial; swapaxes: 'i j'; dropaxis: i; rename: name")
        f.add_text("pix", "Pixel (x y)", "50 50", "local derivative position (0-based)")
        f.add_check("relax", "relax header", True)
        f.add_text("name", "Store as", "wcs_new")
        self.out = self.add_output("Info")
        self.hdr = self.add_output("Header")
        self.high = self.add_output("High-level API")
        self.add_button("Info", self.info)
        self.add_button("Validate", self.validate)
        self.add_button("Local derivatives", self.derivs)
        self.add_button("Apply operation", self.apply)

    def info(self) -> None:
        def go() -> None:
            w = self.wcs()
            self.out.show_text(wcs_summary(w))
            self.hdr.show_text(header_text(w, self.form.value("relax")))
            lines = [f"pixel_n_dim / world_n_dim : {w.pixel_n_dim} / {w.world_n_dim}",
                     f"world_axis_physical_types : {w.world_axis_physical_types}",
                     f"world_axis_units          : {w.world_axis_units}",
                     f"world_axis_names          : {w.world_axis_names}",
                     f"pixel_axis_names          : {w.pixel_axis_names}",
                     f"array_shape               : {w.array_shape}",
                     f"pixel_bounds              : {w.pixel_bounds}",
                     f"axis_correlation_matrix   :\n{w.axis_correlation_matrix}",
                     f"axis types                : {w.get_axis_types()}"]
            try:
                lines.append(f"world_axis_object_classes : {list(w.world_axis_object_classes)}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"world_axis_object_classes : unavailable ({exc})")
            if w.pixel_shape is not None and w.has_celestial:
                try:
                    lines.append(f"footprint (deg):\n{w.celestial.calc_footprint(axes=w.pixel_shape[:2])}")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"footprint unavailable: {exc}")
            if w.naxis == 2 and w.has_celestial:
                lines.append(f"proj-plane distorted: {is_proj_plane_distorted(w)}")
                try:
                    lines.append(f"frame: {wcs_to_celestial_frame(w)!r}")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"frame unavailable: {exc}")
            self.high.show_text("\n".join(lines))
        self.guard(go)

    def validate(self) -> None:
        self.guard(lambda: self.run(lambda w=self.wcs(): validate_wcs(w), self.out.show_text))

    def derivs(self) -> None:
        def go() -> None:
            w = self.wcs()
            pix = points_from_text(self.form.value("pix"), w.naxis)[0]
            try:
                mat = local_partial_pixel_derivatives(w, *pix)
            except Exception as exc:  # noqa: BLE001
                raise ParseError(f"Cannot compute derivatives: {exc}") from exc
            self.out.show_text(f"d(world)/d(pixel) at {pix.tolist()}  (rows: world axes)\n{np.asarray(mat)}")
        self.guard(go)

    def apply(self) -> None:
        def go() -> None:
            new = apply_operation(self.wcs(), self.form.value("op"), self.form.value("arg"))
            name = self.ws.put(unique_name(self.ws, self.form.value("name") or "wcs_new"), new)
            self.out.show_text(f"stored as {name!r}\n\n{wcs_summary(new)}")
        self.guard(go)


class FitPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_multiline("pts", "Points", "", "'x y ra dec' per line (x,y 0-based pixels; sky as deg or "
                        "sexagesimal)", 150)
        f.add_check("use_table", "Use workspace table", False)
        self.table_combo = WorkspaceCombo(ws, Table)
        f.add_widget("table", "Table", self.table_combo)
        f.add_text("cols", "Columns", "x, y, ra, dec", "x, y, lon, lat (degrees)")
        f.add_combo("proj", "Projection", PROJECTIONS, current="TAN")
        f.add_int("sip", "SIP degree", 0, 0, 5, "0: no distortion terms")
        f.add_text("pp", "Projection point", "center", "'center' or 'ra dec'")
        f.add_text("name", "Store as", "fitted_wcs")
        self.view = self.add_table("Residuals")
        self.out = self.add_output("Result")
        self.add_button("Fit WCS", self.go)

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v = self.form
        if v.value("use_table"):
            cols = [c.strip() for c in v.value("cols").split(",") if c.strip()]
            arr = points_from_table(self.table_combo.selected(), cols, 4)
            x, y = arr[:, 0], arr[:, 1]
            sky = SkyCoord(arr[:, 2] * u.deg, arr[:, 3] * u.deg)
        else:
            lines = split_lines(v.value("pts"))
            if not lines:
                raise ParseError("No points given.")
            xs, ys, scs = [], [], []
            for ln in lines:
                parts = ln.replace(",", " ").split(None, 2)
                if len(parts) != 3:
                    raise ParseError(f"Line {ln!r}: expected 'x y ra dec'.")
                xs.append(parse_float(parts[0], "x"))
                ys.append(parse_float(parts[1], "y"))
                scs.append(parse_skycoord(parts[2]))
            x, y, sky = np.asarray(xs), np.asarray(ys), SkyCoord(scs)
        pp = v.value("pp")
        proj_point: Any = "center" if pp.lower() == "center" else parse_skycoord(pp)
        w, res = fit_wcs(x, y, sky, v.value("proj"), v.value("sip"), proj_point)
        name = self.ws.put(unique_name(self.ws, v.value("name") or "fitted_wcs"), w)
        self.view.set_table(res)
        rms = float(np.sqrt(np.mean(np.square(res["sep_arcsec"]))))
        self.out.show_text(f"stored as {name!r}\nresidual rms: {rms:.4g} arcsec "
                           f"({np.sqrt(np.mean(res['dx_pix'] ** 2 + res['dy_pix'] ** 2)):.4g} pix)\n\n"
                           f"{wcs_summary(w)}")


class ComparePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.a = WorkspaceCombo(ws, WCS)
        self.b = WorkspaceCombo(ws, WCS)
        f.add_widget("a", "WCS A", self.a)
        f.add_widget("b", "WCS B", self.b)
        f.add_text("shape", "Image A size (nx ny)", "", "empty: use A's pixel_shape")
        f.add_int("n", "Grid points per side", 21, 2, 200)
        f.add_float("tol", "Tolerance", 0.0, 0.0, 1.0, 12, "WCS.compare tolerance")
        self.out = self.add_output("Comparison")
        self.add_button("Compare", self.go)

    def go(self) -> None:
        def run() -> None:
            shp = [parse_int(t, "size") for t in self.form.value("shape").replace(",", " ").split()]
            if shp and (len(shp) != 2 or min(shp) < 1):
                raise ParseError("Image size needs two positive integers.")
            self.out.show_text(compare_wcs_objects(self.a.selected(), self.b.selected(),
                                                   tuple(shp) if shp else None, self.form.value("n"),
                                                   self.form.value("tol")))
        self.guard(run)


class PlotPanel(_WcsPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.img = ImageSelector(ws)
        f.add_widget("img", "Image", self.img)
        f.add_check("use_img", "Use image data", True, "off: blank frame from the size below")
        f.add_text("shape", "Frame size (nx ny)", "100 100")
        f.add_check("grid", "Coordinate grid", True)
        f.add_combo("overlay", "Overlay frame", ["none", "galactic", "fk5", "icrs", "fk4"],
                    "second coordinate grid in another frame")
        f.add_combo("cmap", "Colormap", ["gray", "viridis", "magma", "inferno"])
        f.add_multiline("points", "Sky points", "", "one coordinate per line", 60)
        f.add_multiline("circles", "Sky circles", "", "'ra dec | radius' per line", 60)
        self.plot = self.add_plot("WCS plot")
        self.add_button("Plot", self.go)
        self.add_button("Save PNG...", self.save)

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v, w = self.form, self.wcs()
        if w.naxis < 2 or not w.has_celestial:
            raise ParseError("The plot needs a WCS with a celestial axis pair.")
        data = None
        if v.value("use_img") and self.img.has_selection():
            data = image_data(self.img.obj())
            if data.ndim != 2:
                raise ParseError("The image must be 2-D.")
            shape = (data.shape[1], data.shape[0])
        else:
            shp = [parse_int(t, "size") for t in v.value("shape").replace(",", " ").split()]
            if len(shp) != 2 or min(shp) < 1:
                raise ParseError("Frame size needs two positive integers.")
            shape = (shp[0], shp[1])
        draw_wcs_plot(self.plot, w, data, shape, v.value("grid"), v.value("overlay"),
                      v.value("points"), v.value("circles"), v.value("cmap"))

    def save(self) -> None:
        def go() -> None:
            path = self.ask_save_path("Save PNG", "PNG (*.png)", "wcs.png")
            if path:
                self.plot.save(path)
        self.guard(go)


def _spec(key: str, title: str, cls: type, desc: str) -> ModuleSpec:
    return ModuleSpec(key, title, CATEGORY, lambda ws: cls(ws), desc)


SPECS = [
    _spec("wcs_builder", "WCS builder", WcsBuilderPanel, "Create a WCS from scratch, a header, a file or an image"),
    _spec("wcs_transform", "WCS transform", TransformPanel, "Pixel <-> world conversion of point lists"),
    _spec("wcs_inspect", "WCS inspector", InspectPanel, "Scales, distortion, footprint, validation, slice/sub/swap"),
    _spec("wcs_fit", "WCS fit", FitPanel, "fit_wcs_from_points with optional SIP"),
    _spec("wcs_compare", "WCS compare", ComparePanel, "Compare two WCS and their pixel grids"),
    _spec("wcs_plot", "WCS plot", PlotPanel, "WCSAxes with grids and overlays"),
]
