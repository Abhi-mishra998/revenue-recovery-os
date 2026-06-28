// Opt-in Sentry hook. Set REACT_APP_SENTRY_DSN to activate.
// @sentry/react is NOT a required dep — the lazy import means a missing
// package just logs a warning instead of crashing the bundle.
//
// To enable in prod:
//   yarn add @sentry/react
//   REACT_APP_SENTRY_DSN=https://...ingest.sentry.io/...
//   REACT_APP_SENTRY_ENVIRONMENT=production
//   REACT_APP_SENTRY_RELEASE=$(git rev-parse --short HEAD)
//
// Without the env var: noop, zero bytes shipped beyond this file.

export async function initSentry() {
  const dsn = process.env.REACT_APP_SENTRY_DSN;
  if (!dsn) return false;
  try {
    // Dynamic import keeps it out of the main bundle until activated.
    const Sentry = await import("@sentry/react");
    Sentry.init({
      dsn,
      environment: process.env.REACT_APP_SENTRY_ENVIRONMENT || "development",
      release: process.env.REACT_APP_SENTRY_RELEASE || undefined,
      tracesSampleRate: Number(process.env.REACT_APP_SENTRY_TRACES_SAMPLE_RATE || 0.1),
    });
    return true;
  } catch (e) {
    // @sentry/react not installed — silent in prod, console-warn in dev.
    // eslint-disable-next-line no-console
    if (process.env.NODE_ENV !== "production") {
      console.warn("[sentry] REACT_APP_SENTRY_DSN set but @sentry/react not installed. " +
                   "Run: yarn add @sentry/react");
    }
    return false;
  }
}
