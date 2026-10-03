/** Toast notifications, themed per the current data-theme. */

/**
 * Gets theme-aware colors for toast notifications.
 * NOTE: While CSS variables (--toast-*) exist for major themes, this function provides
 * hardcoded fallbacks for 11 vintage equipment themes that haven't defined toast variables yet.
 * These fallbacks ensure toasts match each theme's aesthetic. Ideally, all themes would
 * define --toast-success/warning/info/error, but that requires adding 44 more color definitions to style.css.
 * @param {'success'|'warning'|'info'} type - The type of toast notification
 * @param {string} theme - The current theme name (dark, light, nuclear, toxic, scifi, cyberpunk)
 * @returns {{bg: string, border: string, shadow: string}} Color configuration object
 */
function getToastColors(type, theme) {
    // Define color schemes for each theme
    const themeColors = {
        'dark': {
            success: { bg: '#10b981', border: '#10b981', shadow: 'rgba(16, 185, 129, 0.3)' },
            warning: { bg: '#f59e0b', border: '#f59e0b', shadow: 'rgba(245, 158, 11, 0.3)' },
            info: { bg: '#3b82f6', border: '#3b82f6', shadow: 'rgba(59, 130, 246, 0.3)' },
            error: { bg: '#ef4444', border: '#ef4444', shadow: 'rgba(239, 68, 68, 0.3)' }
        },
        'light': {
            success: { bg: '#10b981', border: '#059669', shadow: 'rgba(16, 185, 129, 0.2)' },
            warning: { bg: '#f59e0b', border: '#d97706', shadow: 'rgba(245, 158, 11, 0.2)' },
            info: { bg: '#3b82f6', border: '#2563eb', shadow: 'rgba(59, 130, 246, 0.2)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.2)' }
        },
        'nuclear': {
            success: { bg: '#fbbf24', border: '#f59e0b', shadow: 'rgba(251, 191, 36, 0.4)' },
            warning: { bg: '#f59e0b', border: '#ea580c', shadow: 'rgba(245, 158, 11, 0.4)' },
            info: { bg: '#fbbf24', border: '#f59e0b', shadow: 'rgba(251, 191, 36, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'toxic': {
            success: { bg: '#10b981', border: '#059669', shadow: 'rgba(16, 185, 129, 0.4)' },
            warning: { bg: '#84cc16', border: '#65a30d', shadow: 'rgba(132, 204, 22, 0.4)' },
            info: { bg: '#22c55e', border: '#16a34a', shadow: 'rgba(34, 197, 94, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'scifi': {
            success: { bg: '#00d9ff', border: '#3b82f6', shadow: 'rgba(0, 217, 255, 0.5)' },
            warning: { bg: '#a855f7', border: '#9333ea', shadow: 'rgba(168, 85, 247, 0.5)' },
            info: { bg: '#3b82f6', border: '#00d9ff', shadow: 'rgba(59, 130, 246, 0.5)' },
            error: { bg: '#ef4444', border: '#f87171', shadow: 'rgba(239, 68, 68, 0.5)' }
        },
        'cyberpunk': {
            success: { bg: '#fcee09', border: '#00f5ff', shadow: '0 0 20px rgba(252, 238, 9, 0.6), 0 0 40px rgba(0, 245, 255, 0.3)' },
            warning: { bg: '#ff006e', border: '#fcee09', shadow: '0 0 20px rgba(255, 0, 110, 0.6), 0 0 40px rgba(252, 238, 9, 0.3)' },
            info: { bg: '#00f5ff', border: '#fcee09', shadow: '0 0 20px rgba(0, 245, 255, 0.6), 0 0 40px rgba(252, 238, 9, 0.3)' },
            error: { bg: '#ff006e', border: '#ef4444', shadow: '0 0 20px rgba(255, 0, 110, 0.6), 0 0 40px rgba(239, 68, 68, 0.3)' }
        },
        // Vintage Equipment Themes
        'eberline': {
            success: { bg: '#c9a227', border: '#e07b39', shadow: 'rgba(201, 162, 39, 0.4)' },
            warning: { bg: '#e07b39', border: '#ff6b35', shadow: 'rgba(224, 123, 57, 0.4)' },
            info: { bg: '#c9a227', border: '#e07b39', shadow: 'rgba(201, 162, 39, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'fluke': {
            success: { bg: '#ffc107', border: '#ff9800', shadow: 'rgba(255, 193, 7, 0.4)' },
            warning: { bg: '#ff9800', border: '#ff5722', shadow: 'rgba(255, 152, 0, 0.4)' },
            info: { bg: '#ffc107', border: '#ff9800', shadow: 'rgba(255, 193, 7, 0.4)' },
            error: { bg: '#ff5722', border: '#f44336', shadow: 'rgba(255, 87, 34, 0.4)' }
        },
        'oscilloscope': {
            success: { bg: '#33ff66', border: '#00cc44', shadow: 'rgba(51, 255, 102, 0.5)' },
            warning: { bg: '#66cc88', border: '#33ff66', shadow: 'rgba(102, 204, 136, 0.4)' },
            info: { bg: '#00cc44', border: '#33ff66', shadow: 'rgba(0, 204, 68, 0.5)' },
            error: { bg: '#ff6666', border: '#ff3333', shadow: 'rgba(255, 102, 102, 0.5)' }
        },
        'nixie': {
            success: { bg: '#ff9500', border: '#ff6a00', shadow: '0 0 15px rgba(255, 149, 0, 0.6)' },
            warning: { bg: '#ff6a00', border: '#ff4400', shadow: '0 0 15px rgba(255, 106, 0, 0.6)' },
            info: { bg: '#ff7700', border: '#ff9500', shadow: '0 0 15px rgba(255, 119, 0, 0.6)' },
            error: { bg: '#ff4400', border: '#cc0000', shadow: '0 0 15px rgba(255, 68, 0, 0.6)' }
        },
        'civildefense': {
            success: { bg: '#ffd000', border: '#ffaa00', shadow: 'rgba(255, 208, 0, 0.5)' },
            warning: { bg: '#ffaa00', border: '#ff6600', shadow: 'rgba(255, 170, 0, 0.5)' },
            info: { bg: '#ffd000', border: '#ffaa00', shadow: 'rgba(255, 208, 0, 0.5)' },
            error: { bg: '#ff4400', border: '#cc0000', shadow: 'rgba(255, 68, 0, 0.5)' }
        },
        'tektronix': {
            success: { bg: '#00a2e8', border: '#66ccff', shadow: 'rgba(0, 162, 232, 0.5)' },
            warning: { bg: '#66ccff', border: '#00a2e8', shadow: 'rgba(102, 204, 255, 0.4)' },
            info: { bg: '#00a2e8', border: '#66ccff', shadow: 'rgba(0, 162, 232, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'keithley': {
            success: { bg: '#4a90d9', border: '#7eb8f0', shadow: 'rgba(74, 144, 217, 0.4)' },
            warning: { bg: '#7eb8f0', border: '#4a90d9', shadow: 'rgba(126, 184, 240, 0.4)' },
            info: { bg: '#4a90d9', border: '#7eb8f0', shadow: 'rgba(74, 144, 217, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'ludlum': {
            success: { bg: '#d4915c', border: '#c44536', shadow: 'rgba(212, 145, 92, 0.5)' },
            warning: { bg: '#c44536', border: '#ff5c47', shadow: 'rgba(196, 69, 54, 0.5)' },
            info: { bg: '#d4915c', border: '#c44536', shadow: 'rgba(212, 145, 92, 0.5)' },
            error: { bg: '#ff5c47', border: '#cc0000', shadow: 'rgba(255, 92, 71, 0.5)' }
        },
        'hp': {
            success: { bg: '#d4a574', border: '#e8c49a', shadow: 'rgba(212, 165, 116, 0.5)' },
            warning: { bg: '#e8c49a', border: '#d4a574', shadow: 'rgba(232, 196, 154, 0.4)' },
            info: { bg: '#d4a574', border: '#e8c49a', shadow: 'rgba(212, 165, 116, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'victoreen': {
            success: { bg: '#7cb68a', border: '#9ed4aa', shadow: 'rgba(124, 182, 138, 0.5)' },
            warning: { bg: '#9ed4aa', border: '#7cb68a', shadow: 'rgba(158, 212, 170, 0.4)' },
            info: { bg: '#7cb68a', border: '#9ed4aa', shadow: 'rgba(124, 182, 138, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'canberra': {
            success: { bg: '#26a69a', border: '#4dd0c5', shadow: 'rgba(38, 166, 154, 0.5)' },
            warning: { bg: '#4dd0c5', border: '#26a69a', shadow: 'rgba(77, 208, 197, 0.4)' },
            info: { bg: '#26a69a', border: '#4dd0c5', shadow: 'rgba(38, 166, 154, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        }
    };

    return themeColors[theme]?.[type] || themeColors['dark'][type];
}

/**
 * Displays a toast notification with theme-aware styling.
 * Toast automatically dismisses after 3 seconds.
 * @param {string} message - The message to display
 * @param {'success'|'warning'|'info'} [type='info'] - The type of toast
 * @returns {void}
 */
export function showToast(message, type = 'info') {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const colors = getToastColors(type, currentTheme);

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    // Special text color handling for cyberpunk theme
    const textColor = currentTheme === 'cyberpunk' && type === 'success' ? '#0d0208' : 'white';

    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${colors.bg};
        color: ${textColor};
        border: 2px solid ${colors.border};
        border-radius: 8px;
        box-shadow: ${typeof colors.shadow === 'string' && colors.shadow.includes('0 0') ? colors.shadow : `0 4px 12px ${colors.shadow}`};
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
        font-size: 14px;
        max-width: 350px;
        font-weight: 500;
    `;

    document.body.appendChild(toast);

    // Screen readers announce toasts; errors interrupt, the rest wait their turn
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

    // Auto-remove: 3 s, longer for long messages (they were native notifyAuto() text before) and for errors
    const lifetime = Math.min(12000, Math.max(type === 'error' ? 5000 : 3000, 1500 + message.length * 45));
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, lifetime);
}
