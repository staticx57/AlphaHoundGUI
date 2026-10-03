import { debug } from './log.js';
import { showToast } from './toast.js';

/**
 * Theme dropdown, chart controls and the auto-scale toggle.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.chartManager
 * @param {*} deps.colors
 * @param {*} deps.reapplyIsotopeHighlights
 * @param {*} deps.updateChartScale
 * @param {*} deps.getCurrentData
 */
export function setupThemeAndChartControls({ chartManager, colors, reapplyIsotopeHighlights, updateChartScale, getCurrentData } = {}) {
    // Theme Dropdown
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        // Set initial value from localStorage
        const savedTheme = localStorage.getItem('theme') || 'dark';
        themeSelect.value = savedTheme;
        document.documentElement.setAttribute('data-theme', savedTheme);

        themeSelect.addEventListener('change', (e) => {
            const newTheme = e.target.value;
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);

            // Update chart colors for new theme
            chartManager.updateThemeColors();
            window.dispatchEvent(new Event('themechange'));   // channel panel, sparklines, replica colours

            if (getCurrentData()) {
                const scale = chartManager.getScaleType();
                chartManager.render(getCurrentData().energies, getCurrentData().counts, getCurrentData().peaks, scale);

                // Re-apply isotope highlights after theme change re-renders chart
                reapplyIsotopeHighlights();
            }
        });
    }

    // Chart Controls
    document.getElementById('btn-lin').addEventListener('click', (e) => {
        document.getElementById('btn-log').classList.remove('active');
        e.target.classList.add('active');
        updateChartScale('linear');
    });
    document.getElementById('btn-log').addEventListener('click', (e) => {
        document.getElementById('btn-lin').classList.remove('active');
        e.target.classList.add('active');
        updateChartScale('logarithmic');
    });
    document.getElementById('btn-reset-zoom').addEventListener('click', () => chartManager.resetZoom());

    // Auto-Scale Toggle
    document.getElementById('btn-auto-scale').addEventListener('click', (e) => {
        debug('[Main] Auto-scale button clicked, getCurrentData() exists:', !!getCurrentData());
        const isAutoScale = chartManager.toggleAutoScale();
        e.target.classList.toggle('active', isAutoScale);
        e.target.textContent = isAutoScale ? 'Auto-Scale' : 'Full Spectrum';
        // Re-render chart with new scale
        if (getCurrentData()) {
            chartManager.render(getCurrentData().energies, getCurrentData().counts, getCurrentData().peaks, chartManager.getScaleType());
        }
        showToast(isAutoScale ? 'Auto-scale enabled (zoom to data)' : 'Full spectrum view enabled', 'info');
    });
}
