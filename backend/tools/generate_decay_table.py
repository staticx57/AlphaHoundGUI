"""
Generate backend/decay_data.py: the decay data the built-in engine uses, taken from radioactivedecay (ICRP Publication 107).

The built-in engine has to work without any optional package, so its data is embedded. Writing it by hand is how the old
table ended up with 15 isotopes, no branching and no entry for Co-60; generating it keeps every value traceable.

    python backend/tools/generate_decay_table.py

Needs radioactivedecay (a development-time dependency only). Re-run after changing PARENTS.
"""
import math
import os
import sys

import radioactivedecay as rd

# Parents the built-in engine can start from; their whole decay chains come along.
PARENTS = [
    # natural series and the long-lived heads of their sub-series
    "U-238", "U-235", "U-234", "Th-232", "Th-230", "Th-228", "Ra-228", "Ra-226", "Rn-222", "Pb-210", "Po-210", "Ac-227", "Pa-231",
    "Np-237", "U-233",
    # primordial / cosmogenic
    "K-40", "Lu-176", "C-14", "H-3",
    # fission and activation products, calibration and industrial sources
    "Cs-137", "Cs-134", "Sr-90", "Co-60", "Co-57", "Ba-133", "Eu-152", "Eu-154", "Mn-54", "Zn-65", "Fe-55", "Na-22", "Ce-144",
    "Ru-106", "Sb-125", "Cd-109", "Gd-153", "Ir-192", "Se-75", "Ni-63", "Tl-204",
    # actinides used as sources
    "Am-241", "Pu-238", "Pu-239", "Pu-241", "Cm-244",
    # medical isotopes
    "I-131", "I-125", "Mo-99", "Tc-99m", "F-18", "Ga-67", "In-111", "Xe-133", "Tl-201", "Lu-177", "Yb-169", "Tm-170",
]

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "decay_data.py")


def node(name):
    n = rd.Nuclide(name)
    hl = n.half_life("s")
    stable = isinstance(hl, str) or hl is None or math.isinf(float(hl))
    if stable:
        return None, ()
    products = [(str(p), float(b)) for p, b in zip(n.progeny(), n.branching_fractions())]
    # keep the fraction exactly as the data gives it; drop zero branches and spontaneous fission ("SF" is not a nuclide;
    # its branches are around 1e-6 and below)
    return float(hl), tuple((p, b) for p, b in products if b > 0 and p != "SF")


def main():
    table = {}
    todo = list(PARENTS)
    while todo:
        name = todo.pop()
        if name in table:
            continue
        table[name] = node(name)
        todo.extend(p for p, _ in table[name][1])

    def key(name):
        z = rd.Nuclide(name).Z
        return (z, rd.Nuclide(name).A, name)

    lines = [
        '"""',
        "Decay data for the built-in decay engine (GENERATED: do not edit; run backend/tools/generate_decay_table.py).",
        "",
        f"Source: ICRP Publication 107 via radioactivedecay {rd.__version__}.",
        "Each entry: nuclide -> (half-life in seconds, ((daughter, branching fraction), ...)). A half-life of None means stable.",
        '"""',
        "",
        f'SOURCE = "ICRP Publication 107 (radioactivedecay {rd.__version__})"',
        f"PARENTS = {tuple(PARENTS)!r}",
        "",
        "DECAY_TABLE = {",
    ]
    for name in sorted(table, key=key):
        hl, products = table[name]
        lines.append(f"    {name!r}: ({hl!r}, {products!r}),")
    lines.append("}")
    lines.append("")
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    stable = sum(1 for v in table.values() if v[0] is None)
    print(f"{len(table)} nuclides ({stable} stable) from {len(PARENTS)} parents -> {os.path.normpath(OUT)}")


if __name__ == "__main__":
    sys.exit(main())
