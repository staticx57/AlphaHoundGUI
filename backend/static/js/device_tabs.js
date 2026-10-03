
/**
 * Switching between the AlphaHound and Radiacode connection rows.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 */
export function setupDeviceTabs({  } = {}) {
    // ============================================================
    // Device Type Tab Switching (AlphaHound / Radiacode)
    // Now toggles connection rows, not entire panels
    // ============================================================
    const tabAlphahound = document.getElementById('tab-alphahound');
    const tabRadiacode = document.getElementById('tab-radiacode');
    const alphahoundRow = document.getElementById('alphahound-connection-row');
    const radiacodeRow = document.getElementById('radiacode-connection-row');
    const deviceTitle = document.getElementById('device-title');

    if (tabAlphahound && tabRadiacode && alphahoundRow && radiacodeRow) {
        tabAlphahound.addEventListener('click', () => {
            // Update tab active state
            tabAlphahound.classList.add('active');
            tabRadiacode.classList.remove('active');

            // Show AlphaHound connection, hide Radiacode
            alphahoundRow.style.display = 'flex';
            radiacodeRow.style.display = 'none';
            const quickPanel = document.getElementById('device-quick-panel');
            if (quickPanel) quickPanel.dataset.device = 'alphahound';

            // Update title
            if (deviceTitle) deviceTitle.textContent = 'AlphaHound Device';
        });

        tabRadiacode.addEventListener('click', () => {
            // Update tab active state
            tabRadiacode.classList.add('active');
            tabAlphahound.classList.remove('active');

            // Show Radiacode connection, hide AlphaHound
            radiacodeRow.style.display = 'flex';
            alphahoundRow.style.display = 'none';
            const quickPanel = document.getElementById('device-quick-panel');
            if (quickPanel) quickPanel.dataset.device = 'radiacode';

            // Update title
            if (deviceTitle) deviceTitle.textContent = 'Radiacode Device';
        });
    }
}
