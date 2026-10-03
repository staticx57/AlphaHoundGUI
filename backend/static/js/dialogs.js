/**
 * In-page notifications and dialogs, replacing the browser's alert() and confirm().
 *
 * Native popups block the page (a live dose readout freezes behind them), cannot be styled for the themes, and
 * cannot be driven by tests. These are non-blocking toasts and accessible modal dialogs (the native <dialog>
 * element: focus is trapped, Esc cancels, the page behind is inert).
 */

let notifier = null;

/** main.js registers its themed toast here, so every module can notify without importing main.js. */
export function setNotifier(fn) {
    notifier = fn;
}

/** Show a toast. type: info | success | warning | error. */
export function notify(message, type = 'info') {
    const text = String(message ?? '');
    if (notifier) notifier(text, type);
    else (type === 'error' ? console.error : console.warn)(text);
}

/** Pick a toast type from the wording of an old alert() message. */
export function classify(message) {
    const text = String(message ?? '');
    if (/error|failed|invalid|could not|cannot|not supported|unable/i.test(text)) return 'error';
    if (/success|applied|updated|imported|saved|cleared/i.test(text)) return 'success';
    return 'warning';
}

/** Drop-in for alert(): a toast typed from the message. */
export function notifyAuto(message) {
    notify(message, classify(message));
}

function open({ title, message, preformatted = false, buttons, initialFocus = 0 }) {
    return new Promise((resolve) => {
        const dialog = document.createElement('dialog');
        dialog.className = 'app-dialog';
        dialog.setAttribute('role', 'alertdialog');
        const titleId = `dlg-title-${Math.random().toString(36).slice(2, 8)}`;
        const bodyId = `dlg-body-${Math.random().toString(36).slice(2, 8)}`;
        dialog.setAttribute('aria-labelledby', titleId);
        dialog.setAttribute('aria-describedby', bodyId);

        const heading = document.createElement('h2');
        heading.id = titleId;
        heading.className = 'app-dialog-title';
        heading.textContent = title;

        const body = document.createElement(preformatted ? 'pre' : 'p');
        body.id = bodyId;
        body.className = 'app-dialog-body';
        body.textContent = message;

        const row = document.createElement('div');
        row.className = 'app-dialog-actions';
        let settled = false;
        const finish = (value) => {
            if (settled) return;
            settled = true;
            dialog.close();
            dialog.remove();
            resolve(value);
        };
        buttons.forEach((b, i) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = b.label;
            btn.className = `app-dialog-btn ${b.className || ''}`.trim();
            btn.dataset.value = String(b.value);
            btn.addEventListener('click', () => finish(b.value));
            row.appendChild(btn);
            if (i === initialFocus) btn.autofocus = true;
        });

        dialog.append(heading, body, row);
        // Esc and a click on the backdrop mean "no" / "close"
        dialog.addEventListener('cancel', (e) => { e.preventDefault(); finish(buttons.cancelValue); });
        dialog.addEventListener('click', (e) => { if (e.target === dialog) finish(buttons.cancelValue); });
        document.body.appendChild(dialog);
        dialog.showModal();
        row.children[initialFocus]?.focus();
    });
}

/**
 * Ask a yes/no question. Resolves true for the confirm button, false for cancel / Esc / backdrop.
 * A dangerous action focuses Cancel, so a stray Enter does not confirm it.
 */
export function confirmDialog(message, { title = 'Please confirm', okLabel = 'OK', cancelLabel = 'Cancel', danger = false } = {}) {
    const buttons = [
        { label: cancelLabel, value: false, className: 'app-dialog-cancel' },
        { label: okLabel, value: true, className: danger ? 'app-dialog-ok app-dialog-danger' : 'app-dialog-ok' },
    ];
    buttons.cancelValue = false;
    return open({ title, message, buttons, initialFocus: danger ? 0 : 1 });
}

/** Show text the user may want to read or copy (a configuration dump, for example). */
export function infoDialog(title, text) {
    const buttons = [{ label: 'Close', value: true, className: 'app-dialog-ok' }];
    buttons.cancelValue = true;
    return open({ title, message: text, preformatted: true, buttons });
}
