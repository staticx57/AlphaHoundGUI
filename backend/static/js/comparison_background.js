import { notifyAuto } from './dialogs.js';

/**
 * Sidebar toggles, spectrum comparison and background subtraction.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.chartManager
 * @param {*} deps.clearBackground
 * @param {*} deps.handleBackgroundFile
 * @param {*} deps.handleCompareFile
 * @param {*} deps.setBackground
 * @param {*} deps.toggleCompareMode
 * @param {*} deps.updateOverlayCount
 * @param {*} deps.getCurrentData
 * @param {*} deps.getOverlaySpectra
 * @param {*} deps.setOverlaySpectra
 */
export function setupComparisonAndBackground({ chartManager, clearBackground, handleBackgroundFile, handleCompareFile, setBackground, toggleCompareMode, updateOverlayCount, getCurrentData, getOverlaySpectra, setOverlaySpectra } = {}) {
    // Sidebar Toggles (Mobile/Top Bar)

    // Comparison
    document.getElementById('btn-compare').addEventListener('click', toggleCompareMode);
    document.getElementById('btn-add-file').addEventListener('click', () => {
        // [STABILITY] Memory Cap
        if (getOverlaySpectra().length >= 8) {
            notifyAuto('Maximum of 8 spectra allowed.');
            return;
        }
        document.getElementById('compare-file-input').click();
    });
    document.getElementById('compare-file-input').addEventListener('change', handleCompareFile);
    document.getElementById('btn-clear-overlays').addEventListener('click', () => {
        setOverlaySpectra([]);
        updateOverlayCount();
        chartManager.renderComparison([], 'linear');
    });

    // Background Subtraction
    document.getElementById('btn-load-bg').addEventListener('click', () => document.getElementById('bg-file-input').click());
    document.getElementById('bg-file-input').addEventListener('change', handleBackgroundFile);

    document.getElementById('btn-set-current-bg').addEventListener('click', () => {
        if (!getCurrentData()) return notifyAuto('No data loaded to use as background.');
        setBackground(getCurrentData(), 'Current Spectrum');
    });

    document.getElementById('btn-clear-bg').addEventListener('click', clearBackground);
}
