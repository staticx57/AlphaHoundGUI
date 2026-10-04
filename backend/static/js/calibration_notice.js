/**
 * Energy-axis notice: when the calibration check finds the lines of the sources in the spectrum consistently off, say so above the
 * results and offer to apply the correction it measured. The server maps every energy back (true = (measured - offset) / gain),
 * which keeps the shape of a nonlinear axis, and analyses the spectrum again.
 *
 * Everything shared with main.js is passed in: the current spectrum through a getter, "is a recording running" as a function, and
 * what to do with the re-analysed spectrum.
 *
 * @param {object} deps
 * @param {() => object} deps.getCurrentData
 * @param {() => boolean} deps.isAcquiring
 * @param {(data: object) => void} deps.applyAnalysis
 */
import { notifyAuto } from './dialogs.js';

export function setupCalibrationNotice({ getCurrentData, isAcquiring, applyAnalysis } = {}) {
    const notice = document.getElementById('cal-notice');
    if (!notice) return;
    const text = document.getElementById('cal-notice-text');
    const apply = document.getElementById('btn-apply-axis-correction');
    const dismiss = document.getElementById('btn-dismiss-axis-notice');
    let dismissed = null;                              // the message the user dismissed: a different one shows again

    const refresh = (data) => {
        const check = data?.calibration_check;
        const message = check?.message;
        const show = Boolean(message && check.correction && message !== dismissed && !isAcquiring());
        notice.hidden = !show;
        if (show) text.textContent = message;
    };

    document.addEventListener('spectrum-rendered', (e) => refresh(e.detail));

    dismiss.addEventListener('click', () => {
        dismissed = getCurrentData()?.calibration_check?.message || null;
        notice.hidden = true;
    });

    apply.addEventListener('click', async () => {
        const data = getCurrentData();
        const correction = data?.calibration_check?.correction;
        if (!correction) return;
        const original = apply.textContent;
        apply.disabled = true;
        apply.textContent = 'Applying...';
        try {
            const response = await fetch('/analyze/correct-axis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    energies: data.energies,
                    counts: data.counts,
                    gain: correction.gain,
                    offset_keV: correction.offset_keV,
                    metadata: data.metadata || {},
                    live_time: Number(data.metadata?.live_time) || 0,
                }),
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join('; ') : body.detail;
                throw new Error(detail || `Request failed (${response.status})`);
            }
            applyAnalysis(body);
            notifyAuto(`Energy axis corrected (gain ${correction.gain.toFixed(3)}, offset ${correction.offset_keV.toFixed(1)} keV) and analysed again.`);
        } catch (err) {
            notifyAuto(`Error: could not correct the energy axis: ${err.message}`);
        } finally {
            apply.disabled = false;
            apply.textContent = original;
        }
    });
}
