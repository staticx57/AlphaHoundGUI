"""
Theme x viewport sweep (not collected by pytest): every theme at desktop and 390px width.
Flags horizontal page overflow, text below 3:1 contrast, and JS errors.

Needs playwright + Chrome and the server running at http://localhost:3200.

    python backend/tests/ui_theme_sweep.py
"""
import json, os
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ui_smoke_out", "sweep")
os.makedirs(OUT, exist_ok=True)
URL = os.environ.get("ALPHAHOUND_URL", "http://localhost:3200").rstrip("/") + "/"   # another port: ALPHAHOUND_URL
SPEC = os.path.join(HERE, "..", "data", "test_spectra", "synthetic_cesium137.n42")

JS_METRICS = r"""
() => {
  function lum(c){const a=c.map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)});return 0.2126*a[0]+0.7152*a[1]+0.0722*a[2]}
  function parse(s){const m=s.match(/rgba?\(([^)]+)\)/); if(!m) return null; const p=m[1].split(',').map(x=>parseFloat(x)); return {c:p.slice(0,3),a:p.length>3?p[3]:1}}
  function bgOf(el){let e=el;while(e){const p=parse(getComputedStyle(e).backgroundColor); if(p&&p.a>0.5) return p.c; e=e.parentElement} return [255,255,255]}
  function ratio(el){const fg=parse(getComputedStyle(el).color); if(!fg) return null; const bg=bgOf(el);
    const L1=lum(fg.c),L2=lum(bg); return (Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05)}
  const sels=['header h1, .logo, header .app-title','#device-title','.control-label','button.btn-primary','#peaks-table td, .peaks-table td, table td','.metadata-panel *','label','#theme-select','.data-hub-row summary, .card h3, h3','#xrf-container, #xrf-container *','.rs-name','.rs-note','.rs-facts dd','.rs-facts dt','.rs-kicker','.peak-match','.id-caption','.ai-note'];
  const low=[];
  for(const s of sels){document.querySelectorAll(s).forEach((el,i)=>{ if(i>12) return; const t=(el.textContent||'').trim(); if(!t||el.offsetParent===null) return; const r=ratio(el); if(r!==null&&r<3) low.push({sel:s,text:t.slice(0,30),ratio:+r.toFixed(2)})})}
  const overflow = document.documentElement.scrollWidth - window.innerWidth;
  // elements wider than viewport
  const wide=[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>window.innerWidth+2 && e.offsetParent!==null && getComputedStyle(e).position!=='fixed').slice(0,4).map(e=>(e.id?'#'+e.id:e.tagName.toLowerCase()+'.'+String(e.className).split(' ')[0]));
  return {overflow, wide, low: low.slice(0,6)}
}
"""

report = {}
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    probe = browser.new_page()
    probe.goto(URL, wait_until="networkidle")
    themes = probe.eval_on_selector_all("#theme-select option", "els => els.map(e => e.value)")
    probe.close()
    print(len(themes), "themes:", themes)

    for vp_name, vp in (("desktop", {"width": 1400, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        page.goto(URL, wait_until="networkidle")
        page.set_input_files("#file-input", SPEC)
        page.wait_for_selector("#dashboard", state="visible", timeout=20000)
        page.wait_for_timeout(1200)
        for t in themes:
            errs.clear()
            page.select_option("#theme-select", t)
            page.wait_for_timeout(350)
            m = page.evaluate(JS_METRICS)
            m["errors"] = list(errs)
            report[f"{vp_name}/{t}"] = m
            if vp_name == "mobile" or t in ("dark", "light", "nixie", "oscilloscope"):
                page.screenshot(path=os.path.join(OUT, f"{vp_name}_{t}.png"))
        ctx.close()
    browser.close()

json.dump(report, open(os.path.join(OUT, "report.json"), "w"), indent=1)
bad = 0
for k, m in report.items():
    issues = []
    if m["overflow"] > 2: issues.append(f"h-overflow {m['overflow']}px {m['wide']}")
    if m["low"]: issues.append("low contrast " + "; ".join(f"{x['text']!r}={x['ratio']}" for x in m["low"][:3]))
    if m["errors"]: issues.append("errors " + "; ".join(m["errors"][:2]))
    if issues:
        bad += 1
        print(k, "->", " | ".join(issues))
print(f"\n{len(report)} combos, {bad} with issues")
