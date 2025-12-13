"""
Quick test to compare energy CALIBRATION options for uranium glass spectrum.
Compares:
  Option A: Full range as device sends (~7.4 keV/channel calibration)
  Option B: Recalculated with 3 keV/channel (expected AlphaHound spec)
"""

import csv
import sys
sys.path.insert(0, 'backend')

from peak_detection import detect_peaks
from isotope_database import identify_isotopes

# Load the 6-hour uranium glass spectrum
filepath = r"backend\data\acquisitions\spectrum_2025-12-12_08-41-27.csv"

energies_device = []
counts = []

with open(filepath, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        energy = float(row['Energy (keV)'])
        count = float(row['Counts'])
        energies_device.append(energy)
        counts.append(count)

# Recalculate energies assuming 3 keV/channel
# Assuming channel 0 starts at 0 keV
energies_recalc = [i * 3.0 for i in range(len(counts))]

print("="*80)
print("URANIUM GLASS SPECTRUM CALIBRATION COMPARISON")
print("="*80)
print(f"\nLoaded {len(counts)} channels with {sum(counts):.0f} total counts")
print(f"\nOption A (Device): {min(energies_device):.2f} - {max(energies_device):.2f} keV (~{max(energies_device)/len(counts):.2f} keV/ch)")
print(f"Option B (Recalc): {min(energies_recalc):.2f} - {max(energies_recalc):.2f} keV (3.00 keV/ch)")

print("\n" + "="*80)
print("OPTION A: DEVICE CALIBRATION (~7.4 keV/channel)")
print("="*80)

peaks_device = detect_peaks(energies_device, counts)
print(f"\nDetected {len(peaks_device)} peaks")
if peaks_device:
    print("\nTop 10 peaks:")
    for i, peak in enumerate(peaks_device[:10]):
        print(f"  {i+1}. {peak['energy']:.2f} keV ({peak['counts']:.0f} counts)")

isotopes_device = identify_isotopes(peaks_device, energy_tolerance=30, mode='simple')
print(f"\n> Isotopes identified: {len(isotopes_device)}")
for iso in isotopes_device[:10]:
    conf_level = 'HIGH' if iso['confidence'] >= 70 else 'MEDIUM' if iso['confidence'] >= 40 else 'LOW'
    print(f"  * {iso['isotope']:<12s} - {conf_level:<8s} ({iso['confidence']:.1f}% - {iso['matches']}/{iso['total_lines']} peaks)")

print("\n" + "="*80)
print("OPTION B: RECALCULATED (3.0 keV/channel)")
print("="*80)

peaks_recalc = detect_peaks(energies_recalc, counts)
print(f"\nDetected {len(peaks_recalc)} peaks")
if peaks_recalc:
    print("\nTop 10 peaks:")
    for i, peak in enumerate(peaks_recalc[:10]):
        print(f"  {i+1}. {peak['energy']:.2f} keV ({peak['counts']:.0f} counts)")

isotopes_recalc = identify_isotopes(peaks_recalc, energy_tolerance=30, mode='simple')
print(f"\n> Isotopes identified: {len(isotopes_recalc)}")
for iso in isotopes_recalc[:10]:
    conf_level = 'HIGH' if iso['confidence'] >= 70 else 'MEDIUM' if iso['confidence'] >= 40 else 'LOW'
    print(f"  * {iso['isotope']:<12s} - {conf_level:<8s} ({iso['confidence']:.1f}% - {iso['matches']}/{iso['total_lines']} peaks)")

print("\n" + "="*80)
print("PEAK POSITION COMPARISON")
print("="*80)

print("\nDevice vs Recalculated peak energies:")
for i in range(min(len(peaks_device), len(peaks_recalc), 10)):
    dev_energy = peaks_device[i]['energy']
    rec_energy = peaks_recalc[i]['energy']
    diff = dev_energy - rec_energy
    print(f"  Peak {i+1}: {dev_energy:7.2f} keV (device) -> {rec_energy:7.2f} keV (recalc) | Diff: {diff:+7.2f} keV")

print("\n" + "="*80)
print("ISOTOPE IDENTIFICATION COMPARISON")
print("="*80)

isotopes_device_set = set(iso['isotope'] for iso in isotopes_device)
isotopes_recalc_set = set(iso['isotope'] for iso in isotopes_recalc)

only_in_device = isotopes_device_set - isotopes_recalc_set
only_in_recalc = isotopes_recalc_set - isotopes_device_set
in_both = isotopes_device_set & isotopes_recalc_set

if in_both:
    print(f"\nIdentified in BOTH:")
    for iso_name in sorted(in_both):
        dev_iso = next(iso for iso in isotopes_device if iso['isotope'] == iso_name)
        rec_iso = next(iso for iso in isotopes_recalc if iso['isotope'] == iso_name)
        print(f"  * {iso_name:<12s} | Device: {dev_iso['confidence']:5.1f}% | Recalc: {rec_iso['confidence']:5.1f}%")

if only_in_device:
    print(f"\n[!] ONLY with Device Calibration:")
    for iso_name in sorted(only_in_device):
        iso_data = next(iso for iso in isotopes_device if iso['isotope'] == iso_name)
        conf_level = 'HIGH' if iso_data['confidence'] >= 70 else 'MEDIUM' if iso_data['confidence'] >= 40 else 'LOW'
        print(f"  * {iso_name} - {conf_level} ({iso_data['confidence']:.1f}%)")

if only_in_recalc:
    print(f"\n[+] ONLY with 3 keV/ch Recalculation:")
    for iso_name in sorted(only_in_recalc):
        iso_data = next(iso for iso in isotopes_recalc if iso['isotope'] == iso_name)
        conf_level = 'HIGH' if iso_data['confidence'] >= 70 else 'MEDIUM' if iso_data['confidence'] >= 40 else 'LOW'
        print(f"  * {iso_name} - {conf_level} ({iso_data['confidence']:.1f}%)")

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)
print("\nExpected for uranium glass: U-238, Th-234, Pa-234m, Bi-214, Pb-214")
print("\nIf Option B (3 keV/ch) identifies these isotopes better, then device calibration is wrong.")
print("If Option A (device) identifies them better, then device calibration is correct.")
print("="*80)


