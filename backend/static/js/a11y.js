/**
 * Keyboard and screen-reader behaviour that applies everywhere, so each dialog and image does not have to repeat it:
 *
 *  - every .modal is a labelled aria-modal dialog: opening it moves focus inside, Tab and Shift+Tab stay inside, Esc
 *    closes it (through its own close button, so the app's close logic still runs) and focus returns to what opened it;
 *  - images without an alt attribute (the decorative icons, including those in dynamically built markup) get alt="",
 *    so a screen reader does not read out file names.
 *
 * Opening and closing are detected from the dialog's display, so the existing code that shows and hides the modals
 * (style.display = 'flex' / 'none') keeps working unchanged.
 */

export const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), '
    + 'textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/**
 * Which element should take focus when Tab (or Shift+Tab) is pressed inside a trap. Returns the element to focus, or
 * null to let the browser move focus normally (the focus is somewhere in the middle of the list).
 */
export function nextFocus(list, active, backwards) {
    if (!list.length) return null;
    const first = list[0];
    const last = list[list.length - 1];
    const idx = list.indexOf(active);
    if (idx === -1) return backwards ? last : first;            // focus is outside the list (e.g. on the dialog box itself)
    if (backwards && active === first) return last;
    if (!backwards && active === last) return first;
    return null;
}

const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);

export function focusableIn(root) {
    return [...root.querySelectorAll(FOCUSABLE)].filter(isVisible);
}

const stack = [];                   // open dialogs, topmost last
const info = new Map();             // dialog -> { opener }

function closeDialog(modal) {
    const button = modal.querySelector('.close-btn, [data-close]');
    if (button) button.click();
    else modal.style.display = 'none';
}

function onKeyDown(event) {
    const modal = stack[stack.length - 1];
    if (!modal) return;
    if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeDialog(modal);
    } else if (event.key === 'Tab') {
        const target = nextFocus(focusableIn(modal), document.activeElement, event.shiftKey);
        if (target) {
            event.preventDefault();
            target.focus();
        } else if (!modal.contains(document.activeElement)) {
            event.preventDefault();
            (focusableIn(modal)[0] || modal).focus();
        }
    }
}

function opened(modal) {
    if (info.has(modal)) return;
    info.set(modal, { opener: document.activeElement });
    stack.push(modal);
    if (stack.length === 1) document.addEventListener('keydown', onKeyDown, true);
    const box = modal.querySelector('.modal-content') || modal;
    if (!box.hasAttribute('tabindex')) box.setAttribute('tabindex', '-1');
    // first control that is not the close button, so a dialog does not open on "close"
    const list = focusableIn(box);
    const first = list.find((el) => !el.classList.contains('close-btn')) || list[0] || box;
    requestAnimationFrame(() => first.focus());
}

function closed(modal) {
    const entry = info.get(modal);
    if (!entry) return;
    info.delete(modal);
    const at = stack.indexOf(modal);
    if (at !== -1) stack.splice(at, 1);
    if (!stack.length) document.removeEventListener('keydown', onKeyDown, true);
    const { opener } = entry;
    if (opener && opener !== document.body && document.contains(opener)) opener.focus();
}

function label(modal) {
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    if (modal.hasAttribute('aria-label') || modal.hasAttribute('aria-labelledby')) return;
    const heading = modal.querySelector('h1, h2, h3, h4');
    if (heading) {
        if (!heading.id) heading.id = `${modal.id || 'dialog'}-title`;
        modal.setAttribute('aria-labelledby', heading.id);
    } else {
        modal.setAttribute('aria-label', 'Dialog');
    }
}

export function initDialogs(root = document) {
    root.querySelectorAll('.modal').forEach((modal) => {
        label(modal);
        let wasOpen = getComputedStyle(modal).display !== 'none';
        new MutationObserver(() => {
            const open = getComputedStyle(modal).display !== 'none';
            if (open === wasOpen) return;
            wasOpen = open;
            if (open) opened(modal); else closed(modal);
        }).observe(modal, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
    });
}

/** Decorative images (the icons) get alt="" unless the markup already says something. */
export function fixImageAlts(root = document) {
    root.querySelectorAll('img:not([alt])').forEach((img) => img.setAttribute('alt', ''));
}

export function initImageAlts() {
    fixImageAlts(document);
    new MutationObserver((records) => {
        for (const record of records) {
            record.addedNodes.forEach((node) => {
                if (node.nodeType !== 1) return;
                if (node.tagName === 'IMG' && !node.hasAttribute('alt')) node.setAttribute('alt', '');
                else if (node.querySelectorAll) fixImageAlts(node);
            });
        }
    }).observe(document.body, { childList: true, subtree: true });
}

export function initA11y() {
    initImageAlts();
    initDialogs();
}
