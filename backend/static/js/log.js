/**
 * Diagnostic logging that stays quiet unless asked for: in the browser console run
 *     localStorage.alphahoundDebug = '1'
 * and reload. Warnings and errors still use console.warn / console.error directly.
 */
function debugEnabled() {
    try { return globalThis.localStorage?.getItem('alphahoundDebug') === '1'; } catch (e) { return false; }
}

export function debug(...args) {
    if (debugEnabled()) console.log(...args);
}
