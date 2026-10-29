"""Tests for the dedicated astroquery panels; every service is replaced by a fake that
checks each call against the *real* astroquery method signature (no network)."""
import inspect
import socket

import numpy as np
import pytest
import requests
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import astroquery_catalogs as c
from astrotools_adv.modules import astroquery_generic as g


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def deny(*_a, **_k):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    g.set_offline(False)
    yield
    g.set_offline(False)


# --------------------------------------------------------------------------- #
# fake services
# --------------------------------------------------------------------------- #
def _real_classes():
    from astroquery.gaia import GaiaClass
    from astroquery.ipac.irsa.irsa_dust import IrsaDustClass
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchiveClass
    from astroquery.ipac.ned import NedClass
    from astroquery.jplhorizons import HorizonsClass
    from astroquery.jplsbdb import SBDBClass
    from astroquery.mast import CatalogsClass, ObservationsClass
    from astroquery.mpc import MPCClass
    from astroquery.nist import NistClass
    from astroquery.sdss import SDSSClass
    from astroquery.simbad import SimbadClass
    from astroquery.skyview import SkyViewClass
    from astroquery.splatalogue import SplatalogueClass
    from astroquery.svo_fps import SvoFpsClass
    from astroquery.vizier import VizierClass
    from astroquery.xmatch import XMatchClass

    return {"simbad": SimbadClass, "vizier": VizierClass, "gaia": GaiaClass,
            "horizons": HorizonsClass, "ned": NedClass, "mast_obs": ObservationsClass,
            "mast_cat": CatalogsClass, "sdss": SDSSClass, "skyview": SkyViewClass,
            "irsa_dust": IrsaDustClass, "mpc": MPCClass, "sbdb": SBDBClass,
            "nea": NasaExoplanetArchiveClass, "xmatch": XMatchClass, "svo": SvoFpsClass,
            "splatalogue": SplatalogueClass, "nist": NistClass}


REAL = _real_classes()


class _Resource:
    description = "a catalog"


class _TapTable:
    name = "gaiadr3.gaia_source"


class _Job:
    def get_results(self):
        return Table({"source_id": [1, 2]})


CANNED = {
    "find_catalogs": {"I/239/hip_main": _Resource(), "J/other": _Resource()},
    "list_surveys": {"Optical": ["DSS", "DSS2 Red"], "IR": ["2MASS-J"]},
    "get_image_list": ["http://x/1.fits", "http://x/2.fits"],
    "get_available_tables": ["vizier:A", "simbad"],
    "load_tables": [_TapTable()],
    "cone_search_async": _Job(), "launch_job": _Job(), "launch_job_async": _Job(),
    "query_aliases": {"aliases": ["a", "b"]},
    "query": {"object": {"fullname": "1 Ceres"}},
}


def _sig(cls, name):
    func = getattr(cls, name, None)
    if func is None:
        raise AttributeError(f"{cls.__name__} has no method {name!r}")
    sig = inspect.signature(func)
    kinds = {p.kind for n, p in sig.parameters.items() if n != "self"}
    if kinds <= {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD} \
            and hasattr(cls, name + "_async"):
        sig = inspect.signature(getattr(cls, name + "_async"))
    return sig


class FakeService:
    """Validates every call against the real signature, records it, returns canned data."""

    def __init__(self, cls, log, name, init_kwargs=None):
        self._cls, self._log, self._name = cls, log, name
        self.init_kwargs = init_kwargs or {}

    def __getattr__(self, method):
        if method.startswith("_"):
            raise AttributeError(method)
        sig = _sig(self._cls, method)

        def call(*args, **kwargs):
            sig.bind(None, *args, **kwargs)  # TypeError on a wrong keyword/arity
            self._log.append((self._name, method, args, kwargs, self.init_kwargs))
            result = CANNED.get(method)
            if result is None and method == "query" and self._name != "sbdb":
                result = Table({"a": [1]})
            return result if result is not None else Table({"a": [1, 2, 3]})

        return call


@pytest.fixture
def calls(monkeypatch):
    log = []

    def make(name):
        def factory(timeout, **kw):
            if name in ("horizons", "vizier"):
                sig = inspect.signature(REAL[name].__init__)
                sig.bind(None, **{k: v for k, v in kw.items()})
            if name == "simbad":
                inspect.signature(REAL[name].__init__).bind(None, ROW_LIMIT=kw.get("row_limit"))
            return FakeService(REAL[name], log, name, dict(kw, timeout=timeout))
        return factory

    monkeypatch.setattr(c, "FACTORIES", {name: make(name) for name in REAL})
    return log


def panel(qtbot, ws, key):
    title, intro, queries = c.PANELS[key]
    p = c.ServicePanel(ws, key, intro, queries)
    qtbot.addWidget(p)
    return p


def run(p, query, **values):
    p.select_query(query)
    p.set_values(**values)
    p.run_query()


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
def test_resolve_coord_variants():
    sc = c.resolve_coord("10.68 41.27", {})
    assert sc.ra.deg == pytest.approx(10.68)
    assert c.resolve_coord("00h42m44s +41d16m09s", {}).dec.deg == pytest.approx(41.2692, abs=1e-3)
    mine = SkyCoord(1 * u.deg, 2 * u.deg)
    assert c.resolve_coord("mine", {"mine": mine}) is mine
    with pytest.raises(ParseError):
        c.resolve_coord("tbl", {"tbl": 5})


def test_table_to_skycoord_and_radec_detection():
    t = Table({"RA_ICRS": [1.0, 2.0], "DE_ICRS": [3.0, 4.0]})
    sc = c.resolve_coord("t", {"t": t})
    assert len(sc) == 2 and sc[1].dec.deg == 4.0
    t["RA_ICRS"].unit = u.hourangle
    assert c.table_to_skycoord(t)[0].ra.deg == pytest.approx(15.0)
    with pytest.raises(ParseError):
        c.find_radec_columns(Table({"x": [1]}))


def test_resolve_position_keeps_names_as_strings():
    assert c.resolve_position("M31", {}) == "M31"
    assert c.resolve_position("Sgr A*", {}) == "Sgr A*"
    assert isinstance(c.resolve_position("10.68 41.27", {}), SkyCoord)


def test_parse_kv_and_names():
    assert c.parse_kv("Vmag=<10\nn=5\nr=[1, 2]\n# c\n x = M31") == {
        "Vmag": "<10", "n": 5, "r": [1, 2], "x": "M31"}
    with pytest.raises(ParseError):
        c.parse_kv("novalue")
    assert c.split_names("a, b\n c") == ["a", "b", "c"]


def test_parse_fields_typing_and_errors():
    fields = (c.Field("q", "Radius", "quantity", unit="deg", required=True),
              c.Field("n", "Number", "int", 0), c.Field("rows", "Rows", "int", 50, lo=-1),
              c.Field("b", "Flag", "bool"), c.Field("names", "Names", "lines"),
              c.Field("opt", "Opt", "text"))
    out = c.parse_fields(fields, {"q": "2 arcmin", "n": 0, "rows": 0, "b": True,
                                  "names": "a, b", "opt": ""}, {})
    assert out["q"] == 2 * u.arcmin and out["n"] is None and out["rows"] == 0
    assert out["b"] is True and out["names"] == ["a", "b"] and out["opt"] is None
    assert c.parse_fields(fields, {"q": "0.5"}, {})["q"] == 0.5 * u.deg
    with pytest.raises(ParseError):
        c.parse_fields(fields, {"q": ""}, {})
    with pytest.raises(ParseError):
        c.parse_fields(fields, {"q": "3 km"}, {})
    with pytest.raises(ParseError):
        c.parse_fields((c.Field("t", "Tab", "table"),), {"t": "nope"}, {})
    freq = (c.Field("f", "Freq", "quantity", unit="GHz"),)
    assert c.parse_fields(freq, {"f": "3 mm"}, {})["f"] == 3 * u.mm  # spectral-equivalent


def test_clean_handles_quantities_and_empty():
    kw = c.clean(a=None, b="", c=[], d=(), e={}, f=0, g=False, h=2 * u.deg, i=SkyCoord(0, 0, unit="deg"))
    assert set(kw) == {"f", "g", "h", "i"}


def test_horizons_helpers():
    p = {"mode": "range", "start": "2026-01-01", "stop": "2026-01-02", "step": "1h", "list": ""}
    assert c.horizons_epochs(p) == {"start": "2026-01-01", "stop": "2026-01-02", "step": "1h"}
    assert c.horizons_epochs(dict(p, mode="list", list="2460000.5, 2026-01-01 12:00"))[0] == 2460000.5
    assert len(c.horizons_epochs(dict(p, mode="list", list="2460000.5, 2026-01-01 12:00"))) == 2
    assert c.horizons_epochs(dict(p, mode="now"))[0] > 2460000
    with pytest.raises(ParseError):
        c.horizons_epochs(dict(p, mode="list", list="garbage"))
    with pytest.raises(ParseError):
        c.horizons_epochs(dict(p, start=None))
    assert c.horizons_location("-3.5 40.2 0.6") == {"lon": -3.5, "lat": 40.2, "elevation": 0.6}
    assert c.horizons_location("Z79") == "Z79" and c.horizons_location("") is None


def test_specs():
    assert len(c.SPECS) == len(c.PANELS) >= 15
    assert {s.category for s in c.SPECS} == {"Online"}
    assert len({s.key for s in c.SPECS}) == len(c.SPECS)


# --------------------------------------------------------------------------- #
# every query of every panel against the real signatures
# --------------------------------------------------------------------------- #
def _sample(f: c.Field):
    if f.default not in ("", None):
        return None  # keep the default
    return {"coord": "10.68 41.27", "position": "M31", "lines": "a, b", "kv": "x=1",
            "quantity": f"1 {f.unit or 'deg'}", "text": "M31"}.get(f.kind)


ALL_QUERIES = [(k, q.key) for k, (_t, _i, qs) in c.PANELS.items() for q in qs]


@pytest.mark.parametrize("panel_key,query_key", ALL_QUERIES)
def test_each_query_runs_against_real_signature(qtbot, ws, calls, panel_key, query_key):
    ws.put("tab1", Table({"ra": [1.0], "dec": [2.0]}))
    p = panel(qtbot, ws, panel_key)
    q = p.queries[query_key]
    values = {f.key: _sample(f) for f in q.fields if f.required and _sample(f) is not None}
    values = {k: v for k, v in values.items() if v is not None}
    if query_key in ("catalog",):
        values["catalog"] = "NGC"
    if query_key == "tap":
        pass
    if panel_key == "horizons":
        values["id"] = "Ceres"
    if panel_key == "xmatch" and query_key == "match":
        values["cat2"] = "vizier:II/246/out"
        values["ra2"], values["dec2"] = "RAJ2000", "DEJ2000"
    if panel_key == "mast" and query_key == "products":
        values["obsids"] = "123, 456"
    run(p, query_key, **values)
    text = p.info.toPlainText()
    assert not text.startswith("Error") and "Input error" not in text, text
    assert len(calls) >= 1, (panel_key, query_key)
    assert p.current_table() is not None or p.info.toPlainText()


# --------------------------------------------------------------------------- #
# parameter passing (types, units, row limits)
# --------------------------------------------------------------------------- #
def test_simbad_region_passes_typed_arguments_and_stores(qtbot, ws, calls):
    p = panel(qtbot, ws, "simbad")
    run(p, "region", coord="10.68 41.27", radius="3 arcmin", votable="otype, V", rows=25,
        criteria="otype = 'G..'")
    (name, method, args, kwargs, init), = [x for x in calls if x[1] != "add_votable_fields"]
    assert method == "query_region"
    assert isinstance(args[0], SkyCoord) and args[0].ra.deg == pytest.approx(10.68)
    assert args[1] == 3 * u.arcmin and kwargs == {"criteria": "otype = 'G..'"}
    assert init["row_limit"] == 25 and init["timeout"] == 30
    assert any(x[1] == "add_votable_fields" and x[2] == ("otype", "V") for x in calls)
    assert p.store_table() == "simbad"
    assert isinstance(ws.get("simbad"), Table) and len(ws.get("simbad")) == 3


def test_simbad_objects_and_tap(qtbot, ws, calls):
    p = panel(qtbot, ws, "simbad")
    run(p, "objects", names="M1\nM2, M3")
    assert calls[-1][1] == "query_objects" and calls[-1][2] == (["M1", "M2", "M3"],)
    run(p, "tap", adql="SELECT TOP 5 main_id FROM basic", maxrec=7)
    assert calls[-1][2:4] == (("SELECT TOP 5 main_id FROM basic",), {"maxrec": 7})
    run(p, "columns", tables="basic, ident", keyword="ra")
    assert calls[-1][1:4] == ("list_columns", ("basic", "ident"), {"keyword": "ra"})


def test_vizier_arguments(qtbot, ws, calls):
    p = panel(qtbot, ws, "vizier")
    run(p, "region", coord="10 20", radius="5 arcmin", catalog="I/239/hip_main, II/246",
        columns="RAJ2000, DEJ2000, Vmag", filters="Vmag=<10", rows=12)
    name, method, args, kwargs, init = calls[-1]
    assert method == "query_region" and args[0].dec.deg == 20
    assert kwargs == {"radius": 5 * u.arcmin, "catalog": ["I/239/hip_main", "II/246"]}
    assert init["row_limit"] == 12 and init["columns"] == ["RAJ2000", "DEJ2000", "Vmag"]
    assert init["column_filters"] == {"Vmag": "<10"}


def test_vizier_region_needs_extent_and_box_works(qtbot, ws, calls):
    p = panel(qtbot, ws, "vizier")
    run(p, "region", coord="10 20", radius="")
    assert "Give a radius" in p.info.toPlainText() and not calls
    run(p, "region", coord="10 20", width="1 deg", height="30 arcmin")  # default radius dropped
    assert calls[-1][3] == {"width": 1 * u.deg, "height": 30 * u.arcmin}


def test_vizier_find_and_constraints(qtbot, ws, calls):
    p = panel(qtbot, ws, "vizier")
    run(p, "find", keywords="hipparcos")
    table = p.current_table()
    assert list(table["name"]) == ["I/239/hip_main", "J/other"] and table["description"][0] == "a catalog"
    run(p, "constraints", catalog="I/239/hip_main", constraints="Vmag=<5\nHpmag=>1")
    assert calls[-1][3] == {"catalog": ["I/239/hip_main"], "Vmag": "<5", "Hpmag": ">1"}


def test_gaia_cone_and_adql(qtbot, ws, calls):
    p = panel(qtbot, ws, "gaia")
    run(p, "cone", coord="56.75 24.12", radius="30 arcsec", columns="source_id, ra", rows=10)
    name, method, args, kwargs, init = calls[-1]
    assert method == "cone_search_async" and kwargs["radius"] == 30 * u.arcsec
    assert kwargs["columns"] == ("source_id", "ra") and init["row_limit"] == 10
    assert list(p.current_table()["source_id"]) == [1, 2]
    run(p, "adql", adql="SELECT 1", **{"async": True})
    assert calls[-1][1] == "launch_job_async"
    run(p, "tables")
    assert list(p.current_table()["name"]) == ["gaiadr3.gaia_source"]


def test_horizons_arguments(qtbot, ws, calls):
    p = panel(qtbot, ws, "horizons")
    run(p, "ephemerides", id="Ceres", id_type="smallbody", location="-5.0 37.9 0.1",
        mode="range", start="2026-01-01", stop="2026-01-05", step="1d", quantities="1,9")
    name, method, args, kwargs, init = calls[-1]
    assert init["id"] == "Ceres" and init["id_type"] == "smallbody"
    assert init["location"] == {"lon": -5.0, "lat": 37.9, "elevation": 0.1}
    assert init["epochs"] == {"start": "2026-01-01", "stop": "2026-01-05", "step": "1d"}
    assert method == "ephemerides" and kwargs == {"quantities": "1,9"}
    run(p, "vectors", id="499", mode="now")
    assert calls[-1][1] == "vectors" and isinstance(calls[-1][4]["epochs"][0], float)
    assert calls[-1][4]["id_type"] is None


def test_mast_xmatch_and_workspace_inputs(qtbot, ws, calls):
    p = panel(qtbot, ws, "mast")
    run(p, "obs_criteria", criteria="obs_collection=HST\nt_exptime=[100, 1000]")
    assert calls[-1][3] == {"obs_collection": "HST", "t_exptime": [100, 1000]}
    run(p, "cat_object", name="M31", radius="0.1 deg", catalog="tic")
    assert calls[-1][3] == {"radius": 0.1 * u.deg, "catalog": "tic"}

    ws.put("mytable", Table({"RAJ2000": [1.0], "DEJ2000": [2.0]}))
    x = panel(qtbot, ws, "xmatch")
    run(x, "match", cat2="vizier:II/246/out", maxdist="3 arcsec")
    name, method, args, kwargs, init = calls[-1]
    assert kwargs["cat1"] is ws.get("mytable") and kwargs["cat2"] == "vizier:II/246/out"
    assert kwargs["colRA1"] == "RAJ2000" and kwargs["colDec1"] == "DEJ2000"
    assert kwargs["max_distance"] == 3 * u.arcsec and "colRA2" not in kwargs

    run(p, "obs_region", coord="mytable", radius="0.2 deg")  # workspace table as coordinates
    assert len(calls[-1][2][0]) == 1


def test_coordinates_from_workspace_skycoord(qtbot, ws, calls):
    ws.put("target", SkyCoord(150 * u.deg, 2 * u.deg))
    p = panel(qtbot, ws, "sdss")
    run(p, "region", coord="target", radius="1 arcmin", spectro=True)
    assert calls[-1][2][0] is ws.get("target") and calls[-1][3]["spectro"] is True


def test_skyview_images_become_workspace_objects(qtbot, ws, calls, monkeypatch):
    from astropy.io import fits

    hdul = fits.HDUList([fits.PrimaryHDU(np.zeros((2, 2)))])
    CANNED["get_images"] = [hdul]
    try:
        p = panel(qtbot, ws, "skyview")
        run(p, "images", position="M31", survey="DSS", radius="0.3 deg", pixels=200)
        name, method, args, kwargs, init = calls[-1]
        assert args == ("M31", "DSS") and kwargs == {"radius": 0.3 * u.deg, "pixels": 200}
        assert p.store_objects() == ["skyview"] and ws.get("skyview") is hdul
        run(p, "surveys")
        t = p.current_table()
        assert list(t["survey"]) == ["DSS", "DSS2 Red", "2MASS-J"]
    finally:
        CANNED.pop("get_images")


def test_mpc_number_zero_is_unset(qtbot, ws, calls):
    p = panel(qtbot, ws, "mpc")
    run(p, "object", target_type="comet", name="Halley")
    assert calls[-1][2] == ("comet",) and calls[-1][3] == {"name": "Halley", "limit": 10}


def test_sbdb_dict_shown_as_text(qtbot, ws, calls):
    p = panel(qtbot, ws, "sbdb")
    run(p, "query", target="Ceres", phys=True)
    assert "1 Ceres" in p.info.toPlainText() and p.current_table() is None


def test_lines_and_svo_units(qtbot, ws, calls):
    p = panel(qtbot, ws, "lines")
    run(p, "splatalogue", fmin="230 GHz", fmax="231 GHz", chem="CO")
    assert calls[-1][2] == (230 * u.GHz, 231 * u.GHz) and calls[-1][3] == {"chemical_name": "CO"}
    run(p, "nist", wmin="5000 Angstrom", wmax="6000 Angstrom", line="Fe II")
    assert calls[-1][3]["linename"] == "Fe II"
    s = panel(qtbot, ws, "svo")
    run(s, "index", wmin="1 um", wmax="2 um")
    assert calls[-1][2] == (1 * u.um, 2 * u.um)


# --------------------------------------------------------------------------- #
# robustness
# --------------------------------------------------------------------------- #
class Boom:
    def __init__(self, exc):
        self.exc = exc

    def __getattr__(self, name):
        def fail(*a, **k):
            raise self.exc
        return fail


def test_errors_become_messages(qtbot, ws, monkeypatch):
    p = panel(qtbot, ws, "ned")
    for exc, text in [(requests.exceptions.ReadTimeout("slow"), "Network error"),
                      (ConnectionError("down"), "Network error"),
                      (ValueError("bad name"), "Error: ValueError: bad name")]:
        monkeypatch.setitem(c.FACTORIES, "ned", lambda t, _e=exc, **kw: Boom(_e))
        run(p, "object", name="M31")
        assert text in p.info.toPlainText()
        assert p.current_table() is None
    assert p.status_changed  # signal object exists; no dialog was opened (would block)


def test_empty_and_none_results(qtbot, ws, monkeypatch):
    p = panel(qtbot, ws, "ned")
    monkeypatch.setitem(c.FACTORIES, "ned", lambda t, **kw: type(
        "E", (), {"query_object": lambda self, n: Table({"a": []})})())
    run(p, "object", name="M31")
    assert "no rows" in p.info.toPlainText()
    monkeypatch.setitem(c.FACTORIES, "ned", lambda t, **kw: type(
        "N", (), {"query_object": lambda self, n: None})())
    run(p, "object", name="M31")
    assert "no result" in p.info.toPlainText()


def test_required_and_invalid_inputs_do_not_call_service(qtbot, ws, calls):
    p = panel(qtbot, ws, "simbad")
    run(p, "object", name="")
    assert "required" in p.info.toPlainText() and not calls
    run(p, "region", coord="not a coord !!", radius="2 arcmin")
    assert "Input error" in p.info.toPlainText() and not calls
    run(p, "region", coord="10 20", radius="2 parsec")
    assert "compatible with deg" in p.info.toPlainText() and not calls


def test_offline_blocks_dedicated_panels(qtbot, ws, calls):
    p = panel(qtbot, ws, "simbad")
    p.offline_box.setChecked(True)
    run(p, "object", name="M31")
    assert not calls and "Offline mode" in p.info.toPlainText()
    other = panel(qtbot, ws, "vizier")
    assert other.offline_box.isChecked()          # shared session-wide switch
    p.offline_box.setChecked(False)
    run(p, "object", name="M31")
    assert len(calls) == 1


def test_timeout_is_forwarded(qtbot, ws, calls):
    p = panel(qtbot, ws, "ned")
    p.timeout_box.setValue(7)
    run(p, "object", name="M31")
    assert calls[-1][4]["timeout"] == 7


def test_store_and_save_roundtrip(qtbot, ws, calls, tmp_path, monkeypatch):
    p = panel(qtbot, ws, "ned")
    run(p, "object", name="M31")
    p.store_edit.setText("ned_m31")
    assert p.store_table() == "ned_m31" and "ned_m31" in ws
    out = tmp_path / "t.ecsv"
    monkeypatch.setattr(p, "ask_save_path", lambda *a, **k: str(out))
    p.save_table()
    assert len(Table.read(out)) == 3
    monkeypatch.setattr(p, "ask_save_path", lambda *a, **k: str(tmp_path / "nodir" / "t.ecsv"))
    p.save_table()                                  # failure is reported, not raised
    assert "Could not save" in p.info.toPlainText()


def test_query_switch_changes_form_and_help(qtbot, ws):
    p = panel(qtbot, ws, "gaia")
    p.select_query("adql")
    assert p.stack.currentWidget() is p.forms["adql"]
    assert not p.help_label.isHidden() or p.help_label.text() == ""
    with pytest.raises(KeyError):
        p.select_query("nope")


@pytest.mark.parametrize("text", ["M31", "M 31", "HD 12345", "NGC 224"])
def test_resolve_position_names_never_trigger_local_resolution(text, monkeypatch):
    """Names that merely look like sexagesimal characters must reach the service as strings."""
    monkeypatch.setattr(SkyCoord, "from_name",
                        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("resolved"))))
    assert c.resolve_position(text, {}) == text


@pytest.mark.parametrize("text", ["10.68 41.27", "00h42m44s +41d16m09s", "10.68, -41.27"])
def test_resolve_position_parses_real_positions(text):
    assert isinstance(c.resolve_position(text, {}), SkyCoord)
