import { calUI } from './calibration.js';
import { notifyAuto } from './dialogs.js';
import { showToast } from './toast.js';

/**
 * SNIP background removal and calibration.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.chartManager
 * @param {*} deps.applyCalibration
 * @param {*} deps.getCurrentData
 */
export function setupSnipAndCalibration({ chartManager, applyCalibration, getCurrentData } = {}) {
    // SNIP Auto-Background Removal (Visual Only - preserves original analysis)
    document.getElementById('btn-snip-bg').addEventListener('click', async () => {
        if (!getCurrentData() || !getCurrentData().counts) {
            notifyAuto('No spectrum loaded to remove background from.');
            return;
        }

        const btn = document.getElementById('btn-snip-bg');
        const statusEl = document.getElementById('bg-status');
        const originalText = btn.textContent;

        btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 14px; height: 14px;"> Processing...';
        btn.disabled = true;

        try {
            const response = await fetch('/analyze/snip-background', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    counts: getCurrentData().counts,
                    iterations: 24,
                    reanalyze: false  // Visual only - don't re-analyze
                })
            });

            if (!response.ok) throw new Error('SNIP analysis failed');

            const result = await response.json();

            // Store original counts for potential restore
            if (!getCurrentData()._originalCounts) {
                getCurrentData()._originalCounts = [...getCurrentData().counts];
            }

            // Sync peaks to background-subtracted data (visual fix)
            // Finds the new Y-value (net_counts) for each peak's energy
            const adjustedPeaks = getCurrentData().peaks.map(p => {
                let bestIdx = 0;
                let minDiff = Infinity;

                // Find index corresponding to peak energy
                for (let i = 0; i < getCurrentData().energies.length; i++) {
                    const diff = Math.abs(getCurrentData().energies[i] - p.energy);
                    if (diff < minDiff) {
                        minDiff = diff;
                        bestIdx = i;
                    }
                }
                // Return copy with updated counts
                return { ...p, counts: result.net_counts[bestIdx] };
            });

            // Update ONLY the chart display - preserve analysis results
            chartManager.render(getCurrentData().energies, result.net_counts, adjustedPeaks, chartManager.getScaleType());

            // Update status - make clear this is visual only
            statusEl.innerHTML = '<img src="/static/icons/check.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Background removed <em>(chart only - analysis unchanged)</em>';
            statusEl.style.color = '#10b981';
            const bgIndicator = document.getElementById('bg-active-indicator');
            if (bgIndicator) bgIndicator.style.display = 'inline';

            showToast('Background removed from chart (analysis preserved)', 'success');
        } catch (err) {
            console.error('SNIP background error:', err);
            statusEl.textContent = 'Error: ' + err.message;
            statusEl.style.color = '#ef4444';
            showToast('Failed to remove background', 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    });

    // Calibration
    const btnCalibrate = document.getElementById('btn-calibrate-mode');
    if (btnCalibrate) btnCalibrate.addEventListener('click', () => calUI.show());

    // Listen for calibration application
    document.addEventListener('calibrationApplied', (e) => {
        applyCalibration(e.detail.slope, e.detail.intercept);
    });

    // NOTE: Scale toggle, reset zoom, and compare mode listeners are already registered above (lines 347-398)
    // Duplicate registrations removed to prevent double-execution
}
