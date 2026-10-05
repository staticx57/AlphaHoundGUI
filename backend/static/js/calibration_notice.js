/**
 * Energy-axis notice: when the calibration check finds the lines of the sources in the spectrum consistently off, say so above the
 * results and offer to apply the correction it measured. The server maps every energy back (true = (measured - offset) / gain),
 * which keeps the shape of a nonlinear axis, and analyses the spectrum again.
 * When the server already corrected a clearly drifted axis by itself (data.auto_calibration.applied), the notice says so and offers
 * Undo: the spectrum is analysed again on the axis it came with (data.original_energies), with no automatic correction.
 *
 * Everything shared with main.js is passed in: the current spectrum through a getter, "is a recording running" as a function, and
 * what to do with the re-analysed spectrum.
 *
 * @param {object} deps
 * @param {() => object} deps.getCurrentData
 * @param {() => boolean} deps.isAcquiring
 * @param {(data: object) => void} deps.applyAnalysis
 * @param {() => void} deps.openCalibration - opens the calibration tool (offered for a placeholder axis, in every UI mode)
 */
import { notify, notifyAuto } from './dialogs.js';

export function setupCalibrationNotice({ getCurrentData, isAcquiring, applyAnalysis, openCalibration } = {}) {
    const notice = document.getElementById('cal-notice');
    if (!notice) return;
    const text = document.getElementById('cal-notice-text');
    const apply = document.getElementById('btn-apply-axis-correction');
    const dismiss = document.getElementById('btn-dismiss-axis-notice');
    const undo = document.getElementById('btn-undo-auto-correction');
    const openTool = document.getElementById('btn-open-calibration');
    let dismissed = null;                              // the message the user dismissed: a different one shows again

    const refresh = (data) => {
        // No usable calibration (none at all, or the 0, 3, 6 ... keV placeholder in a file that names a real detector): nothing
        // to correct automatically, so the notice says what to do and opens the calibration tool, which Simple mode shows nowhere else
        const needed = data?.calibration_needed?.message;
        if (openTool) openTool.hidden = !needed;
        if (needed) {
            const show = needed !== dismissed && !isAcquiring();
            notice.hidden = !show;
            apply.hidden = true;
            if (undo) undo.hidden = true;
            if (show) text.textContent = needed;
            return;
        }
        const auto = data?.auto_calibration;
        const automatic = Boolean(auto?.applied && Array.isArray(data?.original_energies));
        const check = data?.calibration_check;
        const message = automatic ? auto.message : check?.message;
        const show = Boolean(message && (automatic || check.correction) && message !== dismissed && !isAcquiring());
        notice.hidden = !show;
        if (undo) undo.hidden = !automatic;
        apply.hidden = automatic;
        if (show) text.textContent = message;
    };

    document.addEventListener('spectrum-rendered', (e) => refresh(e.detail));

    openTool?.addEventListener('click', () => openCalibration?.());

    dismiss.addEventListener('click', () => {
        dismissed = text.textContent || null;          // whichever message is showing (automatic correction or check)
        notice.hidden = true;
    });

    undo?.addEventListener('click', async () => {
        const data = getCurrentData();
        if (!Array.isArray(data?.original_energies)) return;
        const metadata = { ...(data.metadata || {}) };
        delete metadata.energy_correction;
        undo.disabled = true;
        try {
            const response = await fetch('/analyze/reanalyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    energies: data.original_energies,
                    counts: data.counts,
                    metadata,
                    live_time: Number(data.metadata?.live_time) || 0,
                }),
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join('; ') : body.detail;
                throw new Error(detail || `Request failed (${response.status})`);
            }
            applyAnalysis(body);
            notify('Original energy axis restored and analysed again.', 'success');
        } catch (err) {
            notifyAuto(`Error: could not restore the original energy axis: ${err.message}`);
        } finally {
            undo.disabled = false;
        }
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
            notify(`Energy axis corrected (gain ${correction.gain.toFixed(3)}, offset ${correction.offset_keV.toFixed(1)} keV) and analysed again.`, 'success');
        } catch (err) {
            notifyAuto(`Error: could not correct the energy axis: ${err.message}`);
        } finally {
            apply.disabled = false;
            apply.textContent = original;
        }
    });
}
