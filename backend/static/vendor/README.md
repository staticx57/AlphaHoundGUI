# Vendored front-end libraries

Served from here (not from a CDN) so the app works offline, on a LAN without internet, and does not change when a
library publishes a new release. All are MIT licensed.

| File | Library | Version | Source |
|---|---|---|---|
| `chart.umd.js` | Chart.js | 4.5.1 | https://cdn.jsdelivr.net/npm/chart.js |
| `chartjs-plugin-zoom.min.js` | chartjs-plugin-zoom | 2.0.1 | https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js |
| `chartjs-plugin-annotation.min.js` | chartjs-plugin-annotation | 3.0.1 | https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js |
| `hammer.min.js` | Hammer.js | 2.0.7 (the 2.0.8 path on cdnjs serves this build) | https://cdnjs.cloudflare.com/ajax/libs/hammer.js/2.0.8/hammer.min.js |

To update one, download the new file over the old one, change the version here, and run `python backend/tests/ui_smoke.py`.
