// Saved acquisitions on the server (data/acquisitions), as the History dialog lists them.
//
// File names: spectrum_<end>.n42 for a finished run, spectrum_<start>_in_progress.n42 while one runs, and
// spectrum_<start>_interrupted[...].n42 for a run cut short (crash, restart) whose partial spectrum was kept.

const KIND_LABEL = { complete: 'Complete', in_progress: 'In progress', interrupted: 'Interrupted' };

/**
 * A readable description of one saved run from GET /device/acquisitions.
 * @param {{name: string, kind: string}} run
 * @returns {{when: string, whenLabel: string, kind: string, detail: string}}
 */
export function describeSavedRun(run) {
    const m = /^spectrum_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})(?:_(.*))?\.n42$/.exec(run.name || '');
    const when = m ? `${m[1]} ${m[2]}:${m[3]}:${m[4]}` : (run.name || '');
    // the name gives the end of a finished run but the start of a partial one
    const whenLabel = !m ? '' : (run.kind === 'complete' ? 'saved' : 'started');
    const detail = m && m[5] ? m[5].replace(/^(in_progress|interrupted)_?/, '').replace(/_/g, ' ') : '';
    return { when, whenLabel, kind: KIND_LABEL[run.kind] || run.kind || '', detail };
}
