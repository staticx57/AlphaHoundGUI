"""Each frontend module is imported under one specifier everywhere.

Browsers key an ES module by its whole URL, query string included: `./ui.js?v=3.0` in one file and `./ui.js` in another load
the module twice and give two separate singletons (two `ui`, two `chartManager`). That happened here, quietly, because
main.js re-pointed window.chartManager at its own copy. Cache-busting versions belong in main.js only, and the other modules
receive what they need as arguments instead of importing a stateful singleton under a different name."""
import pathlib
import re
from collections import defaultdict

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
IMPORT = re.compile(r"""^\s*(?:import|export)\s[^'"]*?from\s+['"](\./[^'"]+)['"]|^\s*import\s+['"](\./[^'"]+)['"]""", re.M)


def specifiers_by_module():
    found = defaultdict(lambda: defaultdict(set))          # module stem -> specifier -> files importing it so
    for path in sorted(JS.glob("*.js")):
        for match in IMPORT.finditer(path.read_text(encoding="utf-8")):
            spec = match.group(1) or match.group(2)
            found[spec.split("?")[0]][spec].add(path.name)
    return found


def test_every_module_is_imported_under_a_single_specifier():
    conflicts = {stem: {spec: sorted(files) for spec, files in specs.items()}
                 for stem, specs in specifiers_by_module().items() if len(specs) > 1}
    assert not conflicts, "loaded twice by the browser (different specifiers): " + repr(conflicts)


def test_the_scan_sees_the_imports_it_is_meant_to_check():
    """A guard that finds nothing would pass for nothing."""
    found = specifiers_by_module()
    assert "./api.js" in found and "./ui.js" in found and "./charts.js" in found
    assert sum(len(files) for specs in found.values() for files in specs.values()) > 40
