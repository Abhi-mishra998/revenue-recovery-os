#!/usr/bin/env node
/**
 * Post-build: inline main.css into build/index.html and drop the <link>.
 *
 * Why: CRA emits `<link rel="stylesheet" href="/static/css/main.[hash].css">`
 * which is render-blocking — the browser stalls first paint until the CSS
 * downloads + parses. Lighthouse called this out as ~1,250 ms of render
 * block on slow 4G. The file is small enough (~15 KB raw / ~3 KB gzipped
 * with HTML compression) that inlining it is a clean win.
 *
 * No new deps — just node + fs + regex on the emitted index.html.
 */
const fs = require("fs");
const path = require("path");

const buildDir = path.join(__dirname, "..", "build");
const htmlPath = path.join(buildDir, "index.html");

if (!fs.existsSync(htmlPath)) {
  console.error("inline-css: build/index.html not found — skipping");
  process.exit(0);
}

let html = fs.readFileSync(htmlPath, "utf8");

// Find every <link rel="stylesheet" href="/static/css/...">. There's usually
// just one (CRA main.css), but loop in case future deps add more.
const linkRe = /<link[^>]+href="(\/static\/css\/[^"]+\.css)"[^>]*rel="stylesheet"[^>]*>|<link[^>]+rel="stylesheet"[^>]*href="(\/static\/css\/[^"]+\.css)"[^>]*>/g;

let matches = [...html.matchAll(linkRe)];
if (matches.length === 0) {
  console.log("inline-css: no /static/css/*.css <link> tags found — skipping");
  process.exit(0);
}

let inlinedBytes = 0;
for (const m of matches) {
  const tag = m[0];
  const href = m[1] || m[2];
  const cssPath = path.join(buildDir, href);
  if (!fs.existsSync(cssPath)) {
    console.warn(`inline-css: ${cssPath} missing — leaving <link> intact`);
    continue;
  }
  const css = fs.readFileSync(cssPath, "utf8");
  inlinedBytes += css.length;
  // CRA emits already-minified CSS, so inline directly. No re-minify pass needed.
  html = html.replace(tag, `<style>${css}</style>`);
}

fs.writeFileSync(htmlPath, html);
console.log(`inline-css: inlined ${matches.length} stylesheet(s), ${inlinedBytes} bytes total`);
