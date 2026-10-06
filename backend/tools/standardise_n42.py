"""
Give an old N42 file the energy calibration other software reads.

Files saved before 2026-10-04 describe the energy axis only as the app's own `List` / `ChannelEnergies` pair, which InterSpec and SpecUtils
ignore: they show no axis (or a default 0-3000 keV one). Since then the app also writes the calibration as N42-2012 states it, an identified
`EnergyCalibration` with `EnergyBoundaryValues` that the `Spectrum` refers to. This adds exactly that to an old file, in place in the text:
the counts, the times, the instrument, the saved isotope identifications and everything else are untouched.

    python tools/standardise_n42.py "tests/data/real_spectra/takumar 942pm to 558am.recal.n42" [more.n42 ...] [--out-dir DIR]

Writes ``<name>.std.n42`` next to each input (or in DIR); the originals are never modified.

A file whose axis is the 0, 3, 6 ... keV placeholder (older builds discarded the AlphaHound's own axis) is refused: standardising it would
only give other software a wrong axis in the right format. Restore the device's axis first with tools/recalibrate_n42.py.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from formats.n42_exporter import ENERGY_CALIBRATION_ID, channel_edges   # noqa: E402
from recalibrate_n42 import is_forced_linear_3kev                        # noqa: E402

CHANNEL_ENERGIES = re.compile(r"<ChannelEnergies>([^<]*)</ChannelEnergies>")
SPECTRUM_OPEN = re.compile(r"<Spectrum(?=[\s>])([^>]*?)(/?)>")
RAD_MEASUREMENT_LINE = re.compile(r"(?m)^([ \t]*)<RadMeasurement(?=[\s>])")


class AlreadyStandard(Exception):
    """The file already carries EnergyBoundaryValues."""


class NotStandardisable(Exception):
    """The file cannot be upgraded faithfully (placeholder axis, several spectra, no axis at all)."""


def channel_energies(xml_text):
    found = CHANNEL_ENERGIES.findall(xml_text)
    if not found:
        raise NotStandardisable("no <ChannelEnergies>: nothing to describe the axis from")
    if len(found) > 1 or len(SPECTRUM_OPEN.findall(xml_text)) > 1:
        raise NotStandardisable("several spectra in one file: only single-spectrum files are handled")
    return [float(v) for v in found[0].split()]


def standardise_text(xml_text):
    """xml_text with the standard EnergyCalibration added and referenced; raises AlreadyStandard / NotStandardisable."""
    if "<EnergyBoundaryValues" in xml_text:
        raise AlreadyStandard("already has EnergyBoundaryValues")
    energies = channel_energies(xml_text)
    if len(energies) < 2:
        raise NotStandardisable("fewer than two channels")
    if is_forced_linear_3kev(energies):
        raise NotStandardisable("the axis is the 0, 3, 6 ... keV placeholder: restore the device's axis first with tools/recalibrate_n42.py")

    where = RAD_MEASUREMENT_LINE.search(xml_text)
    if not where:
        raise NotStandardisable("no <RadMeasurement> element")
    indent = where.group(1)
    block = (f'{indent}<EnergyCalibration id="{ENERGY_CALIBRATION_ID}">\n'
             f'{indent}  <EnergyBoundaryValues>{" ".join(f"{e:.5f}" for e in channel_edges(energies))}</EnergyBoundaryValues>\n'
             f'{indent}</EnergyCalibration>\n')
    text = xml_text[:where.start()] + block + xml_text[where.start():]

    def refer(match):
        attributes = match.group(1)
        if "energyCalibrationReference" in attributes:
            return match.group(0)
        return f'<Spectrum{attributes} energyCalibrationReference="{ENERGY_CALIBRATION_ID}"{match.group(2)}>'
    text, count = SPECTRUM_OPEN.subn(refer, text, count=1)
    if not count:
        raise NotStandardisable("no <Spectrum> element")
    ET.fromstring(text)                      # well-formed, or this raises before anything is written
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="N42 files to upgrade")
    ap.add_argument("--out-dir", help="write the results here instead of next to the inputs")
    args = ap.parse_args(argv)
    failed = 0
    for name in args.files:
        source = Path(name)
        try:
            text = standardise_text(source.read_text(encoding="utf-8"))
        except AlreadyStandard as e:
            print(f"SKIP  {source.name}: {e}")
            continue
        except (NotStandardisable, ET.ParseError, OSError, UnicodeDecodeError) as e:
            print(f"FAIL  {source.name}: {e}")
            failed += 1
            continue
        target = Path(args.out_dir or source.parent) / (source.stem + ".std.n42")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"OK    {source.name} -> {target.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
