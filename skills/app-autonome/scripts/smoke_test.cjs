#!/usr/bin/env node
/*
 * Smoke test for a self-contained HTML tool: ACTUALLY opens the file over file://
 * in a headless Chromium and checks what the static validator cannot see: that no
 * JS error happens on load, that the key interface elements exist, AND that no
 * network request goes out.
 *
 * This is the deterministic test of the "kill the Wi-Fi" promise:
 *   - the browser context is switched OFFLINE (setOffline);
 *   - every request is intercepted BEFORE the page is created: file:// to the
 *     document itself = allowed, everything else = blocked AND logged (including
 *     WebSockets via routeWebSocket, and requests issued by a Blob worker);
 *   - after load, every .tab tab is clicked (a leak may wait for an interaction);
 *   - the live DOM is inspected: a <link rel="preconnect"> or dns-prefetch to the
 *     outside opens a connection WITHOUT emitting an interceptable request; only
 *     this DOM check can see it, and it fails the test just like a request would;
 *   - verdict: the ONLY request of the whole session must be the file itself.
 *     A dynamically built URL (new Image().src = "https://...") is invisible to
 *     static analysis: this is where it gets caught.
 *
 * Usage:
 *   node smoke_test.cjs path/to/tool.html
 *
 * Exit codes:
 *   0  = the page loads without errors, the expected controls are present,
 *        and zero outgoing requests
 *   1  = JS error, missing control, OR outgoing network request  -> FIX IT
 *   3  = no browser available (Playwright/Chromium missing) -> smoke test SKIPPED,
 *        fall back to the first-open checkpoint described to the user
 *
 * The static validator (validate_package.py) and this smoke test are complementary:
 * the former catches structure and file:// violations BEFORE execution, the latter
 * catches RUNTIME errors and network leaks at execution time. Neither proves the
 * BUSINESS LOGIC is right: that remains the business validation on real data.
 */
"use strict";

const path = require("path");
const { execSync } = require("child_process");

function resolvePlaywright() {
  const candidates = [];
  try { candidates.push(execSync("npm root -g", { encoding: "utf8" }).trim()); } catch (_) {}
  candidates.push(path.join(process.cwd(), "node_modules"));
  candidates.push("/usr/lib/node_modules");
  candidates.push("/usr/local/lib/node_modules");
  for (const base of candidates) {
    try { return require(path.join(base, "playwright")); } catch (_) {}
  }
  try { return require("playwright"); } catch (_) {}
  return null;
}

async function main() {
  const file = process.argv[2];
  if (!file) {
    console.log("Usage: node smoke_test.cjs path/to/tool.html");
    process.exit(2);
  }
  const abs = path.resolve(file);

  const pw = resolvePlaywright();
  if (!pw || !pw.chromium) {
    console.log("SKIPPED  Playwright/Chromium not found in this environment.");
    console.log("         The automated smoke test could not run. Compensate with the");
    console.log("         first-open checkpoint (Step 7 of the skill):");
    console.log("         ask the user to confirm what should appear on screen.");
    process.exit(3);
  }

  let browser;
  try {
    browser = await pw.chromium.launch();
  } catch (e) {
    console.log("SKIPPED  Chromium present but not launchable: " + (e.message || e).split("\n")[0]);
    process.exit(3);
  }

  // Canonical document URL (handles spaces/accents in the path; do not concatenate
  // "file://" + abs by hand).
  const docUrl = require("url").pathToFileURL(abs).href;

  const jsErrors = [];
  const requests = [];      // every request of the session, whatever its fate
  let wsUnwatched = false;  // Playwright < 1.48: no routeWebSocket

  // All the network instrumentation is attached to the CONTEXT, BEFORE the page is
  // created: no request can slip in before the net is up.
  const context = await browser.newContext();
  await context.setOffline(true); // emulated "kill the Wi-Fi" (does not affect file://)

  if (typeof context.routeWebSocket === "function") {
    // A WebSocket handshake does NOT show up in route()/on('request'): routeWebSocket
    // is the only reliable sensor, and as long as connectToServer() is never called,
    // the connection never actually leaves.
    await context.routeWebSocket("**", (ws) => {
      requests.push({ type: "websocket", url: ws.url() });
    });
  } else {
    wsUnwatched = true;
  }

  await context.route("**", (route) => {
    const req = route.request();
    requests.push({ type: req.resourceType(), url: req.url() });
    if (req.url().startsWith("file://")) {
      return route.continue(); // the document itself; any OTHER file:// is judged at the verdict
    }
    return route.abort("blockedbyclient"); // nothing really leaves, even during the test
  });

  const page = await context.newPage();
  page.on("pageerror", (e) => jsErrors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") jsErrors.push("console.error: " + m.text()); });

  let loadOk = true;
  try {
    await page.goto(docUrl, { waitUntil: "load", timeout: 15000 });
    // Let deferred scripts (DOMContentLoaded, microtasks) run their course.
    await page.waitForTimeout(1200);
    // A leak may wait for an interaction: click every tab of the template.
    // (short timeout: a hidden tab must not stall for 30 s, and a failed click
    // is not a test failure: the network is what we watch here.)
    for (const tab of await page.$$(".tab")) {
      await tab.click({ timeout: 2000 }).catch(() => {});
      await page.waitForTimeout(300);
    }
    await page.waitForTimeout(1000); // late beacons
  } catch (e) {
    loadOk = false;
    jsErrors.push("Navigation failure: " + (e.message || e).split("\n")[0]);
  }

  // Interface invariants: title, header, and, for a file tool, a file input.
  const info = await page.evaluate(() => ({
    title: document.title,
    hasHeader: !!document.querySelector("header, h1"),
    fileInputs: document.querySelectorAll('input[type="file"]').length,
    hasDownloadHook: /download/i.test(document.body ? document.body.innerHTML : ""),
    bodyLen: document.body ? document.body.innerText.trim().length : 0,
    // preconnect/dns-prefetch emit NO interceptable request (a connection opened
    // ahead of time, not a load): only inspecting the live DOM sees them. We read
    // l.href (resolved): a relative target becomes file:// and is ignored;
    // preload/prefetch emit real requests, already intercepted.
    preconnects: Array.from(document.querySelectorAll("link[rel]"))
      .filter((l) => /\b(preconnect|dns-prefetch)\b/i.test(l.rel) && /^https?:\/\//i.test(l.href))
      .map((l) => "<" + l.rel + "> " + l.href),
  })).catch(() => null);

  await browser.close();

  // Network verdict: the ONLY legitimate request of the whole session is the document.
  // (data:/blob: never generate an event: no allowlist to maintain.)
  const violations = [];
  for (const r of requests) {
    if (r.url === docUrl) continue;
    if (r.url.startsWith("file://")) {
      violations.push("<" + r.type + "> " + r.url + " (separate file:// resource: the tool is not a single file)");
    } else {
      violations.push("<" + r.type + "> " + r.url);
    }
  }
  const uniqueViolations = [...new Set(violations)];

  const preconnects = info ? info.preconnects : [];

  const problems = [];
  if (!loadOk) problems.push("the page could not load");
  if (jsErrors.length) problems.push(jsErrors.length + " JS error(s) on load");
  if (info && !info.hasHeader) problems.push("no visible <header>/<h1> (empty interface?)");
  if (info && info.bodyLen === 0) problems.push("the <body> is empty on screen");
  if (uniqueViolations.length) problems.push(uniqueViolations.length + " outgoing request(s) detected");
  if (preconnects.length) problems.push(preconnects.length + " external preconnection(s) declared");

  console.log("\n=== Smoke test: " + path.basename(abs) + " ===\n");
  if (info) {
    console.log("  title        : " + JSON.stringify(info.title));
    console.log("  header       : " + (info.hasHeader ? "present" : "MISSING"));
    console.log("  file input   : " + info.fileInputs + (info.fileInputs ? " found" : " (none, normal if the tool reads no file)"));
    console.log("  dl button    : " + (info.hasDownloadHook ? "'download' mention present" : "none (check if the tool produces a file)"));
  }
  if (uniqueViolations.length) {
    console.log("  network      : " + uniqueViolations.length + " outgoing request(s). PROMISE BROKEN:");
    uniqueViolations.slice(0, 10).forEach((v) => console.log("    - " + v));
  } else {
    console.log("  network      : 0 outgoing requests" +
      (preconnects.length ? "" : ", the “kill the Wi-Fi” promise kept") +
      (wsUnwatched ? " (WebSocket unwatched: Playwright < 1.48)" : ""));
  }
  if (preconnects.length) {
    console.log("  preconnect   : " + preconnects.length + " declared to the outside. PROMISE BROKEN:");
    preconnects.slice(0, 10).forEach((p) => console.log("    - " + p));
    console.log("    (a preconnect/dns-prefetch opens a connection without a request: remove the <link> tag)");
  }
  if (jsErrors.length) {
    console.log("\n  Errors detected:");
    jsErrors.slice(0, 10).forEach((e) => console.log("    - " + e));
  }

  if (problems.length) {
    console.log("\nFAILED: " + problems.join("; ") + ".");
    console.log("Fix, then run again. (Reminder: this test does not check the business calculations.)");
    process.exit(1);
  }
  console.log("\nOK: the page loads without JS errors, the interface renders, no request goes out.");
  console.log("The BUSINESS LOGIC still needs validating on real/representative data (see Step 6).");
  process.exit(0);
}

main().catch((e) => {
  console.log("Unexpected smoke test error: " + (e && e.message ? e.message : e));
  process.exit(1);
});
