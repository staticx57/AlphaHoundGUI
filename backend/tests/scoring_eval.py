"""
Identification scoring, measured on every labelled spectrum in the repository (both device families, public spectra, germanium, sodium
iodide), not on one lens and one detector.  Run:  python backend/tests/scoring_eval.py [--json out.json] [--local]

Per spectrum (truth from what the sample is, not from our output):
  verdict      the decay chains reported are exactly the ones the sample has
  false_art    artificial isotopes listed that the sample does not contain (count, highest confidence)
  margin       lowest confidence of the sample's own isotopes in the top 3 minus the highest of anything that is not in its family
  inversion    a series parent with no gamma line of its own (Th-232, U-238) ranked above isotopes that really emit
Across the set:
  order        the isotope ranking does not change when the database lists each isotope's lines in another order
  axis         the verdict and the top isotopes do not change when the energy axis is 3 % off
  copies       (--local) the same run analysed from the acquisition file and from the app's own export gives the same answer
"""
import argparse
import contextlib
import io
import json
import logging
import os
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))

DATA = HERE / "data"
WEB = DATA / "web_spectra"
RC = DATA / "radiacode_fisicas"
REAL = DATA / "real_spectra"
COMM = REAL / "community"

TH = {"Th-232", "Ra-228", "Ac-228", "Th-228", "Ra-224", "Rn-220", "Po-216", "Pb-212", "Bi-212", "Tl-208", "Po-212", "Pb-208"}
U = {"U-238", "Th-234", "Pa-234m", "U-234", "Th-230", "Ra-226", "Rn-222", "Po-218", "Pb-214", "Bi-214", "Po-214", "Pb-210", "Bi-210",
     "Po-210", "U-235", "Th-231", "Pa-231", "Ac-227", "Th-227", "Ra-223", "Pb-211", "Bi-211", "Bi-210m"}
NATURAL_OK = {"K-40"}
PROXY_PARENTS = {"Th-232": ("Th-232", {"Ac-228", "Pb-212", "Tl-208", "Bi-212"}), "U-238": ("U-238", {"Pb-214", "Bi-214", "Th-234", "Pa-234m"})}
ARTIFICIAL = {"Tl-201", "Am-241", "Ba-133", "Co-60", "Cs-137", "I-131", "F-18", "Tc-99m", "Na-22", "Co-57", "Ga-67", "In-111", "Ir-192",
              "Eu-152", "Se-75", "Lu-177", "Sr-90", "Ce-139", "Cr-51", "Mn-54", "Zn-65", "Y-88", "Cd-109", "Bi-207", "Ra-226"}


def series(parent):
    return {"kind": "series", "chains": {parent}, "family": TH if parent == "Th-232" else U, "parent": parent}


def single(*isotopes):
    return {"kind": "single", "chains": set(), "family": set(isotopes), "isotopes": set(isotopes)}


BACKGROUND = {"kind": "bg", "chains": None, "family": set()}

# id, path, loader, device family, truth
CORPUS = [
    ("rc_th232", RC / "Th-232.xml", "rcxml", "RadiaCode CsI", series("Th-232")),
    ("rc_ra226", RC / "Ra-226.xml", "rcxml", "RadiaCode CsI", series("U-238")),
    ("rc_fiesta", RC / "U-238-U-235-FiestaWare.xml", "rcxml", "RadiaCode CsI", series("U-238")),
    ("rc_am241", RC / "Am-241.xml", "rcxml", "RadiaCode CsI", single("Am-241")),
    ("web_th232_bg", WEB / "ckuethe" / "data_th232_plus_background.xml", "rcxml", "RadiaCode CsI", series("Th-232")),
    ("web_th_pendant", WEB / "dmamontov" / "th-90-pendant.xml", "rcxml", "RadiaCode CsI", series("Th-232")),
    ("web_th_wt20", WEB / "dmamontov" / "th-90-wt20.xml", "rcxml", "RadiaCode CsI", series("Th-232")),
    ("web_ra_spd", WEB / "dmamontov" / "ra-88-spd.xml", "rcxml", "RadiaCode CsI", series("U-238")),
    ("web_rn_spd", WEB / "dmamontov" / "rn-86-spd.xml", "rcxml", "RadiaCode CsI", series("U-238")),
    ("web_ra_mazda", WEB / "dmamontov" / "ra-88-mazda0a2.xml", "rcxml", "RadiaCode CsI", series("U-238")),
    ("web_u_glass", WEB / "dmamontov" / "u-92-glass.xml", "rcxml", "RadiaCode CsI", series("U-238")),
    ("web_co60", WEB / "ckuethe" / "Co60_a.xml", "rcxml", "RadiaCode CsI", single("Co-60")),
    ("web_cs137", WEB / "ckuethe" / "Cs137_b.xml", "rcxml", "RadiaCode CsI", single("Cs-137")),
    ("web_co60_cs137", WEB / "ckuethe" / "Co60_a+Cs137_b.xml", "rcxml", "RadiaCode CsI", single("Co-60", "Cs-137")),
    ("web_eu152", WEB / "ckuethe" / "Eu152_b.xml", "rcxml", "RadiaCode CsI", single("Eu-152")),
    ("web_ba133", WEB / "ckuethe" / "Ba133_a.xml", "rcxml", "RadiaCode CsI", single("Ba-133")),
    ("web_ba133_eu152", WEB / "ckuethe" / "Ba133_a+Eu152_b.xml", "rcxml", "RadiaCode CsI", single("Ba-133", "Eu-152")),
    ("web_am241", WEB / "ckuethe" / "data_am241.xml", "rcxml", "RadiaCode CsI", single("Am-241")),
    ("web_am241_his07", WEB / "dmamontov" / "am-95-his07.xml", "rcxml", "RadiaCode CsI", single("Am-241")),
    ("web_bg", WEB / "ckuethe" / "bg.xml", "rcxml", "RadiaCode CsI", BACKGROUND),
    ("web_bg_lead", WEB / "dmamontov" / "bg-lead-shield.xml", "rcxml", "RadiaCode CsI", BACKGROUND),
    ("web_ni63", WEB / "dmamontov" / "ni-28-r26.xml", "rcxml", "RadiaCode CsI", BACKGROUND),
    ("ah_takumar_90m", REAL / "spectrum_2025-12-15_takumar_90min.n42", "n42_recal", "AlphaHound CsI", series("Th-232")),
    ("ah_takumar_8h_dec", REAL / "spectrum_takumar_8hr_reference.n42", "n42_recal", "AlphaHound CsI", series("Th-232")),
    ("ah_takumar_night_dec", REAL / "takumar 942pm to 558am.n42", "n42_recal", "AlphaHound CsI", series("Th-232")),
    ("ah_takumar_live20m", REAL / "takumar_live_2026-10-05_20min_thinned.n42", "n42", "AlphaHound CsI", series("Th-232")),
    ("ah_cs137", BACKEND / "Cs137_Verification_Spectra.n42", "n42", "AlphaHound CsI", single("Cs-137")),
    ("ah_u_glaze_bowl", COMM / "7.5 x 4 Deep Red Uranium Glaze Bowl.csv", "csv", "AlphaHound CsI", series("U-238")),
    ("ah_uraninite", COMM / "Uraninite Ore.csv", "csv", "AlphaHound CsI", series("U-238")),
    ("ah_u_glass_5m_weak", DATA / "real_csv" / "uraniumglass5minutes.csv", "csv", "AlphaHound CsI", {"kind": "weak", "chains": None, "family": U}),
    ("hpge_cave_bg", WEB / "lbl-anp" / "1110C NAA cave background May 2017.spe", "spe", "HPGe", {"kind": "series", "chains": {"U-238", "Th-232"}, "family": TH | U | NATURAL_OK, "parent": None}),
]

# local-only (untracked) runs of the same thoriated lens, for the copy-consistency and more thorium
LOCAL = [
    ("local_8h_overnight", BACKEND / "data" / "acquisitions" / "spectrum_2026-10-05_06-39-14.n42", "n42", "AlphaHound CsI", series("Th-232")),
    ("local_8h_export", pathlib.Path(os.path.expanduser("~")) / "Downloads" / "spectrum_export_2026-10-05T11-12-48-534Z.n42", "n42", "AlphaHound CsI", series("Th-232")),
]


def load(kind, path):
    sys.path.insert(0, str(BACKEND / "tools"))
    from formats.csv_parser import parse_csv_spectrum
    from formats.n42_parser import parse_n42
    from formats.radiacode_xml_parser import parse_radiacode_xml
    if kind == "rcxml":
        return parse_radiacode_xml(path.read_text(encoding="utf-8"))
    if kind == "csv":
        return parse_csv_spectrum(path.read_bytes(), path.name)
    if kind == "n42":
        return parse_n42(path.read_text(encoding="utf-8"))
    if kind == "spe":
        from formats.chn_spe_parser import parse_spe_file
        parsed = parse_spe_file(str(path))
        parsed["metadata"]["live_time"] = parsed.get("live_time", 0)
        return parsed
    if kind == "n42_recal":
        import recalibrate_n42 as rc
        import shutil
        import tempfile
        sys.path.insert(0, str(BACKEND / "tools"))
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "in.n42"
            shutil.copy(path, src)
            return parse_n42(rc.recalibrate_text(src.read_text(encoding="utf-8"), rc.load_axis(REAL / "spectrum_2025-12-12_08-41-27.csv")))
    raise ValueError(kind)


def analyse(parsed, kind="n42", gain=1.0):
    """The app's own upload pipeline (routers/analysis.py): the parser's result into analyze_spectrum_peaks, with the calibration flag each
    format's route passes."""
    from spectroscopy.analysis_utils import analyze_spectrum_peaks
    parsed = dict(parsed)
    if gain != 1.0 and parsed.get("energies"):
        parsed["energies"] = [e * gain for e in parsed["energies"]]
    if kind == "csv":
        calibrated, live = parsed.get("is_calibrated", False), 0.0
    elif kind == "spe":
        calibrated, live = parsed.get("calibration") is not None, parsed.get("live_time", 0.0)
    else:
        calibrated, live = parsed.get("is_calibrated", True), float(parsed.get("metadata", {}).get("live_time", 0) or 0)
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze_spectrum_peaks(parsed, calibrated, live)


def listed(result):
    return [(i["isotope"], float(i["confidence"])) for i in result.get("isotopes", []) if not i.get("suppressed")]


def score(result, truth):
    iso = listed(result)
    chains = {c["parent"] for c in result.get("decay_chains", [])}
    fam = truth["family"]
    out = {"top": [(n, round(c, 1)) for n, c in iso[:6]], "chains": sorted(chains)}
    out["verdict"] = True if truth["chains"] is None else chains == truth["chains"]
    false_art = [(n, c) for n, c in iso if n in ARTIFICIAL and n not in fam]
    out["false_art"] = len(false_art)
    out["false_art_max"] = round(max((c for _, c in false_art), default=0.0), 1)
    top3 = iso[:3]
    true_top = [c for n, c in top3 if n in fam or n in NATURAL_OK]
    false_all = [c for n, c in iso if n not in fam and n not in NATURAL_OK and n not in {"K-40"}]
    if truth["kind"] != "bg" and true_top:
        out["margin"] = round(min(true_top) - max(false_all, default=0.0), 1)
    else:
        out["margin"] = None
    fit = result.get("source_fit") or {}
    out["chi2_dof"] = fit.get("chi2_dof")
    out["levels"] = {c["parent"]: c.get("confidence_level") for c in result.get("decay_chains", []) if c["parent"] in (truth["chains"] or ())}
    src = {k: v.get("z") for k, v in (fit.get("sources") or {}).items()}
    kind, fam = truth["kind"], truth["family"]
    true_names = set()
    if kind == "series":
        if "Th-232" in (truth["chains"] or ()):
            true_names.add("thorium_series")
        if "U-238" in (truth["chains"] or ()):
            true_names |= {"radium_series", "fresh_uranium"}
    elif kind == "single":
        true_names |= {n for n in truth.get("isotopes", ())}
    out["src_z"] = {k: round(v, 1) for k, v in src.items() if v is not None}
    out["z_true_max"] = round(max((src[n] for n in true_names if n in src), default=0.0), 1) if true_names else None
    out["z_false_max"] = round(max((v for k, v in src.items() if k not in true_names and v is not None), default=0.0), 1) if kind in ("series", "single") else None
    wanted = truth["chains"] or set()
    zs = [fit.get("chains", {}).get(c, {}).get("z") for c in wanted]
    out["z"] = min((z for z in zs if z is not None), default=None)
    out["inversion"] = 0
    out["parent_listed"] = None
    parent = truth.get("parent")
    if parent in PROXY_PARENTS:
        name = PROXY_PARENTS[parent][0]
        from spectroscopy.source_templates import SERIES_MEMBERS
        emitters = set(SERIES_MEMBERS[parent]) - {parent}                 # the engine's own definition of the series
        conf = dict(iso)
        best = max((conf[e] for e in emitters if e in conf), default=None)
        # the parent has no line of its own: it must not be more certain than the best daughter that carries its evidence
        if name in conf and best is not None and conf[name] > best + 0.05:
            out["inversion"] = 1
        out["parent_listed"] = (name in conf) if parent in chains else None
        out["parent_rank"] = ([n for n, _ in iso].index(name) + 1) if name in conf else None
    return out


@contextlib.contextmanager
def shuffled_lines(seed):
    from nuclides import isotope_database as db
    saved = {k: list(v) for k, v in db.ISOTOPE_DATABASE.items()}
    rng = random.Random(seed)
    for v in db.ISOTOPE_DATABASE.values():
        rng.shuffle(v)
    for name in ("ISOTOPE_DATABASE_SIMPLE", "ISOTOPE_DATABASE_ADVANCED"):
        d = getattr(db, name, None)
        if isinstance(d, dict) and d is not db.ISOTOPE_DATABASE:
            for k, v in d.items():
                rng.shuffle(v)
    try:
        yield
    finally:
        for k, v in saved.items():
            db.ISOTOPE_DATABASE[k][:] = v


def _task(arg):
    """One analysis in a worker process: (corpus id, mode) with mode base / order / a gain. Returns the scored row or an error."""
    cid, mode = arg
    logging.disable(logging.CRITICAL)
    entry = next(e for e in CORPUS + LOCAL if e[0] == cid)
    _, path, kind, dev, truth = entry
    try:
        parsed = load(kind, path)
        akind = "csv" if kind == "csv" else "spe" if kind == "spe" else "n42"
        if mode == "order":
            with shuffled_lines(1):
                result = analyse(parsed, akind)
        elif mode.startswith("g"):
            result = analyse(parsed, akind, float(mode[1:]))
        else:
            result = analyse(parsed, akind)
        return cid, mode, score(result, truth)
    except Exception as exc:
        return cid, mode, {"error": f"{type(exc).__name__}: {exc}"[:90]}


def main():
    import concurrent.futures as cf
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--fast", action="store_true", help="skip the order and axis checks")
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()
    corpus = [e for e in CORPUS + (LOCAL if args.local else []) if e[1].exists()]
    truths = {e[0]: e[4] for e in corpus}
    devices = {e[0]: e[3] for e in corpus}
    modes = ["base"] + ([] if args.fast else ["order", "g0.97", "g1.03"])
    tasks = [(e[0], m) for m in modes for e in corpus]
    results = {}
    with cf.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for cid, mode, row in pool.map(_task, tasks):
            results[(cid, mode)] = row

    rows = {}
    for e in corpus:
        r = results[(e[0], "base")]
        rows[e[0]] = dict(r, device=devices[e[0]], kind=truths[e[0]]["kind"])
    order_changed, axis_changed = [], []
    for cid in rows:
        base = rows[cid]
        if "error" in base:
            continue
        o = results.get((cid, "order"))
        if o and "error" not in o and [n for n, _ in o["top"]][:4] != [n for n, _ in base["top"]][:4]:
            order_changed.append(cid)
        for g in ("g0.97", "g1.03"):
            a = results.get((cid, g))
            if a and "error" not in a and (a["chains"] != base["chains"] or set(n for n, _ in a["top"][:3]) != set(n for n, _ in base["top"][:3])):
                axis_changed.append(f"{cid}@{g[1:]}")

    ok = [r for r in rows.values() if "error" not in r]
    scored = [r for r in ok if r["kind"] != "weak"]
    series_ids = [k for k, r in rows.items() if "error" not in r and truths[k].get("parent") in PROXY_PARENTS]
    margins = [r["margin"] for r in ok if r.get("margin") is not None]
    summary = {
        "spectra": len(ok), "errors": [k for k, r in rows.items() if "error" in r],
        "verdict_ok": f"{sum(r['verdict'] for r in scored)}/{len(scored)}",
        "false_artificial": sum(r["false_art"] for r in ok), "false_artificial_spectra": sum(1 for r in ok if r["false_art"]),
        "margin_median": round(sorted(margins)[len(margins) // 2], 1) if margins else None,
        "margin_negative": sum(1 for m in margins if m < 0),
        "inversions": f"{sum(1 for k in series_ids if rows[k]['inversion'])}/{len(series_ids)}",
        "parent_not_listed": f"{sum(1 for k in series_ids if rows[k].get('parent_listed') is False)}/{sum(1 for k in series_ids if rows[k].get('parent_listed') is not None)}",
        "parent_rank": {k: rows[k].get('parent_rank') for k in series_ids},
        "z_median": (lambda zs: round(sorted(zs)[len(zs) // 2], 1) if zs else None)([r["z"] for r in ok if r.get("z") is not None]),
        "chi2_dof_median": (lambda cs: round(sorted(cs)[len(cs) // 2], 1) if cs else None)([r["chi2_dof"] for r in ok if r.get("chi2_dof") is not None]),
        "z_by_spectrum": {k: rows[k].get("z") for k in series_ids},
        "chi2_by_spectrum": {k: rows[k].get("chi2_dof") for k in series_ids},
        "z_true_min": min((r["z_true_max"] for r in ok if r.get("z_true_max")), default=None),
        "z_false_max": max((r["z_false_max"] for r in ok if r.get("z_false_max") is not None), default=None),
        "z_false_worst": max(((r["z_false_max"], k) for k, r in rows.items() if "error" not in r and r.get("z_false_max") is not None), default=None),
        "z_true_worst": min(((r["z_true_max"], k) for k, r in rows.items() if "error" not in r and r.get("z_true_max")), default=None),
        "series_high": f"{sum(1 for k in series_ids if rows[k].get('levels') and all(v == 'HIGH' for v in rows[k]['levels'].values()))}/{len(series_ids)}",
        "order_changes": order_changed, "axis_changes": len(axis_changed), "axis_changed_ids": axis_changed,
    }
    if not args.quiet:
        print(f"{'spectrum':<22}{'dev':<15}{'verdict':<8}{'art':>4}{'margin':>8}{'inv':>4}  top isotopes / chains")
        for cid, r in rows.items():
            if "error" in r:
                print(f"{cid:<22}{r['device']:<15}ERROR {r['error']}")
                continue
            print(f"{cid:<22}{r['device']:<15}{'ok' if r['verdict'] else 'WRONG':<8}{r['false_art']:>4}{str(r['margin']):>8}{r['inversion']:>4}  "
                  f"{' '.join(f'{n}:{c:.0f}' for n, c in r['top'][:4])} | {','.join(r['chains'])}")
    print(json.dumps(summary, indent=1))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({"rows": rows, "summary": summary}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
