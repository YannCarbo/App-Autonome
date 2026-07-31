---
name: app-autonome
description: "Turns an idea, a need, or a prototype into a self-contained web tool."
---

# Self-contained HTML tool

This skill produces a **single `.html` file**: the recipient double-clicks it, their browser opens it, and the tool works offline, with no installation, no server and no admin rights. Target: recent Edge, Chrome and Firefox, non-technical users. The file is designed to be maintained by AI: the user re-uploads it, asks for an evolution, gets a new version back (see "Maintenance mode").

## The promise

**AI is for building the tool, not for running it.** The deliverable is self-contained:

- **No AI dependency**: no credits, no subscription, no model to call in order to use it.
- **Explicit rules**: repeatable behavior, described in plain language inside the tool itself.
- **Built for teams**: a single file shared by email or team space.
- **100% local**: data never leaves the computer. No network request, no exception, never a "try the network then fall back to local" middle ground. One leaking tool destroys trust in all the others; the validator and the smoke test block it.

## Posture

The requester and the recipients are business people, not developers:

- **A minimum of questions, in business language.** Only ask what a wrong assumption would make the tool unusable or dangerous, and never a technical choice: that is your job, not theirs. A sample file beats ten questions; offer it, without making it a prerequisite. **The only always-mandatory question is the tool's name, chosen by the user**: it shows at the top of the page and names the `.html` file.
- **Deliver first.** Fill the gaps with plausible assumptions, deliver a testable v1, list the assumptions in the reply and in the "Tool rules" tab. Business users correct more easily by testing than by answering an interrogation.
- **Never a silent correction.** That is what makes "deliver first" sustainable: any undecided ambiguous case is reported as an anomaly, never guessed. A tool that misses a case but shows it is acceptable; a tool that corrects silently is not.
- **Zero jargon.** No "UMD", "CORS", "parser" in replies: say "double-click it", "works without an internet connection".

## Step 1: Understand the need

Identify: **inputs** (files, columns with their exact names, real formats), **business rules** (prefer a numbered example over an abstract description), **outputs** (format, naming), **edge cases** (mandatory data missing: block, warn, default value?), **volume** (beyond ~50,000 rows: batch processing + progress bar).

**If a sample file is provided, actually inspect it before writing a single line of code**: real columns hold surprises compared to the verbal description.

## Step 2: Data guardrails (mandatory for any transformation)

The worst-case scenario is not a crash, it is silent corruption. Ready-to-adapt patterns in `references/business-patterns.md`.

1. **Before/after preview**: a sample of the transformed data (10–20 rows) before download.
2. **Numbered report**: "212 rows read, 208 transformed, 4 anomalies", with a list and row numbers.
3. **Zero silent correction**: ambiguous case = reported anomaly; row excluded with a mention or kept with a warning.
4. **Never overwrite**: the produced file bears a name distinct from the original (`supplier_formatted_2026-07-16.xlsx`).
5. **Explicit errors**: "This file has no \"Reference\" column. Columns found: …", not a technical error.

## Step 3: Golden rules of `file://` (non-negotiable)

Opened by double-click = `file://` protocol, opaque `null` origin. An app that works on a dev server can be completely dead on double-click:

- **Classic scripts only.** Never `<script type="module">`, never `import`/`export`: blocked by CORS.
- **No external resource.** No `http(s)` URL in a `src`, `href`, `action` or CSS `url()`: everything is inlined. (Exception: SVG `xmlns`, identifiers rather than downloads.)
- **Never `fetch()` nor `XMLHttpRequest`.** User files: `<input type="file">` + `FileReader`. Embedded data: `<script type="application/json" id="data-inline">` read with `JSON.parse(...)`.
- **No Web Workers nor Service Workers**: `new Worker("file.js")` fails from a `null` origin. Long runs split into batches via `setTimeout`/`requestAnimationFrame`. Narrow exception: a worker inlined as a Blob when a lib truly requires it (typically pdf.js), to be confirmed at the smoke test on Chrome, Edge and Firefox.
- **No File System Access API** (not supported by Firefox). Output = `Blob` + programmatically clicked `<a download>` link.
- **`localStorage` = a bonus, never critical** (variable behavior under `file://`): the tool works fully without it.
- **`<meta charset="utf-8">`** at the top of `<head>`; images as inline SVG or data URI; system fonts only.

## What if the need requires the internet?

Reframe it in business language, never oppose a flat refusal; most "internet needs" have an acceptable offline answer:

- **"The reference data changes"** → embed it (`<script type="application/json">`); the maintenance cycle produces a new version when it really changes.
- **"We need to query our system"** (ERP, CRM) → the user exports it themselves (Excel, CSV) and loads the export into the tool.
- **"The result must be sent"** → the tool produces a file, the user sends it through their usual channel. Tolerated because nothing loads on open: a prepared `mailto:`, a navigation `<a href>` link followed on click.
- **True real time** (shared stock, direct writes into a system) → say it honestly: that is a hosted web application, a different deliverable out of scope, never a "degraded" variant of a self-contained tool.

## Step 4: Libraries

Read `references/libraries.md` (verified libraries with browser builds, URLs, procedure). Three tiers: **vanilla JS** (simple tool) → **Alpine.js** (a few UI states) → **Vue 3 global build** (real stateful application). Never React ≥ 19 nor Tailwind for a new tool. Embed only what is needed: every lib adds hundreds of KB.

Inlining traps:

- **Escape `</script`** in any lib before insertion: replace with `<\/script`, otherwise the tag closes prematurely.
- **`defer`/`async` are lost** when inlined: an auto-starting lib (Alpine…) runs before the APP CODE that follows it. Wrap the lib in `window.addEventListener("DOMContentLoaded", () => { … })` to restore the original order.
- **Minified builds are untouchable**: no modification beyond the escaping above. A validator warning about LIBRARIES content is justified in the reply, never patched.
- **Fresh then frozen versions**: download the latest stable, record it in the block's comment (name@version); the deliverable will never fetch anything online again.

## Step 5: File structure

Start from `assets/template.html`. Sections delimited by sentinel markers, which is what makes AI maintenance possible without re-reading the minified libs:

```
<!-- ===== SECTION: STYLES ===== -->
<!-- ===== SECTION: MARKUP ===== -->
<!-- ===== SECTION: LIBRARIES (do not edit) ===== -->
<!-- ===== SECTION: APP CODE ===== -->
```

Three mandatory elements in the interface:

- **Header**: `Tool name · VX.X · date`, hard-coded in the HTML.
- **Two tabs**: "Processing" (active by default) and "Tool rules" (transformations and assumptions, in plain language: the documentation lives in the tool, not in the conversation). The template provides the tab mechanism: reuse it.
- **Footer**: `This tool runs entirely in your browser: no data is sent over the internet.`

The rest is free: sober design with an identity (accent color tied to the domain), buttons named after their effect ("Download the corrected file", not "Submit"). **The interface is written in the requester's language, non-negotiable**: a French team gets a fully French tool (tab labels, buttons, messages, date formats, and the footer, e.g. « Cet outil fonctionne entièrement dans votre navigateur : aucune donnée n'est envoyée sur internet. »). This skill being written in English must never make a delivered tool default to English. The validator recognizes the privacy footer in English and French; for any other language, justify its warning in one sentence.

## Step 6: Validation

```bash
python3 scripts/validate_package.py path/to/tool.html
```

Fix and rerun until **zero errors**. An **error** is fixed in STYLES/MARKUP/APP CODE or in the assembly, never by editing a minified lib. A **warning** is handled with judgment and justified in one sentence.

The validator's zero errors (static) does not prove the page runs. Three complementary layers, from cheapest to most conclusive:

1. **Pure functions under node**: isolate the business logic (see `references/business-patterns.md`) and test it with numbered cases before inlining it.
2. **Browser smoke test**, when a browser is available:
   ```bash
   node scripts/smoke_test.cjs path/to/tool.html
   ```
   Actually opens the file under `file://` offline, clicks every tab, fails on any JS error and any outgoing request: the deterministic test of "100% local". "SKIPPED" is not a green light: verification falls back to the first open at the user's (Step 7).
3. **Business validation on real data** (or a representative anonymized sample): have the business check a few expected results and the main edge cases. For a critical transformation (accounting, ERP, customs), this prerequisite is non-negotiable.

Self-check of the guardrails themselves, when in doubt about the environment or after modifying the skill's scripts: `python3 tests/run_tests.py` (exit 1 = a guardrail regressed, do not validate any tool).

## Step 7: Delivery

- File name: `tool-name-v1.0.html` (kebab-case, version included: the name survives transfers, metadata does not).
- Deliver through the file-presentation tool, **with a sample file** when the tool transforms files: the business tests immediately, without risking real data.
- Mandatory numbered how-to, in plain language, covering four moments: **1. Get it** (download, save) · **2. Open it** (double-click, opens in the browser, everything happens on the computer) · **3. Test it** (concrete scenario with the sample file, say what to check) · **4. Share it** (like a plain file, from the team space; by email, zip the `.html` if it is blocked as an attachment).
- Add the two sentences that prevent 90% of the tickets: "If the file opens in Notepad: right-click > Open with > Edge." and "For any evolution: send this file back to me in a new conversation describing the wanted change."

## Conversion mode (multi-file → single file)

Mechanical inlining is not enough: first inventory what the original structure guaranteed implicitly.

1. **`defer`/`async`/`type` and the real execution order** they imply: reproduce that order (positioning + `DOMContentLoaded` wrapper), not the order of appearance.
2. **Libs that scan the DOM when they run** (Alpine via `x-data`, Tailwind Play…) must run after that DOM exists.
3. **Network resources to cut**: fonts → system stack, remote images → data URI, data `fetch` → `<script type="application/json">`.

Then run Steps 5 to 7. Libs inherited from the existing artifact (Tailwind Play, React 18 UMD…) can stay as they are: "never for a new tool" does not apply to a conversion.

## Maintenance mode (existing tool uploaded)

1. **Never read the whole file** (LIBRARIES weighs MBs of minified code): `grep -n "===== SECTION" tool.html`, then read only STYLES, MARKUP and APP CODE by line ranges.
2. Modify **without touching LIBRARIES**, except for an explicitly requested lib update: re-download, re-escape, replace the whole block, update the name@version comment.
3. Bump version and date (header + file name); update the "Tool rules" tab if the rules changed.
4. Revalidate (`scripts/validate_package.py`), deliver under the new versioned name.

If the file lacks the sentinel markers (created outside the skill), offer to restructure it to the skill's format on the occasion of the change.
