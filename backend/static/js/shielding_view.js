/**
 * Shielding and emissions modal: how numbers are shown and the sentences around the tables (pure functions, no DOM).
 */

/** A length in cm with the unit that fits: 0.0123 -> "0.12 mm", 0.55 -> "0.55 cm", 154 -> "1.54 m". */
export function formatLength(cm) {
    if (typeof cm !== 'number' || !Number.isFinite(cm)) return '--';
    const abs = Math.abs(cm);
    if (abs >= 100) return `${Number((cm / 100).toPrecision(3))} m`;
    if (abs >= 0.1) return `${Number(cm.toPrecision(3))} cm`;
    if (abs === 0) return '0 cm';
    return `${Number((cm * 10).toPrecision(2))} mm`;
}

/** A transmitted fraction as a percentage; very small values are not rounded down to a misleading 0. */
export function formatPercent(fraction) {
    if (typeof fraction !== 'number' || !Number.isFinite(fraction)) return '--';
    const pct = fraction * 100;
    if (pct === 0) return '0 %';
    if (Math.abs(pct) < 0.001) return '< 0.001 %';
    if (Math.abs(pct) < 0.1) return `${Number(pct.toPrecision(2))} %`;
    if (Math.abs(pct) < 10) return `${Number(pct.toPrecision(3))} %`;
    return `${Math.round(pct)} %`;
}

/** The result of POST /analyze/shielding as one sentence, plus the caveat that always goes with it. */
export function describeShielding(result, materialName) {
    if (!result) return '';
    const material = (materialName || result.material || 'the material').toLowerCase();
    const caveat = 'Narrow beam: photons that scatter in the shield and still arrive are not counted, so a thick shield, or one close to the source, lets more through.';
    if (Array.isArray(result.lines)) {
        const through = `Through ${formatLength(result.thickness_cm)} of ${material}, ${formatPercent(result.transmission)} of ${result.isotope}'s gamma photons get through.`;
        const progeny = "These are the isotope's own lines: decay products that build up in a sealed source (Bi-214 and Pb-214 for Ra-226, for example) add their own, often harder, gamma rays.";
        return `${through} ${progeny} ${caveat}`;
    }
    const parts = [`At ${result.energy_kev} keV, ${material} halves the beam in ${formatLength(result.half_value_layer_cm)} and cuts it to a tenth in ${formatLength(result.tenth_value_layer_cm)}.`];
    if (typeof result.transmission === 'number') {
        parts.push(`${formatLength(result.thickness_cm)} lets ${formatPercent(result.transmission)} through.`);
    }
    return `${parts.join(' ')} ${caveat}`;
}

const CHANNEL_NAMES = { alpha: 'alpha', beta: 'beta', gamma: 'gamma' };

/** Which AlphaHound channels an isotope can show up in, and what it needs to do so. */
export function describeEmissions(emissions) {
    if (!emissions) return '';
    const channels = (emissions.channels || []).map((c) => CHANNEL_NAMES[c] || c);
    if (!channels.length) return `${emissions.isotope}: no alpha, beta or gamma lines above ${emissions.min_intensity_percent} %.`;
    const seen = channels.length === 1 ? `${channels[0]} channel` : `${channels.slice(0, -1).join(', ')} and ${channels[channels.length - 1]} channels`;
    const needs = [];
    if (channels.includes('alpha')) needs.push('an alpha source must be within a few centimetres of the detector window with nothing in between');
    if (channels.includes('beta')) needs.push('betas are stopped by a few millimetres of metal at most, so a source in a metal case shows no beta');
    return `${emissions.isotope} shows in the ${seen}${needs.length ? ': ' + needs.join('; ') : ''}.`;
}
