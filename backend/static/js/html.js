/**
 * HTML escaping for text that ends up inside an innerHTML template: device names from Bluetooth scans, error
 * messages from the server, user-defined isotope names. Pure function, no DOM.
 */
const ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (c) => ENTITIES[c]);
}
