// Metrics arrive about every 1.5 s. If nothing has arrived for this long, what is on
// screen is old news and must say so instead of looking current.
export const STALE_AFTER_MS = 8000

export const isStale = (at, now, limit = STALE_AFTER_MS) => at != null && now - at > limit
