// Timed server polls that cannot overlap.
//
// setInterval fires on schedule whether or not the previous request has answered. When the server is slow the
// requests pile up behind the browser's six connections per host and the whole page stops responding (a long
// acquisition did exactly that). A tick that finds the previous poll still pending is skipped instead.

/** Wraps an async poll so calls made while one is pending do nothing (and resolve to undefined). */
export function nonOverlapping(poll) {
    let pending = false;
    return async function (...args) {
        if (pending) return undefined;
        pending = true;
        try {
            return await poll.apply(this, args);
        } finally {
            pending = false;
        }
    };
}
