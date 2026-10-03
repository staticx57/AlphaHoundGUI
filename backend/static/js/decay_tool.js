/** Decay tool: engine list, prediction request and the log-scale chart. State lives here; main.js only wires the buttons. */
import { notifyAuto } from './dialogs.js';
import { seriesPalette, readThemeColors } from './palette.js';
import { chartTheme, themeGlowPlugin } from './chart_theme.js';
import { durationToDays, formatBq, describeDecayResult, forLogAxis, activityAxisRange } from './decay_view.js';

// Globals for Decay Chart
let decayChartInstance = null;
let decayResult = null;   // the last prediction, kept so a theme change can redraw the chart

/**
 * Populate the decay engine selector from the backend, marking engines whose
 * library is not installed. Without this the menu offers engines that silently
 * fall back to the built-in solver.
 */
export async function loadDecayEngines() {
    const select = document.getElementById('decay-engine-select');
    if (!select) return;

    try {
        const response = await fetch('/analyze/decay-engines');
        if (!response.ok) return;
        const { engines, default: defaultEngine, isotopes } = await response.json();

        const list = document.getElementById('decay-isotope-list');
        if (list && Array.isArray(isotopes) && isotopes.length) {
            list.replaceChildren(...isotopes.map((iso) => {
                const option = document.createElement('option');
                option.value = iso.name;
                option.label = `${iso.name} (${iso.half_life})`;
                return option;
            }));
        }

        select.innerHTML = '';
        const auto = document.createElement('option');
        auto.value = 'auto';
        auto.textContent = `Auto (${defaultEngine})`;
        select.appendChild(auto);

        for (const engine of engines) {
            const option = document.createElement('option');
            option.value = engine.name;
            option.textContent = engine.available
                ? engine.description
                : `${engine.description} — not installed`;
            option.disabled = !engine.available;
            select.appendChild(option);
        }
        select.value = 'auto';
    } catch (e) {
        console.warn('Could not load decay engines, keeping static list:', e);
    }
}


export async function runDecayPrediction() {
    const isotope = document.getElementById('decay-isotope').value.trim();
    const activity = parseFloat(document.getElementById('decay-activity').value);
    const duration = parseFloat(document.getElementById('decay-duration').value);
    const unit = document.getElementById('decay-duration-unit')?.value || 'years';
    const engineSelect = document.getElementById('decay-engine-select');
    const engine = engineSelect ? engineSelect.value : 'auto';
    const info = document.getElementById('decay-info');
    if (!isotope) return notifyAuto('Enter an isotope, for example Cs-137.');
    if (!(activity > 0)) return notifyAuto('The starting activity must be more than zero.');
    if (!(duration > 0)) return notifyAuto('The duration must be more than zero.');

    try {
        const response = await fetch('/analyze/decay-prediction', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                isotope: isotope,
                initial_activity_bq: activity,
                duration_days: durationToDays(duration, unit),
                engine: engine
            })
        });

        if (!response.ok) {
            let errorMsg = "Prediction failed";
            try {
                const err = await response.json();
                if (err.detail) errorMsg = typeof err.detail === 'string' ? err.detail : 'Check the values entered.';
            } catch (ignore) { }
            throw new Error(errorMsg);
        }

        const result = await response.json();
        decayResult = result;
        renderDecayChart(result);

    } catch (e) {
        console.error(e);
        if (info) info.textContent = '';
        notifyAuto(e.message);
    }
}

function renderDecayChart(result) {
    if (decayChartInstance) {
        decayChartInstance.destroy();
    }

    const th = chartTheme();
    const names = result.isotopes;
    const colors = seriesPalette(readThemeColors(), names.length);
    const dashes = [[], [7, 4], [2, 3], [9, 3, 2, 3]];       // colour is never the only cue
    const labels = result.time_labels;
    const range = activityAxisRange(result);

    const datasets = names.map((iso, i) => ({
        label: iso,
        data: forLogAxis(result.activities[iso]),
        borderColor: colors[i],
        backgroundColor: 'transparent',
        borderDash: dashes[i % dashes.length],
        borderWidth: th.lineWidth,
        pointRadius: 0,
        spanGaps: false,
        tension: Math.min(0.4, th.tension),
    }));

    const ctx = document.getElementById('decayChart');
    if (!ctx) return console.error('Decay chart canvas not found');

    const notes = describeDecayResult(result);
    const info = document.getElementById('decay-info');
    if (info) info.textContent = [...notes.warnings, notes.info].join(' \u00b7 ');
    ctx.setAttribute('aria-label', `Decay of ${result.isotope}: ${names.length} nuclides over ${labels[labels.length - 1]}. ${notes.info}`);

    decayChartInstance = new Chart(ctx.getContext('2d'), {
        type: 'line',
        plugins: [themeGlowPlugin],
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                title: {
                    display: true,
                    text: `Decay of ${result.isotope} over ${labels[labels.length - 1]}`,
                    color: th.textSecondary,
                    font: { family: th.font }
                },
                legend: { position: 'right', labels: { color: th.textSecondary, font: { family: th.font }, usePointStyle: false } },
                themeGlow: { blur: th.glow },
                tooltip: {
                    backgroundColor: th.card, titleColor: th.text, bodyColor: th.text, borderColor: th.grid, borderWidth: 1,
                    titleFont: { family: th.font }, bodyFont: { family: th.font },
                    callbacks: { label: (item) => `${item.dataset.label}: ${formatBq(item.parsed.y)}` }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Time since the start', color: th.textSecondary, font: { family: th.font } },
                    grid: { color: th.grid, borderDash: th.gridDash },
                    ticks: { color: th.textSecondary, font: { family: th.font }, maxTicksLimit: 8, maxRotation: 0 }
                },
                y: {
                    type: 'logarithmic',
                    min: range.min,
                    max: range.max,
                    title: { display: true, text: 'Activity (Bq)', color: th.textSecondary, font: { family: th.font } },
                    grid: { color: th.grid, borderDash: th.gridDash },
                    ticks: {
                        color: th.textSecondary,
                        font: { family: th.font },
                        callback: function (value) {
                            // one tick per decade
                            const log10 = Math.log10(value);
                            return Math.abs(log10 - Math.round(log10)) < 1e-9 ? formatBq(value) : null;
                        }
                    }
                }
            }
        }
    });
}

/** A theme switch changes the chart's look: redraw the last prediction, if there is one. */
export function redrawDecayChart() {
    if (decayChartInstance && decayResult) renderDecayChart(decayResult);
}
