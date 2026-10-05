import { setupDoseAndAlertSettings } from './dose_alert_settings.js';
import { showToast } from './toast.js';
import { escapeHtml } from './html.js';
import { describeSavedRun } from './saved_runs.js';

/**
 * The settings modal (mode, sliders, apply, reset) and the history modal.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.ui
 * @param {*} deps.alertCenter
 * @param {*} deps.applyUIMode
 * @param {*} deps.loadFromHistory
 * @param {*} deps.getCurrentData
 * @param {*} deps.getSettings
 * @param {*} deps.listSavedRuns - () => Promise of the runs the server saved
 * @param {*} deps.openSavedRun - (name) => Promise<boolean>, true when it was loaded
 */
export function setupSettingsAndHistory({ ui, alertCenter, applyUIMode, loadFromHistory, getCurrentData, getSettings,
                                          listSavedRuns, openSavedRun } = {}) {
    // Settings Modal
    document.getElementById('btn-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'flex';
    });

    document.getElementById('close-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'none';
    });
    setupDoseAndAlertSettings({ ui, alertCenter });

    // Simple/Advanced Mode Toggle
    document.querySelectorAll('input[name="analysis-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const advancedPanel = document.getElementById('advanced-settings');
            if (e.target.value === 'advanced') {
                advancedPanel.style.display = 'block';
                getSettings().mode = 'advanced';
            } else {
                advancedPanel.style.display = 'none';
                getSettings().mode = 'simple';
            }
        });
    });

    // Slider Value Displays
    document.getElementById('isotope-confidence')?.addEventListener('input', (e) => {
        document.getElementById('iso-conf-val').textContent = e.target.value;
    });

    document.getElementById('chain-confidence')?.addEventListener('input', (e) => {
        document.getElementById('chain-conf-val').textContent = e.target.value;
    });

    document.getElementById('energy-tolerance')?.addEventListener('input', (e) => {
        document.getElementById('energy-tol-val').textContent = e.target.value;
    });

    // Apply Settings
    document.getElementById('btn-apply-settings')?.addEventListener('click', () => {
        // Get current mode
        const mode = document.querySelector('input[name="analysis-mode"]:checked').value;

        // Update settings from UI
        getSettings().mode = mode;
        if (mode === 'advanced') {
            getSettings().isotope_min_confidence = parseFloat(document.getElementById('isotope-confidence').value);
            getSettings().chain_min_confidence = parseFloat(document.getElementById('chain-confidence').value);
            getSettings().energy_tolerance = parseFloat(document.getElementById('energy-tolerance').value);
        }

        // Save to localStorage
        localStorage.setItem('analysisSettings', JSON.stringify(getSettings()));

        // Apply UI Complexity Mode (controls panel visibility)
        const uiModeRadio = document.querySelector('input[name="ui-mode"]:checked');
        const uiMode = uiModeRadio ? uiModeRadio.value : 'simple';
        getSettings().uiMode = uiMode;
        applyUIMode(uiMode);

        // Close modal
        document.getElementById('settings-modal').style.display = 'none';

        // Re-analyze current data if loaded
        if (getCurrentData()) {
            showToast('Settings applied. Re-upload or re-acquire to see changes.', 'info');
        } else {
            showToast('Settings saved.', 'success');
        }
    });

    // Reset to Defaults
    document.getElementById('btn-reset-defaults')?.addEventListener('click', () => {
        document.getElementById('isotope-confidence').value = 40;
        document.getElementById('iso-conf-val').textContent = '40';
        document.getElementById('chain-confidence').value = 30;
        document.getElementById('chain-conf-val').textContent = '30';
        document.getElementById('energy-tolerance').value = 20;
        document.getElementById('energy-tol-val').textContent = '20';
    });

    // History Modal  
    document.getElementById('btn-history').addEventListener('click', () => {
        const modal = document.getElementById('history-modal');
        const historyList = document.getElementById('history-list');
        const history = JSON.parse(localStorage.getItem('fileHistory') || '[]');
        renderSavedRuns(listSavedRuns, openSavedRun);

        if (history.length === 0) {
            historyList.innerHTML = '<p style="text-align: center; color: #94a3b8;">No file history yet</p>';
        } else {
            historyList.innerHTML = history.map((item, index) => {
                // Check if item has data (legacy support check)
                const hasData = item.data && item.data.energies;
                const statusClass = hasData ? '' : 'opacity: 0.5; cursor: not-allowed;';
                const statusTitle = hasData ? 'Click to load' : 'Old history item (no data)';

                return `
                <div class="history-item" data-index="${index}" style="${statusClass}" title="${statusTitle}">
                    <div class="history-item-name">${item.filename}</div>
                    <div class="history-item-date">${new Date(item.timestamp).toLocaleString()}</div>
                    <div style="font-size: 0.875rem; margin-top: 0.5rem;">
                        ${item.preview.peakCount} peaks | ${(item.preview.isotopes || []).join(', ') || 'No isotopes'}
                    </div>
                </div>
            `;
            }).join('');

            // Add click listeners
            document.querySelectorAll('.history-item').forEach(el => {
                el.addEventListener('click', () => {
                    const index = parseInt(el.getAttribute('data-index'));
                    loadFromHistory(index);
                });
            });
        }
        modal.style.display = 'flex';
    });

    document.getElementById('close-history').addEventListener('click', () => {
        document.getElementById('history-modal').style.display = 'none';
    });

    // NOTE: Background subtraction listeners registered below with full set (btn-load-bg, btn-set-current-bg, btn-clear-bg)
}

// The runs the server saved: every acquisition, finished or not, whichever browser (if any) was watching it
async function renderSavedRuns(listSavedRuns, openSavedRun) {
    const box = document.getElementById('saved-runs-list');
    if (!box || !listSavedRuns) return;
    box.innerHTML = '<p class="saved-runs-note">Loading…</p>';
    let runs;
    try {
        runs = await listSavedRuns();
    } catch (e) {
        box.innerHTML = `<p class="saved-runs-note">${escapeHtml(e.message)}</p>`;
        return;
    }
    if (!runs.length) {
        box.innerHTML = '<p class="saved-runs-note">No acquisitions saved yet</p>';
        return;
    }
    box.innerHTML = runs.map((run, i) => {
        const d = describeSavedRun(run);
        const facts = [d.detail, `${Math.max(1, Math.round(run.size_bytes / 1024))} KB`,
            `modified ${new Date(run.modified).toLocaleString()}`].filter(Boolean).join(' · ');
        return `<button type="button" class="history-item saved-run" data-index="${i}" title="Open ${escapeHtml(run.name)}">
            <span class="history-item-name">${escapeHtml(d.whenLabel ? `${d.whenLabel} ${d.when}` : d.when)}</span>
            <span class="saved-run-kind saved-run-${escapeHtml(run.kind)}">${escapeHtml(d.kind)}</span>
            <span class="history-item-date">${escapeHtml(facts)}</span>
        </button>`;
    }).join('');
    box.querySelectorAll('.saved-run').forEach((el) => {
        el.addEventListener('click', async () => {
            if (await openSavedRun(runs[Number(el.dataset.index)].name)) {
                document.getElementById('history-modal').style.display = 'none';
            }
        });
    });
}
