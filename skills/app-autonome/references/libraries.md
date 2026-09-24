# Verified libraries for self-contained HTML tools

Every library below ships a **browser build** (global/UMD/IIFE): a single `.js` file that runs in a classic `<script>` tag and exposes a global variable. It is the only form compatible with the `file://` protocol.

## Finding the latest stable version

Never code a version from memory. At generation time:

```bash
# Latest stable version on npm
curl -s https://registry.npmjs.org/vue/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])"
```

Then download the build by replacing `VERSION` in the URL from the table below.

## Library table

| Need | Library | Global variable | Browser build URL |
|---|---|---|---|
| Reactive UI | Vue 3 | `Vue` | `https://unpkg.com/vue@VERSION/dist/vue.global.prod.js` |
| Lightweight reactivity in HTML | Alpine.js | `Alpine` | `https://unpkg.com/alpinejs@VERSION/dist/cdn.min.js` (load with `defer`) |
| Read/write Excel (.xlsx, .xls) | SheetJS | `XLSX` | `https://cdn.sheetjs.com/xlsx-latest/package/dist/xlsx.full.min.js` |
| Parse/generate CSV | PapaParse | `Papa` | `https://unpkg.com/papaparse@VERSION/papaparse.min.js` |
| Charts | Chart.js | `Chart` | `https://unpkg.com/chart.js@VERSION/dist/chart.umd.js` |
| Advanced/scientific charts | Plotly | `Plotly` | `https://unpkg.com/plotly.js-dist-min@VERSION/plotly.min.js` (~4.5 MB: only if Chart.js is not enough) |
| Dates (parsing, formatting) | Day.js | `dayjs` | `https://unpkg.com/dayjs@VERSION/dayjs.min.js` |
| Create/read ZIP files | JSZip | `JSZip` | `https://unpkg.com/jszip@VERSION/dist/jszip.min.js` |
| Generate PDFs (drawing) | jsPDF | `jspdf` (then `jspdf.jsPDF`) | `https://unpkg.com/jspdf@VERSION/dist/jspdf.umd.min.js` |
| Fill a PDF form (AcroForm) | pdf-lib | `PDFLib` | `https://unpkg.com/pdf-lib@VERSION/dist/pdf-lib.min.js` |
| Excel with rich styling / logo | ExcelJS | `ExcelJS` | `https://unpkg.com/exceljs@VERSION/dist/exceljs.min.js` |
| Compress an image-heavy PDF | pdf.js (+ pdf-lib) | `pdfjsLib` | `https://unpkg.com/pdfjs-dist@VERSION/build/pdf.min.js` (see worker note) |
| Manipulate .docx files | docx | `docx` | `https://unpkg.com/docx@VERSION/build/index.umd.js` |
| Text diffing | jsdiff | `Diff` | `https://unpkg.com/diff@VERSION/dist/diff.min.js` |

Notes:
- **jsPDF vs pdf-lib**: jsPDF *draws* a PDF from scratch (text, shapes); **pdf-lib** *loads an existing PDF* and fills its form fields (AcroForm): the right choice to reproduce a regulatory form from a provided template. `form.getFields()` lists the field names; a missing field must be **reported as an anomaly**, not ignored.
- **ExcelJS vs SheetJS**: SheetJS is enough to read/write data; switch to **ExcelJS** only when the output demands rich styling (conditional colors, borders, image logo). An often more reliable alternative: start from a template workbook styled by the user and only write the data cells into it.
- **pdf.js and the Web Worker (important under `file://`)**: pdf.js wants a worker. Under `file://`, a `workerSrc` pointing at a `.js` file **does not load** (`null` origin, see Step 3 of the SKILL). Two options: (a) inline the content of `pdf.worker.min.js` into a Blob and point `workerSrc` at the Blob URL: it works, but **must be confirmed at the smoke test** (Chrome/Edge/Firefox); (b) disable the worker and work on the main thread, slower, split into batches so the UI never freezes. Rasterization-based compression remains **lossy** compression that turns text into images (no more selectable text): announce it clearly to the user.
- **SheetJS**: recent versions are no longer published on npm (stuck at 0.18.5). Use `cdn.sheetjs.com` exclusively; `xlsx-latest` always points at the latest version. Record the actual version found in the downloaded file's header in the `name@version` comment of the inlined block (LIBRARIES section).
- **Vue**: strictly `vue.global.prod.js`. Neither `vue.esm-browser.js` (ES module, dead under `file://`), nor `vue.global.js` (dev build, heavy and verbose in the console).
- A library outside this table is usable **if and only if** it passes the verification procedure below.

## Off-limits

- **React ≥ 19**: no UMD build published anymore, and JSX requires compilation anyway. (React 18 as UMD remains technically possible, but Vue 3 global or Alpine.js are the default choices here.)
- **Tailwind CSS in production requires a build step.** Honest nuance: Tailwind's self-hosted "browser" script works under `file://`: it compiles the classes on the fly in the browser. But that is ~400 KB of compiler reloaded and re-run on every open, discouraged by Tailwind itself, and hand-written CSS is lighter and more readable in maintenance. Accept it only to reuse an existing artifact already written with Tailwind classes; never for a new tool.
- **Alpine.js** must be loaded with the `defer` attribute (it scans the DOM on load).
- **Any "ESM only" package** (e.g. `lodash-es`, many recent libraries): being on npm guarantees nothing, check the contents of `dist/`.
- **External web fonts** (Google Fonts...): system font stacks only.

## Verifying that a build is really `file://` compatible

After download, before inlining:

```bash
# 1. The start of the file: we must see a UMD/IIFE wrapper, no module keywords
head -c 600 lib.js
# Bad signs: "import ", "export " at the start of a line
grep -nE '^\s*(import|export)\s' lib.js | head -5   # must be empty

# 2. The fatal sequence for inlining (would close the <script> tag prematurely)
grep -c '</script' lib.js    # if > 0, replace '</script' with '<\/script'
python3 - <<'EOF'
data = open('lib.js', encoding='utf-8').read()
open('lib.js', 'w', encoding='utf-8').write(data.replace('</script', '<\\/script'))
EOF

# 3. Execution test: the global must exist after loading in a non-module context
node -e "global.window=global; global.self=global; global.document={createElement:()=>({}),}; require('./lib.js'); console.log(typeof window.GlobalName)" 2>/dev/null || echo "Node test inconclusive, inspect the UMD wrapper manually"
```

The node test is indicative (some legitimate browser builds touch the DOM on load): on failure, eyeball the wrapper. The decisive criterion remains the absence of top-level `import`/`export` and the presence of an assignment to `window`/`this`/`self`.

## Loading libraries in the right order

In the LIBRARIES section, each library occupies its own `<script>` tag, preceded by a name + version + origin URL comment:

```html
<!-- vue@3.5.17 - https://unpkg.com/vue@3.5.17/dist/vue.global.prod.js -->
<script>/* ...minified content... */</script>
```

Order: dependencies before dependents (e.g. Day.js before a Day.js plugin). The APP CODE section always comes after LIBRARIES.
