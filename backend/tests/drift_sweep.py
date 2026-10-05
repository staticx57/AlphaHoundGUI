"""
The axis drifted by 0.90-1.10 on every labelled spectrum: does the answer survive, and does any automatic correction name the wrong source?
    python backend/tests/drift_sweep.py [--offset-limit KEV] [--json out.json]

The numbers that decided the auto-correction's offset limit (2026-10-05, 308 cases, germanium left out):
  +-20 keV                                       292 right, 11 with a false artificial ID
  +-30 keV alone                                 294 right, 13 false IDs, a drifted Co-60 + Cs-137 mixture "corrected" as Eu-152 (3 cases)
  +-30 keV, z >= 15 confirmation beyond +-20     294 right, 10 false IDs, no wrong correction (4 cases differ from +-20: the drifted
                                                 thorium capture is corrected and identified in three of them)
Run it after changing anything in auto_calibration.py. A mixture counts a correction as right when it names one of its own sources.
"""
import argparse
import concurrent.futures as cf
import json
import logging
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import scoring_eval as se   # noqa: E402

GAINS = tuple(round(0.90 + 0.02 * i, 2) for i in range(11))
# the auto-correction's hypothesis that is right for a sample's isotopes
RIGHT_SOURCE = {"Th-232": {"thorium_series"}, "U-238": {"radium_series"}, "Eu-152": {"Eu-152"}, "Ba-133": {"Ba-133"}, "Co-60": {"Co-60 + K-40"}}


def _task(arg):
    cid, gain, limit = arg
    logging.disable(logging.CRITICAL)
    from spectroscopy import auto_calibration as ac
    if limit:
        ac.OFFSET_RANGE = (-limit, limit)
    _, path, kind, _, truth = next(e for e in se.CORPUS + se.LOCAL if e[0] == cid)
    try:
        parsed = se.load(kind, path)
        result = se.analyse(parsed, "csv" if kind == "csv" else "spe" if kind == "spe" else "n42", gain)
        scored = se.score(result, truth)
        auto = result.get("auto_calibration") or {}
        return cid, gain, {"verdict": scored["verdict"], "false_art": scored["false_art"], "top": [n for n, _ in scored["top"][:3]],
                           "applied": bool(auto.get("applied")), "source": auto.get("source") if auto.get("applied") else None}
    except Exception as exc:
        return cid, gain, {"error": str(exc)[:60]}


def _right_sources(truth):
    names = [truth.get("parent")] if truth["kind"] == "series" else list(truth.get("isotopes", ()))
    return set().union(*(RIGHT_SOURCE.get(n, set()) for n in names)) if names else set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset-limit", type=float, default=0.0, help="override the offset limit of auto_calibration (keV)")
    ap.add_argument("--json")
    args = ap.parse_args()
    entries = [e for e in se.CORPUS + se.LOCAL if e[1].exists() and e[4]["kind"] in ("series", "single") and e[3] != "HPGe"]
    tasks = [(e[0], g, args.offset_limit) for e in entries for g in GAINS]
    out = {}
    with cf.ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) - 2)) as pool:
        for cid, gain, row in pool.map(_task, tasks):
            out.setdefault(cid, {})[gain] = row
    truth = {e[0]: e[4] for e in entries}
    cases = right = false_ids = 0
    wrong = []
    for cid, rows in out.items():
        for gain, row in rows.items():
            if "error" in row:
                continue
            cases += 1
            right += bool(row["verdict"])
            false_ids += bool(row["false_art"])
            if row["applied"] and row["source"] not in _right_sources(truth[cid]):
                wrong.append(f"{cid}@{gain}:{row['source']}")
    from spectroscopy import auto_calibration as ac
    print(f"offset limit {args.offset_limit or ac.OFFSET_RANGE[1]:g} keV: cases {cases} | verdict right {right} | with a false artificial ID {false_ids}"
          f" | corrections that named the wrong source {len(wrong)} {wrong}")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({str(k): {str(g): v for g, v in rows.items()} for k, rows in out.items()}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
