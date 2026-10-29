"""Dedicated, form-based panels for the most used astroquery services.

Every panel is a list of :class:`Query` definitions; ``Query.call`` receives the
already parsed values and a timeout and talks to the service through
``FACTORIES`` (so tests can substitute offline fakes). All services are
imported lazily, only when a query actually runs. Less common services are
available in the *Astroquery Browser*.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time
from PyQt5.QtWidgets import QComboBox, QLabel, QStackedWidget, QVBoxLayout, QWidget

from ..core.parsing import ParseError, parse_quantity, parse_skycoord, safe_eval
from ..core.registry import ModuleSpec
from ..core.widgets import ParamForm, WorkspaceCombo
from ..core.workspace import Workspace
from .astroquery_generic import QueryPanel, set_timeout

# --------------------------------------------------------------------------- #
# Service factories (lazy imports; replaceable in tests)
# --------------------------------------------------------------------------- #
def _simbad(timeout: float, row_limit: Optional[int] = None) -> Any:
    from astroquery.simbad import SimbadClass
    return SimbadClass(ROW_LIMIT=row_limit, timeout=timeout)


def _vizier(timeout: float, **kw: Any) -> Any:
    from astroquery.vizier import VizierClass
    return VizierClass(timeout=timeout, **kw)


def _horizons(timeout: float, **kw: Any) -> Any:
    from astroquery.jplhorizons import HorizonsClass
    obj = HorizonsClass(**kw)
    set_timeout(obj, timeout)
    return obj


def _global(module: str, name: str) -> Callable[..., Any]:
    def factory(timeout: float, **_kw: Any) -> Any:
        import importlib
        obj = getattr(importlib.import_module(module), name)
        set_timeout(obj, timeout)
        return obj
    return factory


def _gaia(timeout: float, row_limit: Optional[int] = None) -> Any:
    from astroquery.gaia import Gaia
    if row_limit is not None:
        Gaia.ROW_LIMIT = row_limit
    return Gaia


FACTORIES: Dict[str, Callable[..., Any]] = {
    "simbad": _simbad,
    "vizier": _vizier,
    "gaia": _gaia,
    "horizons": _horizons,
    "ned": _global("astroquery.ipac.ned", "Ned"),
    "mast_obs": _global("astroquery.mast", "Observations"),
    "mast_cat": _global("astroquery.mast", "Catalogs"),
    "sdss": _global("astroquery.sdss", "SDSS"),
    "skyview": _global("astroquery.skyview", "SkyView"),
    "irsa_dust": _global("astroquery.ipac.irsa.irsa_dust", "IrsaDust"),
    "mpc": _global("astroquery.mpc", "MPC"),
    "sbdb": _global("astroquery.jplsbdb", "SBDB"),
    "nea": _global("astroquery.ipac.nexsci.nasa_exoplanet_archive", "NasaExoplanetArchive"),
    "xmatch": _global("astroquery.xmatch", "XMatch"),
    "svo": _global("astroquery.svo_fps", "SvoFps"),
    "splatalogue": _global("astroquery.splatalogue", "Splatalogue"),
    "nist": _global("astroquery.nist", "Nist"),
}


def service(name: str, timeout: float, **kw: Any) -> Any:
    return FACTORIES[name](timeout, **kw)


# --------------------------------------------------------------------------- #
# Field / query declarations and parsing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = "text"   # text lines kv coord position quantity int float bool combo table
    default: Any = ""
    tip: str = ""
    unit: Optional[str] = None            # quantity: default / expected unit
    choices: Tuple[str, ...] = ()
    required: bool = False
    lo: int = 0
    hi: int = 10**9
    editable: bool = False                # combo: allow free text


@dataclass(frozen=True)
class Query:
    key: str
    label: str
    fields: Tuple[Field, ...]
    call: Callable[[Dict[str, Any], float], Any]
    help: str = ""


_RA_NAMES = ("ra", "ra_icrs", "raj2000", "_raj2000", "ra_deg", "ra_j2000")
_DEC_NAMES = ("dec", "de_icrs", "dej2000", "_dej2000", "dec_deg", "dec_j2000", "decl", "de")


def find_radec_columns(table: Table) -> Tuple[str, str]:
    lower = {c.lower(): c for c in table.colnames}
    ra = next((lower[n] for n in _RA_NAMES if n in lower), None)
    dec = next((lower[n] for n in _DEC_NAMES if n in lower), None)
    if ra is None or dec is None:
        raise ParseError("Cannot find RA/Dec columns in the table (columns: "
                         + ", ".join(table.colnames) + ").")
    return ra, dec


def table_to_skycoord(table: Table) -> SkyCoord:
    ra, dec = find_radec_columns(table)
    def col(name: str) -> u.Quantity:
        c = table[name]
        unit = c.unit if c.unit is not None else u.deg
        return np.asarray(c, dtype=float) * unit
    return SkyCoord(col(ra), col(dec), frame="icrs")


def resolve_coord(text: str, objs: Dict[str, Any]) -> SkyCoord:
    """Workspace SkyCoord/Table name, coordinate text, or an object name (Sesame)."""
    text = text.strip()
    if text in objs:
        obj = objs[text]
        if isinstance(obj, SkyCoord):
            return obj
        if isinstance(obj, Table):
            return table_to_skycoord(obj)
        raise ParseError(f"Workspace object '{text}' is not a SkyCoord or Table.")
    try:
        return parse_skycoord(text)
    except ParseError:
        if not re.search(r"[A-Za-z]", text):
            raise
    try:
        return SkyCoord.from_name(text)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Cannot resolve '{text}' as coordinates or object name ({exc}).") from None


_COORD_LIKE = re.compile(r"^[\s\d.+\-:,hdmsHDMS°]+$")


def resolve_position(text: str, objs: Dict[str, Any]) -> Any:
    """Like :func:`resolve_coord` but leaves object names as plain strings."""
    text = text.strip()
    if text in objs or _COORD_LIKE.match(text):
        try:
            return resolve_coord(text, objs)
        except ParseError:
            if text in objs:
                raise
    return text


def parse_kv(text: str) -> Dict[str, Any]:
    """``key=value`` lines (values are expressions where possible, else strings)."""
    out: Dict[str, Any] = {}
    for line in text.replace(";", "\n").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ParseError(f"Expected 'key=value', got {line!r}.")
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not key:
            raise ParseError(f"Missing key in {line!r}.")
        try:
            out[key] = safe_eval(val)
        except ParseError:
            out[key] = val
    return out


def split_names(text: str, lines_only: bool = False) -> List[str]:
    parts = text.splitlines() if lines_only else re.split(r"[,\n]", text)
    return [p.strip() for p in parts if p.strip() and not p.strip().startswith("#")]


def parse_fields(fields: Sequence[Field], raw: Dict[str, Any], objs: Dict[str, Any]) -> Dict[str, Any]:
    """Raw widget values -> typed values; empty optional fields become ``None``."""
    out: Dict[str, Any] = {}
    for f in fields:
        v = raw.get(f.key)
        text = v.strip() if isinstance(v, str) else v
        if f.kind == "bool":
            out[f.key] = bool(v)
            continue
        if f.kind in ("int", "float"):
            unset_zero = f.default in (0, "") and v == 0 and not f.required
            out[f.key] = None if unset_zero else v
            continue
        if text in ("", None):
            if f.required:
                raise ParseError(f"'{f.label}' is required.")
            out[f.key] = None if f.kind not in ("lines", "kv") else ([] if f.kind == "lines" else {})
            continue
        if f.kind == "coord":
            out[f.key] = resolve_coord(text, objs)
        elif f.kind == "position":
            out[f.key] = resolve_position(text, objs)
        elif f.kind == "quantity":
            q = parse_quantity(text, f.unit, f.label)
            if f.unit and not q.unit.is_equivalent(u.Unit(f.unit), u.spectral()):
                raise ParseError(f"'{f.label}' must be in units compatible with {f.unit}.")
            out[f.key] = q
        elif f.kind == "lines":
            out[f.key] = split_names(text, lines_only=False)
        elif f.kind == "kv":
            out[f.key] = parse_kv(text)
        elif f.kind == "table":
            obj = objs.get(text)
            if not isinstance(obj, Table):
                raise ParseError(f"'{f.label}': '{text}' is not a table in the workspace.")
            out[f.key] = obj
        else:
            out[f.key] = text
    return out


def _unset(v: Any) -> bool:
    return v is None or (isinstance(v, (str, list, tuple, dict)) and len(v) == 0)


def clean(**kw: Any) -> Dict[str, Any]:
    """Drop unset (None / empty) keyword arguments so server defaults apply."""
    return {k: v for k, v in kw.items() if not _unset(v)}


def need(p: Dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if _unset(p.get(k))]
    if missing:
        raise ParseError("Missing: " + ", ".join(missing))


def _names_table(names: Sequence[Any], descriptions: Optional[Sequence[str]] = None,
                 column: str = "name") -> Table:
    t = Table()
    t[column] = [str(n) for n in names]
    if descriptions is not None:
        t["description"] = [str(d) for d in descriptions]
    return t


# Reusable fields ------------------------------------------------------------- #
def _coord(label: str = "Coordinates") -> Field:
    return Field("coord", label, "coord", "", "RA Dec in deg or sexagesimal ('10.68 41.27', "
                 "'00h42m44s +41d16m09s'), an object name (needs network), or the name of a "
                 "SkyCoord/Table in the workspace.", required=True)


def _radius(default: str = "2 arcmin", required: bool = True, key: str = "radius",
            label: str = "Radius") -> Field:
    return Field(key, label, "quantity", default, "A quantity, e.g. '2 arcmin' or '0.5 deg'.",
                 unit="deg", required=required)


def _name(label: str = "Object name", key: str = "name") -> Field:
    return Field(key, label, "text", "", "Resolvable object name, e.g. 'M31'.", required=True)


def _rows(default: int = 100, tip: str = "Maximum rows returned (-1 = server maximum).") -> Field:
    return Field("rows", "Max rows", "int", default, tip, lo=-1)


# --------------------------------------------------------------------------- #
# SIMBAD
# --------------------------------------------------------------------------- #
_SIMBAD_COMMON = (
    Field("votable", "Extra fields", "lines", "", "Comma separated SIMBAD fields to add, e.g. "
          "'otype, sp_type, V' (see 'Show votable fields')."),
    _rows(100),
)
_CRITERIA = Field("criteria", "ADQL criteria", "text", "", "Optional ADQL condition, e.g. "
                  "\"otype = 'G..'\" (column names as in SIMBAD's basic table).")


def _simbad_run(p: Dict[str, Any], t: float, method: str, *args: Any, **kw: Any) -> Any:
    s = service("simbad", t, row_limit=p.get("rows"))
    if p.get("votable"):
        s.add_votable_fields(*p["votable"])
    return getattr(s, method)(*args, **kw)


def _simbad_plain(p: Dict[str, Any], t: float) -> Any:
    return service("simbad", t, row_limit=None)


SIMBAD_QUERIES = (
    Query("object", "Query object", (_name(), Field("wildcard", "Wildcard", "bool", False,
          "Interpret '*' and '?' in the name as wildcards."), _CRITERIA) + _SIMBAD_COMMON,
          lambda p, t: _simbad_run(p, t, "query_object", p["name"], **clean(
              wildcard=p["wildcard"] or None, criteria=p["criteria"]))),
    Query("objects", "Query several objects", (Field("names", "Object names", "lines", "",
          "One name per line (or comma separated).", required=True), Field(
              "wildcard", "Wildcard", "bool", False), _CRITERIA) + _SIMBAD_COMMON,
          lambda p, t: _simbad_run(p, t, "query_objects", p["names"], **clean(
              wildcard=p["wildcard"] or None, criteria=p["criteria"]))),
    Query("region", "Query region", (_coord(), _radius(), _CRITERIA) + _SIMBAD_COMMON,
          lambda p, t: _simbad_run(p, t, "query_region", p["coord"], p["radius"],
                                   **clean(criteria=p["criteria"]))),
    Query("catalog", "Query catalog", (Field("catalog", "Catalog id", "text", "", "SIMBAD catalog "
          "prefix, e.g. 'M', 'NGC', 'HD'.", required=True), _CRITERIA) + _SIMBAD_COMMON,
          lambda p, t: _simbad_run(p, t, "query_catalog", p["catalog"],
                                   **clean(criteria=p["criteria"]))),
    Query("bibcode", "Objects of a bibcode", (Field("bibcode", "Bibcode", "text", "", "e.g. "
          "'2005A&A...430..165F'", required=True), _CRITERIA) + _SIMBAD_COMMON,
          lambda p, t: _simbad_run(p, t, "query_bibobj", p["bibcode"],
                                   **clean(criteria=p["criteria"]))),
    Query("reference", "Reference by bibcode", (Field("bibcode", "Bibcode", "text", "",
          "Bibcode, wildcards allowed if enabled.", required=True),
          Field("wildcard", "Wildcard", "bool", False), Field("abstract", "Abstract", "bool",
                                                              False, "Include the abstract.")),
          lambda p, t: _simbad_run(p, t, "query_bibcode", p["bibcode"], **clean(
              wildcard=p["wildcard"] or None, abstract=p["abstract"] or None))),
    Query("ids", "Identifiers of object", (_name(),),
          lambda p, t: _simbad_run(p, t, "query_objectids", p["name"])),
    Query("hierarchy", "Hierarchy (parents/children)", (_name(), Field(
        "hierarchy", "Relation", "combo", "parents", choices=("parents", "children", "siblings")),
        Field("detailed", "Detailed", "bool", True, "Add bibcode and membership certainty."),
        _rows(100)),
        lambda p, t: _simbad_run(p, t, "query_hierarchy", p["name"], p["hierarchy"],
                                 detailed_hierarchy=p["detailed"])),
    Query("tap", "ADQL (TAP)", (Field("adql", "ADQL query", "text", "SELECT TOP 10 main_id, ra, "
          "dec FROM basic", "Free ADQL; see 'Show tables/columns'.", required=True),
          Field("maxrec", "Max records", "int", 10000, lo=1, hi=10**7)),
          lambda p, t: _simbad_run(p, t, "query_tap", p["adql"], maxrec=p["maxrec"])),
    Query("tables", "Show tables", (), lambda p, t: _simbad_plain(p, t).list_tables(),
          "Lists the tables of the SIMBAD TAP service."),
    Query("columns", "Show columns", (Field("tables", "Tables", "lines", "basic",
          "Table names (comma separated).", required=True), Field("keyword", "Keyword", "text")),
          lambda p, t: _simbad_plain(p, t).list_columns(*p["tables"], **clean(keyword=p["keyword"]))),
    Query("votable", "Show votable fields", (), lambda p, t: _simbad_plain(p, t).list_votable_fields(),
          "Fields that can be added with 'Extra fields'."),
    Query("linked", "Show linked tables", (Field("table", "Table", "text", "basic", required=True),),
          lambda p, t: _simbad_plain(p, t).list_linked_tables(p["table"])),
)

# --------------------------------------------------------------------------- #
# VizieR
# --------------------------------------------------------------------------- #
_VZ_COMMON = (
    Field("columns", "Columns", "lines", "*", "Comma separated output columns; '*' = default set, "
          "'**' = all, '+_r' adds distance."),
    Field("filters", "Column filters", "kv", "", "One per line: Vmag=<10 or SpType=~K*"),
    _rows(50),
)


def _vz(p: Dict[str, Any], t: float) -> Any:
    return service("vizier", t, columns=p.get("columns") or ["*"],
                   column_filters={k: str(v) for k, v in (p.get("filters") or {}).items()},
                   row_limit=p["rows"] if p.get("rows") is not None else 50)


def _vz_catalog(p: Dict[str, Any]) -> Any:
    return p["catalog"] or None


_CATALOG = Field("catalog", "Catalogs", "lines", "", "Catalog ids, comma separated, e.g. "
                 "'I/239/hip_main' (empty = search all).")


def _vz_region(p: Dict[str, Any], t: float) -> Any:
    if p["radius"] is None and (p["width"] is None or p["height"] is None):
        raise ParseError("Give a radius, or both width and height.")
    box = p["width"] is not None and p["height"] is not None  # a box overrides the radius
    return _vz(p, t).query_region(p["coord"], **clean(
        radius=None if box else p["radius"], width=p["width"] if box else None,
        height=p["height"] if box else None, catalog=_vz_catalog(p)))


def _vz_find(p: Dict[str, Any], t: float) -> Table:
    found = _vz(dict(p, rows=50), t).find_catalogs(p["keywords"], **clean(
        max_catalogs=p["max"]))
    return _names_table(list(found), [getattr(r, "description", "") for r in found.values()])


VIZIER_QUERIES = (
    Query("object", "Query object", (_name(), _radius("", False), _CATALOG) + _VZ_COMMON,
          lambda p, t: _vz(p, t).query_object(p["name"], **clean(
              radius=p["radius"], catalog=_vz_catalog(p)))),
    Query("region", "Query region", (_coord(), _radius("5 arcmin", False),
          Field("width", "Box width", "quantity", "", "Alternative to radius.", unit="deg"),
          Field("height", "Box height", "quantity", "", unit="deg"), _CATALOG) + _VZ_COMMON,
          _vz_region),
    Query("constraints", "Query constraints", (_CATALOG, Field(
        "constraints", "Constraints", "kv", "", "One per line, e.g. Vmag=<10", required=True))
        + _VZ_COMMON[:1] + _VZ_COMMON[2:],
        lambda p, t: _vz(dict(p, filters={}), t).query_constraints(**clean(
            catalog=_vz_catalog(p)), **{k: str(v) for k, v in p["constraints"].items()})),
    Query("find", "Find catalogs", (Field("keywords", "Keywords", "text", "", "e.g. 'hipparcos' or "
          "'quasar redshift'", required=True), Field("max", "Max catalogs", "int", 50, lo=0)),
          _vz_find),
    Query("get", "Download catalog", (Field("catalog", "Catalog id", "text", "", "e.g. "
          "'J/ApJ/727/L9'", required=True), _rows(50)),
          lambda p, t: _vz(dict(p, columns=["*"], filters={}), t).get_catalogs(p["catalog"])),
    Query("metadata", "Catalog metadata", (Field("catalog", "Catalog id", "text", "",
          required=True),),
          lambda p, t: _vz(dict(p, rows=50, columns=["*"], filters={}), t).get_catalog_metadata(
              catalog=p["catalog"])),
)

# --------------------------------------------------------------------------- #
# Gaia
# --------------------------------------------------------------------------- #
_GAIA_NOTE = ("Queries the ESA Gaia archive (anonymous access). Queries are sent over the "
              "internet; large ADQL jobs can take minutes.")
_GAIA_ROWS = Field("rows", "Max rows", "int", 50, "-1 = unlimited.", lo=-1)


def _gaia_results(job: Any) -> Any:
    return job.get_results() if hasattr(job, "get_results") else job


def _gaia_box(p: Dict[str, Any]) -> Dict[str, Any]:
    box = p["width"] is not None and p["height"] is not None  # a box overrides the radius
    if p["radius"] is None and not box:
        raise ParseError("Give a radius, or both width and height.")
    return clean(radius=None if box else p["radius"], width=p["width"] if box else None,
                 height=p["height"] if box else None)


def _gaia_adql(p: Dict[str, Any], t: float) -> Any:
    gaia = service("gaia", t, row_limit=p["rows"])
    job = gaia.launch_job_async(p["adql"]) if p["async"] else gaia.launch_job(p["adql"])
    return _gaia_results(job)


def _gaia_tables(p: Dict[str, Any], t: float) -> Table:
    tables = service("gaia", t, row_limit=None).load_tables(only_names=True)
    return _names_table([getattr(x, "name", x) for x in tables])


GAIA_QUERIES = (
    Query("cone", "Cone search", (_coord(), _radius("10 arcsec"), Field(
        "columns", "Columns", "lines", "", "Empty = all columns; or e.g. source_id, ra, dec"),
        _GAIA_ROWS),
        lambda p, t: _gaia_results(service("gaia", t, row_limit=p["rows"]).cone_search_async(
            p["coord"], radius=p["radius"], **clean(columns=tuple(p["columns"] or ())))),
        _GAIA_NOTE),
    Query("object", "Query object (cone/box)", (_coord(), _radius("10 arcsec", False),
          Field("width", "Box width", "quantity", "", unit="deg"),
          Field("height", "Box height", "quantity", "", unit="deg"), _GAIA_ROWS),
          lambda p, t: service("gaia", t, row_limit=p["rows"]).query_object(
              p["coord"], **_gaia_box(p)), _GAIA_NOTE),
    Query("adql", "ADQL query", (Field("adql", "ADQL", "text", "SELECT TOP 10 source_id, ra, dec, "
          "phot_g_mean_mag FROM gaiadr3.gaia_source", required=True), Field(
              "async", "Asynchronous job", "bool", False, "Needed for >2000 rows."), _GAIA_ROWS),
          _gaia_adql, _GAIA_NOTE),
    Query("tables", "List archive tables", (), _gaia_tables, _GAIA_NOTE),
)

# --------------------------------------------------------------------------- #
# JPL Horizons
# --------------------------------------------------------------------------- #
_HZ_FIELDS = (
    Field("id", "Target", "text", "", "Name, number or designation, e.g. 'Ceres', '499', '1P'.",
          required=True),
    Field("id_type", "Target type", "combo", "", "How to interpret the target.",
          choices=("", "smallbody", "designation", "name", "asteroid_name", "comet_name")),
    Field("location", "Location", "text", "", "Observatory code ('500' geocenter, 'Z79', '@sun') "
          "or 'lon lat elevation_km' (E-positive deg)."),
    Field("mode", "Epochs", "combo", "range", "now / range / list", choices=("now", "range", "list")),
    Field("start", "Start", "text", "2026-01-01", "UTC/TDB, YYYY-MM-DD [HH:MM]"),
    Field("stop", "Stop", "text", "2026-01-10"),
    Field("step", "Step", "text", "1d", "n followed by y, mo, d, h, m (e.g. 6h)"),
    Field("list", "Epoch list", "text", "", "Julian dates or ISO times, comma separated."),
)


def horizons_epochs(p: Dict[str, Any]) -> Any:
    mode = p["mode"]
    if mode == "now":
        return [float(Time.now().jd)]
    if mode == "range":
        need(p, "start", "stop", "step")
        return {"start": p["start"], "stop": p["stop"], "step": p["step"]}
    items = split_names(p["list"] or "")
    if not items:
        raise ParseError("Give at least one epoch.")
    epochs = []
    for item in items:
        try:
            epochs.append(float(item))
        except ValueError:
            try:
                epochs.append(float(Time(item).jd))
            except Exception:  # noqa: BLE001
                raise ParseError(f"Cannot parse epoch {item!r}.") from None
    return epochs


def horizons_location(text: Optional[str]) -> Any:
    if not text:
        return None
    parts = text.replace(",", " ").split()
    if len(parts) == 3:
        try:
            lon, lat, elev = (float(x) for x in parts)
            return {"lon": lon, "lat": lat, "elevation": elev}
        except ValueError:
            pass
    return text


def _hz(p: Dict[str, Any], t: float, method: str) -> Any:
    h = service("horizons", t, id=p["id"], location=horizons_location(p["location"]),
                epochs=horizons_epochs(p), id_type=p["id_type"] or None)
    return getattr(h, method)(**clean(quantities=p.get("quantities")))


HORIZONS_QUERIES = (
    Query("ephemerides", "Ephemerides", _HZ_FIELDS + (Field(
        "quantities", "Quantities", "text", "", "Horizons quantity codes, e.g. '1,9,20' (empty = all)."),),
        lambda p, t: _hz(p, t, "ephemerides")),
    Query("elements", "Orbital elements", _HZ_FIELDS, lambda p, t: _hz(p, t, "elements")),
    Query("vectors", "State vectors", _HZ_FIELDS, lambda p, t: _hz(p, t, "vectors")),
)

# --------------------------------------------------------------------------- #
# NED
# --------------------------------------------------------------------------- #
NED_QUERIES = (
    Query("object", "Query object", (_name(),), lambda p, t: service("ned", t).query_object(p["name"])),
    Query("region", "Query region", (_coord(), _radius("1 arcmin")),
          lambda p, t: service("ned", t).query_region(p["coord"], radius=p["radius"])),
    Query("table", "Object data table", (_name(), Field(
        "table", "Table", "combo", "photometry", choices=(
            "photometry", "positions", "diameters", "redshifts", "references", "object_notes"))),
          lambda p, t: service("ned", t).get_table(p["name"], table=p["table"])),
    Query("images", "Image list", (_name(),), lambda p, t: _names_table(
        service("ned", t).get_image_list(p["name"]), column="url"), "Lists FITS image URLs."),
    Query("refcode", "Objects of a reference", (Field("refcode", "Reference code", "text", "",
          "19-digit NED reference code", required=True),),
          lambda p, t: service("ned", t).query_refcode(p["refcode"])),
)

# --------------------------------------------------------------------------- #
# MAST
# --------------------------------------------------------------------------- #
_CAT_CHOICES = ("hsc", "tic", "ctl", "diskdetective", "panstarrs", "galex", "gaia")


def _mast_products(p: Dict[str, Any], t: float) -> Any:
    if p["obsids"]:
        return service("mast_obs", t).get_product_list(p["obsids"])
    if p["table"] is not None:
        return service("mast_obs", t).get_product_list(p["table"])
    raise ParseError("Give observation ids, or select an observations table from the workspace.")


MAST_QUERIES = (
    Query("obs_object", "Observations: object", (_name(), _radius("0.2 deg")),
          lambda p, t: service("mast_obs", t).query_object(p["name"], radius=p["radius"])),
    Query("obs_region", "Observations: region", (_coord(), _radius("0.2 deg")),
          lambda p, t: service("mast_obs", t).query_region(p["coord"], radius=p["radius"])),
    Query("obs_criteria", "Observations: criteria", (Field(
        "criteria", "Criteria", "kv", "obs_collection=HST\ndataproduct_type=image",
        "One per line. Ranges as lists: t_exptime=[100, 1000]", required=True),),
        lambda p, t: service("mast_obs", t).query_criteria(**p["criteria"])),
    Query("products", "Observations: data products", (Field(
        "obsids", "Observation ids", "lines", "", "obsid values, comma separated"),
        Field("table", "...or workspace table", "table", "", "Result of an observations query")),
        _mast_products),
    Query("cat_object", "Catalogs: object", (_name(), _radius("0.2 deg"), Field(
        "catalog", "Catalog", "combo", "hsc", choices=_CAT_CHOICES)),
        lambda p, t: service("mast_cat", t).query_object(p["name"], radius=p["radius"],
                                                         catalog=p["catalog"])),
    Query("cat_region", "Catalogs: region", (_coord(), _radius("0.2 deg"), Field(
        "catalog", "Catalog", "combo", "hsc", choices=_CAT_CHOICES)),
        lambda p, t: service("mast_cat", t).query_region(p["coord"], radius=p["radius"],
                                                         catalog=p["catalog"])),
    Query("cat_criteria", "Catalogs: criteria", (Field(
        "catalog", "Catalog", "combo", "tic", choices=_CAT_CHOICES), Field(
            "criteria", "Criteria", "kv", "", "e.g. Tmag=[8, 10]", required=True)),
        lambda p, t: service("mast_cat", t).query_criteria(p["catalog"], **p["criteria"])),
)

# --------------------------------------------------------------------------- #
# SDSS, SkyView, IRSA Dust
# --------------------------------------------------------------------------- #
_DR = Field("dr", "Data release", "int", 17, "SDSS data release number.", lo=1, hi=99)

SDSS_QUERIES = (
    Query("region", "Query region", (_coord(), _radius("2 arcmin"), Field(
        "spectro", "Spectroscopic only", "bool", False), _DR),
        lambda p, t: service("sdss", t).query_region(p["coord"], radius=p["radius"],
                                                     spectro=p["spectro"], data_release=p["dr"])),
    Query("crossid", "Cross-identify", (_coord(), _radius("5 arcsec"), Field(
        "spectro", "Spectroscopic only", "bool", False), _DR),
        lambda p, t: service("sdss", t).query_crossid(p["coord"], radius=p["radius"],
                                                      spectro=p["spectro"], data_release=p["dr"])),
    Query("sql", "SQL query", (Field("sql", "SQL", "text", "SELECT TOP 10 objID, ra, dec, r FROM "
          "PhotoObj", required=True), _DR),
          lambda p, t: service("sdss", t).query_sql(p["sql"], data_release=p["dr"])),
)


def _skyview_surveys(p: Dict[str, Any], t: float) -> Table:
    surveys = service("skyview", t).list_surveys()
    rows = [(str(cat), s) for cat, names in surveys.items() for s in names]
    t_ = Table(rows=rows, names=("category", "survey"), dtype=(str, str))
    return t_


_SV_FIELDS = (Field("position", "Position", "position", "", "Object name or coordinates.",
                    required=True),
              Field("survey", "Survey", "combo", "DSS", "Survey name (see 'List surveys').",
                    choices=("DSS", "DSS2 Red", "DSS2 Blue", "2MASS-J", "2MASS-H", "2MASS-K",
                             "SDSSg", "SDSSr", "WISE 3.4", "GALEX Near UV", "Fermi 5", "NVSS"),
                    editable=True, required=True),
              _radius("0.5 deg", False),
              Field("pixels", "Pixels", "int", 0, "Image size in pixels (0 = default).", lo=0, hi=10000))

SKYVIEW_QUERIES = (
    Query("images", "Download images", _SV_FIELDS,
          lambda p, t: service("skyview", t).get_images(p["position"], p["survey"], **clean(
              radius=p["radius"], pixels=p["pixels"])),
          "Images are returned as FITS HDULists; store them in the workspace."),
    Query("urls", "Image URLs", _SV_FIELDS,
          lambda p, t: _names_table(service("skyview", t).get_image_list(
              p["position"], p["survey"], **clean(radius=p["radius"], pixels=p["pixels"])),
              column="url")),
    Query("surveys", "List surveys", (), _skyview_surveys),
)

IRSA_QUERIES = (
    Query("extinction", "Dust extinction", (Field("position", "Position", "position", "",
          "Object name or coordinates.", required=True), _radius("", False)),
          lambda p, t: service("irsa_dust", t).get_extinction_table(
              p["position"], **clean(radius=p["radius"])),
          "Schlegel / Schlafly & Finkbeiner dust maps via IRSA."),
    Query("query", "Dust table section", (Field("position", "Position", "position", "",
          required=True), _radius("", False), Field("section", "Section", "text", "",
                                                    "Optional table section, e.g. 'ebv'.")),
          lambda p, t: service("irsa_dust", t).get_query_table(
              p["position"], **clean(radius=p["radius"], section=p["section"]))),
)

# --------------------------------------------------------------------------- #
# Solar system: MPC, SBDB; exoplanets; cross-match; filters; lines
# --------------------------------------------------------------------------- #
MPC_QUERIES = (
    Query("object", "Query orbit database", (Field(
        "target_type", "Type", "combo", "asteroid", choices=("asteroid", "comet")),
        Field("name", "Name", "text", "", "e.g. Eros"),
        Field("number", "Number", "int", 0, "e.g. 433 (0 = unset)", lo=0),
        Field("designation", "Designation", "text", "", "e.g. 2014+AA (use + for spaces)"),
        Field("limit", "Limit", "int", 10, lo=1, hi=100000)),
        lambda p, t: service("mpc", t).query_object(p["target_type"], **clean(
            name=p["name"], number=p["number"], designation=p["designation"], limit=p["limit"]))),
    Query("ephemeris", "Ephemeris", (Field("target", "Target", "text", "", "Name or number",
          required=True), Field("location", "Observatory code", "text", "500", required=True),
          Field("start", "Start (UTC)", "text", "", "YYYY-MM-DD HH:MM (empty = now)"),
          Field("step", "Step", "text", "1d"), Field("number", "Steps", "int", 10, lo=1, hi=10000)),
          lambda p, t: service("mpc", t).get_ephemeris(p["target"], location=p["location"],
                                                       **clean(start=p["start"], step=p["step"],
                                                               number=p["number"]))),
    Query("observatories", "Observatory codes", (), lambda p, t: service("mpc", t).get_observatory_codes()),
)

SBDB_QUERIES = (
    Query("query", "Small-body lookup", (Field("target", "Target", "text", "", "Name, number or "
          "designation", required=True), Field("id_type", "Search mode", "combo", "search",
          choices=("search", "spk", "designation", "name")),
          Field("phys", "Physical parameters", "bool", False),
          Field("discovery", "Discovery circumstances", "bool", False),
          Field("close_approach", "Close approaches", "bool", False),
          Field("neo_only", "NEO only", "bool", False)),
          lambda p, t: service("sbdb", t).query(p["target"], id_type=p["id_type"], phys=p["phys"],
                                                discovery=p["discovery"],
                                                close_approach=p["close_approach"],
                                                neo_only=p["neo_only"])),
)

_NEA_TABLE = Field("table", "Table", "combo", "ps", "ps = all parameter sets, pscomppars = "
                   "composite parameters", choices=("ps", "pscomppars", "stellarhosts", "keplernames"),
                   editable=True, required=True)

NEA_QUERIES = (
    Query("object", "Query object", (_name("Planet/host name"), _NEA_TABLE),
          lambda p, t: service("nea", t).query_object(p["name"], table=p["table"])),
    Query("criteria", "Query criteria", (_NEA_TABLE, Field("select", "Select", "text", "*",
          "Columns, e.g. pl_name,hostname,pl_rade"), Field("where", "Where", "text", "",
          "ADQL condition, e.g. pl_rade<2 and disc_year>2020"), Field("order", "Order by", "text")),
          lambda p, t: service("nea", t).query_criteria(p["table"], **clean(
              select=p["select"], where=p["where"], order=p["order"]))),
    Query("region", "Query region", (_NEA_TABLE, _coord(), _radius("1 deg")),
          lambda p, t: service("nea", t).query_region(p["table"], p["coord"], p["radius"])),
    Query("aliases", "Object aliases", (_name(),), lambda p, t: service("nea", t).query_aliases(p["name"])),
)


def _xmatch_cat(p: Dict[str, Any], n: int) -> Tuple[Any, Optional[str], Optional[str]]:
    cds = p[f"cat{n}"]
    if cds:
        return cds, p[f"ra{n}"], p[f"dec{n}"]
    tbl = p[f"tab{n}"]
    if tbl is None:
        raise ParseError(f"Catalog {n}: give a CDS id or select a workspace table.")
    ra, dec = (p[f"ra{n}"], p[f"dec{n}"]) if p[f"ra{n}"] and p[f"dec{n}"] else find_radec_columns(tbl)
    return tbl, ra, dec


def _xmatch(p: Dict[str, Any], t: float) -> Any:
    c1, ra1, dec1 = _xmatch_cat(p, 1)
    c2, ra2, dec2 = _xmatch_cat(p, 2)
    return service("xmatch", t).query(
        cat1=c1, cat2=c2, max_distance=p["maxdist"],
        **clean(colRA1=ra1, colDec1=dec1, colRA2=ra2, colDec2=dec2))


def _xm_fields(n: int, default: str) -> Tuple[Field, ...]:
    return (Field(f"cat{n}", f"Catalog {n} (CDS id)", "text", default,
                  "e.g. 'vizier:II/246/out' or 'simbad'; empty = use workspace table below."),
            Field(f"tab{n}", f"...or workspace table {n}", "table", ""),
            Field(f"ra{n}", f"RA column {n}", "text", "", "Needed for CDS catalogs; guessed for tables."),
            Field(f"dec{n}", f"Dec column {n}", "text", ""))


XMATCH_QUERIES = (
    Query("match", "Cross-match", _xm_fields(1, "") + _xm_fields(2, "vizier:II/246/out") + (
        Field("maxdist", "Max distance", "quantity", "5 arcsec", unit="arcsec", required=True),),
        _xmatch, "Uses the CDS XMatch service; uploaded workspace tables must have RA/Dec in deg."),
    Query("tables", "Available CDS tables", (), lambda p, t: _names_table(
        service("xmatch", t).get_available_tables())),
)

SVO_QUERIES = (
    Query("index", "Filters by wavelength", (Field("wmin", "Min effective wavelength", "quantity",
          "4000 Angstrom", unit="Angstrom", required=True), Field("wmax", "Max effective wavelength",
          "quantity", "7000 Angstrom", unit="Angstrom", required=True)),
          lambda p, t: service("svo", t).get_filter_index(p["wmin"], p["wmax"])),
    Query("list", "Filters of a facility", (Field("facility", "Facility", "text", "", "e.g. 'HST', "
          "'2MASS'", required=True), Field("instrument", "Instrument", "text", "")),
          lambda p, t: service("svo", t).get_filter_list(p["facility"], **clean(
              instrument=p["instrument"]))),
    Query("transmission", "Transmission curve", (Field("filter_id", "Filter id", "text", "",
          "e.g. '2MASS/2MASS.J'", required=True),),
          lambda p, t: service("svo", t).get_transmission_data(p["filter_id"])),
)

LINES_QUERIES = (
    Query("splatalogue", "Splatalogue (radio/mm lines)", (
        Field("fmin", "Min frequency", "quantity", "100 GHz", unit="GHz", required=True),
        Field("fmax", "Max frequency", "quantity", "101 GHz", unit="GHz", required=True),
        Field("chem", "Chemical name", "text", "", "Regular expression, e.g. 'CO' or ' H2CO '")),
        lambda p, t: service("splatalogue", t).query_lines(p["fmin"], p["fmax"], **clean(
            chemical_name=p["chem"]))),
    Query("nist", "NIST atomic spectra", (
        Field("wmin", "Min wavelength", "quantity", "4000 Angstrom", unit="Angstrom", required=True),
        Field("wmax", "Max wavelength", "quantity", "7000 Angstrom", unit="Angstrom", required=True),
        Field("line", "Spectrum", "text", "H I", "e.g. 'H I', 'Fe II'", required=True),
        Field("eunit", "Energy unit", "combo", "eV", choices=("eV", "cm-1", "Rydberg")),
        Field("wtype", "Wavelength type", "combo", "vacuum", choices=("vacuum", "vac+air"))),
        lambda p, t: service("nist", t).query(p["wmin"], p["wmax"], linename=p["line"],
                                              energy_level_unit=p["eunit"],
                                              wavelength_type=p["wtype"])),
)


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
class ServicePanel(QueryPanel):
    """One service: a combo selects the query, a stacked form holds its fields."""

    def __init__(self, ws: Workspace, key: str, intro: str, queries: Sequence[Query]) -> None:
        super().__init__(ws, key)
        self.queries: Dict[str, Query] = {q.key: q for q in queries}
        self.forms: Dict[str, ParamForm] = {}
        header = QWidget()
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        intro_label = QLabel(intro)
        intro_label.setWordWrap(True)
        hl.addWidget(intro_label)
        self.query_combo = QComboBox()
        for q in queries:
            self.query_combo.addItem(q.label, q.key)
        self.query_combo.setToolTip("Choose which query of this service to run.")
        hl.addWidget(self.query_combo)
        self.help_label = QLabel()
        self.help_label.setWordWrap(True)
        hl.addWidget(self.help_label)
        self.stack = QStackedWidget()
        for q in queries:
            form = ParamForm()
            for f in q.fields:
                self._add_field(form, f)
            self.forms[q.key] = form
            self.stack.addWidget(form)
        self.controls_layout.insertWidget(0, header)
        self.controls_layout.insertWidget(1, self.stack)
        self.add_button("Run query", self.run_query)
        self.query_combo.currentIndexChanged.connect(self._on_query)
        self._on_query()
        self.info.show_text(intro)

    # ---- building ------------------------------------------------------------ #
    def _add_field(self, form: ParamForm, f: Field) -> None:
        label = f.label + (" *" if f.required else "")
        k = f.kind
        if k in ("text", "coord", "position", "quantity"):
            form.add_text(f.key, label, str(f.default), f.tip)
        elif k in ("lines", "kv"):
            form.add_multiline(f.key, label, str(f.default), f.tip, height=70 if k == "kv" else 50)
        elif k == "int":
            form.add_int(f.key, label, int(f.default or 0), f.lo, f.hi, f.tip)
        elif k == "float":
            form.add_float(f.key, label, float(f.default or 0.0), tip=f.tip)
        elif k == "bool":
            form.add_check(f.key, label, bool(f.default), f.tip)
        elif k == "combo":
            form.add_combo(f.key, label, f.choices, f.tip, current=str(f.default) or None,
                           editable=f.editable)
        elif k == "table":
            w = WorkspaceCombo(self.ws, Table)
            w.setToolTip(f.tip)
            form.add_widget(f.key, label, w)
        else:  # pragma: no cover - programming error
            raise ValueError(f"unknown field kind {k!r}")

    # ---- interaction ----------------------------------------------------------- #
    def current_query(self) -> Query:
        return self.queries[self.query_combo.currentData()]

    def select_query(self, key: str) -> None:
        idx = self.query_combo.findData(key)
        if idx < 0:
            raise KeyError(key)
        self.query_combo.setCurrentIndex(idx)

    def _on_query(self) -> None:
        q = self.current_query()
        self.stack.setCurrentWidget(self.forms[q.key])
        self.help_label.setText(q.help)
        self.help_label.setVisible(bool(q.help))

    def set_values(self, **values: Any) -> None:
        form = self.forms[self.current_query().key]
        for k, v in values.items():
            form.set_value(k, v)

    def run_query(self) -> None:
        q = self.current_query()
        raw = self.forms[q.key].values()
        objs = {n: self.ws.get(n) for n in self.ws.names()}

        def job(timeout: float) -> Any:
            return q.call(parse_fields(q.fields, raw, objs), timeout)

        self.execute(job, label=q.key)


def _factory(key: str, intro: str, queries: Sequence[Query]) -> Callable[[Workspace], QWidget]:
    def make(ws: Workspace) -> QWidget:
        return ServicePanel(ws, key, intro, queries)
    return make


_PANELS = (
    ("simbad", "SIMBAD", "SIMBAD astronomical database (CDS Strasbourg).", SIMBAD_QUERIES),
    ("vizier", "VizieR", "VizieR catalogue service (CDS Strasbourg).", VIZIER_QUERIES),
    ("gaia", "Gaia Archive", "ESA Gaia archive. " + _GAIA_NOTE, GAIA_QUERIES),
    ("horizons", "JPL Horizons", "Ephemerides, orbital elements and state vectors of solar-system "
     "bodies (JPL).", HORIZONS_QUERIES),
    ("ned", "NED", "NASA/IPAC Extragalactic Database.", NED_QUERIES),
    ("mast", "MAST", "Mikulski Archive for Space Telescopes (HST, JWST, TESS, ...). Metadata "
     "queries only; no login.", MAST_QUERIES),
    ("sdss", "SDSS", "Sloan Digital Sky Survey catalogue queries.", SDSS_QUERIES),
    ("skyview", "SkyView", "NASA SkyView image cut-outs from many surveys.", SKYVIEW_QUERIES),
    ("irsa_dust", "IRSA Dust", "Galactic dust reddening and extinction (IRSA).", IRSA_QUERIES),
    ("mpc", "Minor Planet Center", "Minor Planet Center orbits, ephemerides and observatory codes.",
     MPC_QUERIES),
    ("sbdb", "JPL Small-Body DB", "JPL Small-Body Database lookup.", SBDB_QUERIES),
    ("nea", "NASA Exoplanet Archive", "NASA Exoplanet Archive tables.", NEA_QUERIES),
    ("xmatch", "CDS XMatch", "Cross-match catalogues or workspace tables with the CDS service.",
     XMATCH_QUERIES),
    ("svo", "SVO Filter Profiles", "Spanish Virtual Observatory filter profile service.", SVO_QUERIES),
    ("lines", "Spectral Lines", "Splatalogue (radio/mm) and NIST (atomic) line databases.",
     LINES_QUERIES),
)

PANELS: Dict[str, Tuple[str, str, Tuple[Query, ...]]] = {k: (t, i, q) for k, t, i, q in _PANELS}

SPECS = [ModuleSpec(f"aq_{key}", title, "Online", _factory(key, intro, queries),
                    intro) for key, title, intro, queries in _PANELS]
