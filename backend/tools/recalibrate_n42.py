"""
Re-apply a device energy axis to N42 files that were saved with a forced linear
3.0 keV/channel axis (ChannelEnergies 0, 3, 6 ... 3069).

Older builds discarded the AlphaHound's own (nonlinear) energy axis when saving
acquisitions. The per-channel counts in those files are still valid, so the axis can be
restored from any spectrum CSV saved by the same unit (an ``Energy (keV),Counts`` file).

    python tools/recalibrate_n42.py --axis-csv tests/data/real_spectra/spectrum_2025-12-12_08-41-27.csv \
        "tests/data/real_spectra/takumar 942pm to 558am.n42" [more.n42 ...]

Those builds also wrote LiveTime / RealTime as 1 s and the moment of saving (the END of the run) as
StartTime. When the real length is known (a file name, a note), restore it:

    python tools/recalibrate_n42.py --axis-csv <csv> --live-time 29760 --start-time 2025-12-18T02:42:35.438Z <file>

Writes ``<name>.recal.n42`` next to each input; the originals are never modified. Only use an
axis taken from the SAME physical unit (axes differ between devices).
"""
import argparse
import csv
import re
import sys
from pathlib import Path

CHANNEL_ENERGIES = re.compile(r"(<ChannelEnergies>)([^<]*)(</ChannelEnergies>)")
TIME_ELEMENTS = ("LiveTime", "RealTime")


def load_axis(csv_path):
    with open(csv_path, encoding="utf-8") as handle:
        rows = [r for r in csv.reader(handle) if r]
    axis = [float(r[0]) for r in rows[1:]]
    if len(axis) < 2 or any(b <= a for a, b in zip(axis, axis[1:])):
        raise ValueError(f"{csv_path}: first column is not a strictly increasing energy axis")
    return axis


def is_forced_linear_3kev(energies):
    return all(abs(e - 3.0 * i) < 1e-6 for i, e in enumerate(energies))


def recalibrate_text(xml_text, axis):
    """Return xml_text with ChannelEnergies replaced by ``axis`` (must match channel count)."""
    m = CHANNEL_ENERGIES.search(xml_text)
    if not m:
        raise ValueError("no <ChannelEnergies> element found")
    old = [float(v) for v in m.group(2).split()]
    if len(old) != len(axis):
        raise ValueError(f"channel count mismatch: file has {len(old)}, axis has {len(axis)}")
    if not is_forced_linear_3kev(old):
        raise ValueError("file does not carry the forced 3.0 keV/channel axis; refusing to overwrite its calibration")
    new = " ".join(f"{e:.5f}" for e in axis)
    return xml_text[:m.start(2)] + new + xml_text[m.end(2):]


def set_times(xml_text, live_time_s=None, start_time=None):
    """Set LiveTime and RealTime (ISO 8601 duration, seconds) and/or StartTime; each must be present once in the file."""
    if live_time_s is not None:
        for name in TIME_ELEMENTS:
            xml_text, n = re.subn(rf"(<{name}>)[^<]*(</{name}>)", rf"\g<1>PT{float(live_time_s):.3f}S\g<2>", xml_text)
            if n != 1:
                raise ValueError(f"expected one <{name}>, found {n}")
    if start_time is not None:
        xml_text, n = re.subn(r"(<StartTime>)[^<]*(</StartTime>)", rf"\g<1>{start_time}\g<2>", xml_text)
        if n != 1:
            raise ValueError(f"expected one <StartTime>, found {n}")
    return xml_text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--axis-csv", required=True, help="spectrum CSV from the same device (Energy,Counts)")
    ap.add_argument("--live-time", type=float, help="the run's real length in seconds (LiveTime and RealTime)")
    ap.add_argument("--start-time", help="the run's real start, ISO 8601 (e.g. 2025-12-18T02:42:35.438Z)")
    ap.add_argument("files", nargs="+", help="N42 files to re-calibrate")
    args = ap.parse_args(argv)
    axis = load_axis(args.axis_csv)
    status = 0
    for f in args.files:
        src = Path(f)
        try:
            out = src.with_suffix(".recal.n42")
            text = recalibrate_text(src.read_text(encoding="utf-8"), axis)
            out.write_text(set_times(text, args.live_time, args.start_time), encoding="utf-8")
            print(f"OK    {src.name} -> {out.name}")
        except Exception as e:
            print(f"SKIP  {src.name}: {e}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
