# Reusable business patterns

These patterns come back tool after tool, whatever the domain. They live in the
**APP CODE** section (readable, commented, never minified). They fit the
**single-file `file://`** model: no `fetch`, no reference to a `libs/` folder, everything is
inline. Copy and adapt, do not reinvent.

## 1. Drag-and-drop + file picker

The `<input type="file">` remains the source of truth; drag-and-drop is only a convenience.

```html
<div id="drop-zone" class="drop-zone">
  Drag your file here, or <label for="file-input" class="link">choose it</label>
  <input type="file" id="file-input" accept=".xlsx,.csv" hidden />
</div>
```

```js
const zone = document.getElementById("drop-zone");
const input = document.getElementById("file-input");
["dragenter", "dragover"].forEach(evt =>
  zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.add("dragover"); }));
["dragleave", "drop"].forEach(evt =>
  zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.remove("dragover"); }));
zone.addEventListener("drop", e => processFile(e.dataTransfer.files[0]));
input.addEventListener("change", e => processFile(e.target.files[0]));
```

## 2. Alert panel by severity (the Step 2 guardrail)

Never fail silently, never drown a critical alert in 50 lines of info.
Split by severity, show errors first, with the row number.

```js
function validateRow(row, index) {
  const alerts = [];
  const rowNumber = index + 2; // +2: header + 0-based index
  if (!row.address) alerts.push({ severity: "error", message: `Row ${rowNumber} (${row.client ?? "unknown client"}): missing address` });
  if (row.weight != null && row.weight <= 0) alerts.push({ severity: "warning", message: `Row ${rowNumber}: zero or negative weight, check it` });
  return alerts;
}

function renderSummary(rowCount, transformedCount, allAlerts) {
  const errors = allAlerts.filter(a => a.severity === "error");
  const warnings = allAlerts.filter(a => a.severity === "warning");
  document.getElementById("summary").innerHTML = `
    <p>${rowCount} rows read, ${transformedCount} transformed, ${errors.length + warnings.length} anomaly(ies).</p>
    ${errors.length ? `<div class="alert error"><strong>${errors.length} error(s) to fix</strong><ul>${errors.map(a => `<li>${a.message}</li>`).join("")}</ul></div>` : ""}
    ${warnings.length ? `<div class="alert warning"><strong>${warnings.length} warning(s)</strong><ul>${warnings.map(a => `<li>${a.message}</li>`).join("")}</ul></div>` : ""}
    ${!allAlerts.length ? `<div class="alert ok">No anomaly detected.</div>` : ""}`;
}
```

Decide with the user, at Step 1, whether an error blocks **the row** (the others go through) or
**the whole run**. Blocking row by row and carrying on is usually more useful, but confirm it,
and always **report**, never guess (the "zero silent correction" rule).

## 3. Business rules: pure, testable functions

Separate "read", "apply the rules" and "generate the output". It lets you test the logic in
isolation (with `node`, before inlining, see Step 6) and prevents a generation bug from
masking a calculation bug.

```js
// Pure function: checkable against the numbered examples given at Step 1.
function computePallets(parcels, { maxVolume = 1.44, maxWeight = 800 } = {}) {
  const volume = parcels.reduce((s, p) => s + p.length * p.width * p.height, 0);
  const weight = parcels.reduce((s, p) => s + p.weight, 0);
  return Math.max(Math.ceil(volume / maxVolume), Math.ceil(weight / maxWeight));
}
// Before wiring to the UI:
console.assert(computePallets([{ length: 1, width: 1, height: 1, weight: 500 }]) === 1, "simple case");
```

Document the business constants (thresholds, rounding) in comments: they are the values most
likely to change, and the interface's "Tool rules" tab must reflect them.

## 4. Group by key before generating

```js
function groupBy(rows, key) {
  return rows.reduce((g, row) => {
    (g[row[key] ?? "Not specified"] ??= []).push(row);
    return g;
  }, {});
}
```

## 5. Full pipeline: export file → multi-file generation → ZIP

```js
async function processExport(file) {
  const rows = await readExcel(file);                // see references/libraries.md (SheetJS)
  const alerts = rows.flatMap(validateRow);
  // Coupled to validateRow's messages: the filter matches the literal `Row N ` prefix.
  const validRows = rows.filter((_, i) => !alerts.some(a => a.severity === "error" && a.message.includes(`Row ${i + 2} `)));
  renderSummary(rows.length, validRows.length, alerts);

  const byClient = groupBy(validRows, "client");
  const zip = new JSZip();                           // see references/libraries.md (JSZip)
  for (const [client, clientRows] of Object.entries(byClient)) {
    const folder = zip.folder(client);
    folder.file("packing-list.xlsx", buildPackingList(clientRows)); // -> Blob
    folder.file("delivery-note.pdf", await buildPdf(clientRows));    // -> Blob/Uint8Array
  }
  const content = await zip.generateAsync({ type: "blob" });
  downloadFile(content, `export_${new Date().toISOString().slice(0, 10)}.zip`, "application/zip");
}
```

`downloadFile` is provided in the template (`assets/template.html`). The download is triggered
by an **explicit click**, never automatically, and **after** the user has seen the preview and
the summary.

## 6. Never freeze the UI on a heavy run (without a Web Worker)

No worker under `file://` (see Step 3). One `await` per step with a counter covers nearly
every business volume; beyond that, split into batches with `processInBatches` (template).

```js
const bar = document.getElementById("progress");
for (let i = 0; i < clients.length; i++) {
  await processOneClient(clients[i]);
  bar.textContent = `${i + 1} / ${clients.length} clients processed`;
}
```
