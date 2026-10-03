import { debug } from './log.js';

/**
 * The simple / advanced / expert mode change.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.applyUIMode
 */
export function setupUiModeListener({ applyUIMode } = {}) {
    // UI Complexity Mode change listener
    document.querySelectorAll('input[name="ui-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const newMode = e.target.value;
            applyUIMode(newMode);
            debug(`[Settings] UI Mode changed to: ${newMode}`);
        });
    });
}
