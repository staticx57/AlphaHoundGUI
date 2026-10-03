/**
 * The headline of a result: what the spectrum most likely is, how sure we are, and the numbers that frame it.
 *
 * Pure functions (no DOM) so the wording and the comparison rules can be tested. The page puts these in a card above
 * the chart, so the answer is visible without scrolling past the spectrum, the peaks table and the identification
 * panels.
 */

/** HIGH above 70 %, MEDIUM above 40 %, otherwise LOW (the same bands the identification lists use). */
export function confidenceLabel(confidence) {
    return confidence > 70 ? 'HIGH' : confidence > 40 ? 'MEDIUM' : 'LOW';
}

/** "Cs-137", "cs137" and " CS 137 " compare equal. */
export function normalizeName(name) {
    return String(name ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

/**
 * The headline identification from the line-matching results (sorted best first by the server).
 * state: 'uncalibrated' (no energy scale, so nothing can be identified), 'none' (nothing matched) or 'found'.
 */
export function summarizeIdentification({ isotopes, isCalibrated = true } = {}) {
    if (isCalibrated === false) return { state: 'uncalibrated' };
    const list = (Array.isArray(isotopes) ? isotopes : []).filter((i) => i && i.isotope);
    if (!list.length) return { state: 'none' };
    const top = list[0];
    const confidence = Number(top.confidence) || 0;
    return {
        state: 'found',
        name: top.isotope,
        confidence,
        label: top.confidence_label || confidenceLabel(confidence),
        also: list.slice(1, 4).map((i) => ({ name: i.isotope, confidence: Number(i.confidence) || 0 })),
    };
}

/**
 * Do the line matching and the neural net agree?
 * 'agree' = same top isotope; 'partial' = the net's top is another line-matching result, or line matching's top is
 * among the net's top three; 'differ' = neither; 'none' = one of them has no answer.
 */
export function compareIdentifications(lineSummary, predictions) {
    const ai = (Array.isArray(predictions) ? predictions : []).filter((p) => p && p.isotope && !p.suppressed);
    if (!lineSummary || lineSummary.state !== 'found' || !ai.length) return { state: 'none', ai: ai[0] || null };
    const lineTop = normalizeName(lineSummary.name);
    const aiTop = normalizeName(ai[0].isotope);
    if (lineTop === aiTop) return { state: 'agree', ai: ai[0] };
    const lineNames = [lineSummary.name, ...(lineSummary.also || []).map((a) => a.name)].map(normalizeName);
    const aiTop3 = ai.slice(0, 3).map((p) => normalizeName(p.isotope));
    if (lineNames.includes(aiTop) || aiTop3.includes(lineTop)) return { state: 'partial', ai: ai[0] };
    return { state: 'differ', ai: ai[0] };
}

/** For each peak, the names of the identified isotopes whose matched line sits on it (best match first). */
export function peakMatches(peaks, isotopes, tolerance = 1.5) {
    const list = Array.isArray(isotopes) ? isotopes : [];
    return (Array.isArray(peaks) ? peaks : []).map((peak) => {
        const hits = [];
        for (const iso of list) {
            const lines = Array.isArray(iso?.matched_peaks) ? iso.matched_peaks : [];
            if (lines.some((m) => Math.abs(Number(m.observed) - Number(peak.energy)) <= tolerance)) {
                hits.push({ name: iso.isotope, confidence: Number(iso.confidence) || 0 });
            }
        }
        return hits.sort((a, b) => b.confidence - a.confidence).map((h) => h.name);
    });
}

export function totalCounts(counts) {
    if (!Array.isArray(counts)) return 0;
    let sum = 0;
    for (const c of counts) sum += Number(c) || 0;
    return sum;
}

/** 987 -> "987", 12345 -> "12,345", 4.2e6 -> "4.20 M". */
export function formatCount(n) {
    if (!Number.isFinite(n)) return '--';
    if (n >= 1e9) return `${(n / 1e9).toFixed(2)} G`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(2)} M`;
    return Math.round(n).toLocaleString('en-US');
}

/** Seconds as "45 s", "12.5 min" or "2 h 05 min". */
export function formatDuration(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return '--';
    if (seconds < 60) return `${Math.round(seconds)} s`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(seconds < 600 ? 1 : 0)} min`;
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return `${h} h ${String(m).padStart(2, '0')} min`;
}

/** The time the spectrum was collected over, in seconds (null if the file does not say). */
export function liveSeconds(metadata) {
    const md = metadata || {};
    for (const key of ['live_time', 'live_time_s', 'acquisition_time', 'real_time', 'real_time_s', 'duration_s', 'device_duration_s']) {
        if (typeof md[key] === 'number' && md[key] > 0) return md[key];
    }
    if (typeof md.count_time_minutes === 'number' && md.count_time_minutes > 0) return md.count_time_minutes * 60;
    return null;
}

/** The numbers beside the verdict. */
export function summaryFacts({ counts, metadata, peaks } = {}) {
    const total = totalCounts(counts);
    const live = liveSeconds(metadata);
    return {
        peaks: Array.isArray(peaks) ? peaks.length : 0,
        total,
        live,
        rate: live ? total / live : null,
    };
}

/** One sentence for a screen reader describing what the spectrum chart shows. */
export function describeSpectrum({ counts, peaks, metadata, isCalibrated = true } = {}) {
    const channels = Array.isArray(counts) ? counts.length : 0;
    const total = totalCounts(counts);
    const live = liveSeconds(metadata);
    const list = (Array.isArray(peaks) ? peaks : []).slice(0, 6)
        .map((p) => (isCalibrated === false ? `channel ${Math.round(p.energy)}` : `${Math.round(p.energy)} keV`));
    const more = Array.isArray(peaks) && peaks.length > 6 ? ` and ${peaks.length - 6} more` : '';
    const where = list.length ? `${peaks.length} peak${peaks.length > 1 ? 's' : ''}, at ${list.join(', ')}${more}.` : 'No peaks detected.';
    return `Gamma spectrum, ${channels} channels, ${formatCount(total)} counts${live ? ` collected over ${formatDuration(live)}` : ''}. ${where}`;
}

/** "Same spectrum, more counts" (a live acquisition growing), "new" (a different spectrum) or "same". */
export function spectrumChange(previous, current) {
    if (!previous) return 'new';
    if (previous.length !== current.length) return 'new';
    if (current.total < previous.total) return 'new';
    return current.total === previous.total ? 'same' : 'grown';
}

/** A cheap fingerprint of a spectrum for spectrumChange(). */
export function spectrumSignature(counts) {
    return { length: Array.isArray(counts) ? counts.length : 0, total: totalCounts(counts) };
}
