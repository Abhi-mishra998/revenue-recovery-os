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

// Activate by:
//   1. yarn add @sentry/react
//   2. uncomment the import in src/index.js and call initSentry()
//   3. set REACT_APP_SENTRY_DSN in Vercel/local env
//
// Left out of the build graph entirely so a missing @sentry/react can't
// break the production bundle.
//
/* eslint-disable */
// import * as Sentry from "@sentry/react";
//
// export function initSentry() {
//   const dsn = process.env.REACT_APP_SENTRY_DSN;
//   if (!dsn) return false;
//   Sentry.init({
//     dsn,
//     environment: process.env.REACT_APP_SENTRY_ENVIRONMENT || "development",
//     release: process.env.REACT_APP_SENTRY_RELEASE || undefined,
//     tracesSampleRate: Number(process.env.REACT_APP_SENTRY_TRACES_SAMPLE_RATE || 0.1),
//   });
//   return true;
// }
export {};
