#!/usr/bin/env python3
"""
Validates that a self-contained HTML tool honors the constraints of the file://
protocol and the structure required by the app-autonome skill.

Usage: python3 validate_package.py path/to/tool.html
Output: ERROR / WARNING / OK report; exit code 0 if zero errors, 1 otherwise.

ERROR / WARNING separation principle:
- A resource ACTUALLY loaded by the browser at runtime (<script src> tag,
  <link rel=stylesheet>, remote <img src>, <iframe>/<video>/<source> src, external
  CSS url()/@import) is an ERROR, wherever it lives, including in LIBRARIES: it is
  what breaks the "100% offline" promise.
- An http(s) URL present only as an INERT STRING inside minified code (license
  attribution, feature detection...) stays a WARNING: patching it would be more
  dangerous than leaving it alone.
The scanner below makes that distinction by honoring HTML semantics: the content
of a <script>...</script> block is plain text, so a "<script src=..." appearing
inside it is a string, not a tag: it is never loaded.
"""

import re
import sys
import os

SENTINELS = {
    "STYLES": r"=====\s*SECTION:\s*STYLES",
    "MARKUP": r"=====\s*SECTION:\s*MARKUP",
    "LIBRARIES": r"=====\s*SECTION:\s*LIBRARIES",
    "APP CODE": r"=====\s*SECTION:\s*APP CODE",
}

# APIs forbidden under file://: error in APP CODE, warning in LIBRARIES
# (libraries often contain inert feature-detection code)
FORBIDDEN_APIS = [
    (r"\bfetch\s*\(", "fetch()"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"navigator\.serviceWorker", "Service Worker"),
    (r"\bimportScripts\s*\(", "importScripts()"),
    (r"\bimport\s*\(", "dynamic import()"),
    (r"\bshowOpenFilePicker\b|\bshowSaveFilePicker\b", "File System Access API (not supported by Firefox)"),
    # Data EGRESS channels: nothing must leave, not just nothing come in.
    # sendBeacon( without the navigator. prefix: minified code often aliases the object.
    (r"\bsendBeacon\s*\(", "navigator.sendBeacon()"),
    # new required for WebSocket/EventSource/RTCPeerConnection: the bare word shows up
    # in prose or feature tests ("WebSocket" in window).
    (r"\bnew\s+WebSocket\s*\(", "WebSocket"),
    (r"\bnew\s+EventSource\s*\(", "EventSource (Server-Sent Events)"),
    (r"\bnew\s+(?:webkit)?RTCPeerConnection\s*\(", "RTCPeerConnection (WebRTC)"),
]

# <link> rel values that trigger a load: for those, even a RELATIVE href is a real
# resource (a stylesheet sitting next to the file breaks the single-file promise).
LOADING_LINK_RELS = {
    "stylesheet", "icon", "shortcut", "apple-touch-icon",
    "preload", "prefetch", "modulepreload", "manifest",
}


def find_section_spans(html):
    """Returns {section_name: (start, end)} based on the sentinel markers."""
    positions = []
    for name, pattern in SENTINELS.items():
        m = re.search(pattern, html)
        if m:
            positions.append((m.start(), name))
    positions.sort()
    spans = {}
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(html)
        spans[name] = (start, end)
    return spans


def _attr(tag, name):
    """Value of an attribute inside a tag, quoted or not, any order. '' if absent."""
    m = re.search(r"\b" + name + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))", tag, re.I)
    if not m:
        return ""
    return next((g for g in m.groups() if g is not None), "").strip()


def strip_script_bodies(html):
    """
    Returns the HTML without the bodies of <script>...</script> (tags kept).
    The text of a script block is never parsed as CSS/HTML: removing it lets us
    look for real CSS url()/@import without false positives from JS strings.
    """
    out = []
    n = len(html)
    low = html.lower()
    i = 0
    while i < n:
        lt = html.find("<", i)
        if lt == -1:
            out.append(html[i:])
            break
        gt = html.find(">", lt)
        if gt == -1:
            out.append(html[i:])
            break
        tag = html[lt:gt + 1]
        out.append(html[i:gt + 1])
        if re.match(r"<script\b", tag, re.I):
            close = low.find("</script", gt)
            i = close if close != -1 else n
        else:
            i = gt + 1
    return "".join(out)


def scan_real_loads(html):
    """
    Walks the HTML while honoring the plain-text rule of <script> blocks:
    everything between a <script ...> and the next </script is skipped
    (it is library content, never a tag to load).
    Returns a list of (type, excerpt) tuples for every resource ACTUALLY loaded.
    """
    loads = []
    n = len(html)
    low = html.lower()
    i = 0
    while i < n:
        lt = html.find("<", i)
        if lt == -1:
            break
        gt = html.find(">", lt)
        if gt == -1:
            break
        tag = html[lt:gt + 1]

        m_script = re.match(r"<script\b([^>]*)>", tag, re.I)
        if m_script:
            attrs = m_script.group(1)
            m_src = re.search(r"\bsrc\s*=\s*[\"']([^\"']*)[\"']", attrs, re.I)
            if m_src:
                loads.append(("script-src", m_src.group(1)))
            close = low.find("</script", gt)
            i = (close + 1) if close != -1 else (gt + 1)
            continue

        if re.match(r"<link\b", tag, re.I):
            rel = _attr(tag, "rel").lower()
            href = _attr(tag, "href")
            if href:
                hl = href.lower()
                loading_rels = set(rel.split()) & LOADING_LINK_RELS
                if loading_rels and not hl.startswith(("data:", "#")):
                    # stylesheet/icon/preload...: relative or absolute, it loads.
                    loads.append(("link-" + sorted(loading_rels)[0], href))
                elif hl.startswith(("http://", "https://", "//")):
                    loads.append(("link", href))

        m_media = re.match(r"<(img|iframe|video|audio|source|track|embed)\b", tag, re.I)
        if m_media:
            m = re.search(r"\bsrc\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
            if m and not m.group(1).strip().lower().startswith(("data:", "#", "javascript:")):
                loads.append((m_media.group(1).lower() + "-src", m.group(1)))
            # srcset: candidates separated by ", " (a data URI contains a comma
            # with NO space after it, so this split preserves it), URL = candidate's 1st token.
            srcset = _attr(tag, "srcset")
            if srcset:
                candidates = [c.strip().split()[0] for c in re.split(r",\s+", srcset) if c.strip()]
                if any(not c.lower().startswith(("data:", "#")) for c in candidates):
                    loads.append(("srcset", srcset))
            poster = _attr(tag, "poster")
            if poster and not poster.lower().startswith("data:"):
                loads.append(("poster", poster))

        if re.match(r"<(a|area)\b", tag, re.I):
            # ping= sends a background POST on click: a transmission, unlike the
            # navigation href (tolerated, see count_external_anchors).
            ping = _attr(tag, "ping")
            if ping:
                loads.append(("ping", ping))

        if re.match(r"<meta\b", tag, re.I) and re.search(r"http-equiv\s*=\s*[\"']?refresh", tag, re.I):
            content = _attr(tag, "content")
            if re.search(r"url\s*=", content, re.I):
                # a refresh WITHOUT url= reloads the same file: harmless.
                loads.append(("meta-refresh", content))

        if re.match(r"<html\b", tag, re.I):
            manifest = _attr(tag, "manifest")
            if manifest:
                loads.append(("manifest", manifest))

        if re.match(r"<input\b", tag, re.I) and re.search(r"\btype\s*=\s*[\"']?image\b", tag, re.I):
            src = _attr(tag, "src")
            if src and not src.lower().startswith("data:"):
                loads.append(("input-image-src", src))

        if re.match(r"<use\b", tag, re.I):
            # <use href="#icon"> (internal sprite) is the legitimate case; an
            # external target is a load.
            m = re.search(r"\b(?:xlink:)?href\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
            if m and not m.group(1).strip().lower().startswith(("#", "data:")):
                loads.append(("use-href", m.group(1)))

        if re.match(r"<object\b", tag, re.I):
            m = re.search(r"\bdata\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
            if m and not m.group(1).strip().lower().startswith("data:"):
                loads.append(("object-data", m.group(1)))

        if re.match(r"<form\b", tag, re.I):
            m = re.search(r"\baction\s*=\s*[\"']?(https?://[^\"'\s>]+)", tag, re.I)
            if m:
                loads.append(("form-action", m.group(1)))

        i = gt + 1
    return loads


def count_external_anchors(html):
    """Counts <a href="http(s)://..."> links: navigation on click, not a load."""
    return len(re.findall(r"<a\b[^>]*\bhref\s*=\s*[\"']?https?://", html, re.I))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"ERROR  File not found: {path}")
        return 1

    errors, warnings, oks = [], [], []

    size = os.path.getsize(path)
    size_mb = size / (1024 * 1024)
    if size_mb > 15:
        errors.append(f"Size {size_mb:.1f} MB: far too heavy, trim the embedded libraries")
    elif size_mb > 6:
        warnings.append(f"Size {size_mb:.1f} MB: heavy for email sharing, check that every library is needed")
    else:
        oks.append(f"Size: {size_mb:.2f} MB")

    if not path.lower().endswith(".html"):
        errors.append("The extension must be .html")

    raw = open(path, "rb").read()
    try:
        html = raw.decode("utf-8")
        oks.append("Valid UTF-8 encoding")
    except UnicodeDecodeError:
        errors.append("The file is not valid UTF-8")
        html = raw.decode("utf-8", errors="replace")

    if re.search(r"<meta[^>]+charset\s*=\s*[\"']?utf-8", html, re.I):
        oks.append('<meta charset="utf-8"> present')
    else:
        errors.append('<meta charset="utf-8"> missing (mandatory under file://)')

    if re.search(r"type\s*=\s*[\"']module[\"']", html, re.I):
        errors.append('<script type="module"> detected: blocked by CORS under file://')
    else:
        oks.append("No ES modules")

    spans = find_section_spans(html)
    if "LIBRARIES" in spans:
        lib_start, lib_end = spans["LIBRARIES"]
        libs_txt = html[lib_start:lib_end]
    else:
        lib_start = lib_end = None
        libs_txt = ""

    loads = scan_real_loads(html)
    if loads:
        preview = "; ".join(f"<{k}> {v[:60]}" for k, v in loads[:4])
        if len(loads) > 4:
            preview += f" ... (+{len(loads) - 4})"
        errors.append(
            f"{len(loads)} resource(s) loaded at runtime: the tool must be 100% inline/offline. "
            f"Inline (script/CSS) or convert to a data URI (images): {preview}"
        )
    else:
        oks.append("No resource loaded at runtime (everything is inline)")

    outside_libs = (html[:lib_start] + html[lib_end:]) if libs_txt else html

    def count_css_ext(txt):
        n = len(re.findall(r"url\(\s*[\"']?https?://", txt, re.I))
        n += len(re.findall(r"@import\s+[\"']?https?://", txt, re.I))
        return n

    # Real CSS (<style> tags, style= attributes) lives outside <script> bodies:
    # we scan the HTML stripped of those bodies to avoid false positives from JS
    # strings, and hunt both external (http) and relative (file next door) targets.
    html_no_scripts = strip_script_bodies(html)

    def count_css_rel(txt):
        n = 0
        for m in re.finditer(r"url\(\s*([\"']?)([^\"')]+)\1\s*\)", txt, re.I):
            target = m.group(2).strip().lower()
            if not target.startswith(("data:", "#", "blob:", "http://", "https://", "//")):
                n += 1
        n += len(re.findall(r"@import\s+[\"'](?!https?://|data:)[^\"']+[\"']", txt, re.I))
        return n

    css_ext = count_css_ext(html_no_scripts)
    css_rel = count_css_rel(html_no_scripts)
    css_ext_libs = count_css_ext(libs_txt)
    if css_ext:
        errors.append(f"{css_ext} external CSS url()/@import: inline or convert to a data URI")
    if css_rel:
        errors.append(f"{css_rel} relative CSS url(): a separate file (image, stylesheet) breaks the single file. Inline or convert to a data URI")
    if css_ext_libs:
        warnings.append(f"{css_ext_libs} http(s) url()/@import occurrence(s) in LIBRARIES: probably inert strings of minified libs. Do NOT patch the lib: check that no execution path loads them")

    url_strings_libs = len(re.findall(r"[\"']https?://[^\"']+[\"']", libs_txt))
    if url_strings_libs:
        warnings.append(f"{url_strings_libs} URL string(s) in LIBRARIES: normal for minified code (source maps, license links). Confirm at the smoke test that none is fetched at runtime")

    n_anchors = count_external_anchors(outside_libs)
    if n_anchors:
        warnings.append(f"{n_anchors} external link(s) <a href=\"http...\">: they don't stop the tool from running offline, but won't open without a connection. Fine if deliberate")

    missing = [s for s in SENTINELS if s not in spans]
    if missing:
        errors.append(f"Missing sentinel marker(s): {', '.join(missing)}")
    else:
        oks.append("All 4 sentinel sections are present")
        order = [name for _, name in sorted((v[0], k) for k, v in spans.items())]
        if order.index("LIBRARIES") > order.index("APP CODE"):
            errors.append("The APP CODE section must come AFTER the LIBRARIES section")

    app_code = html[spans["APP CODE"][0]:spans["APP CODE"][1]] if "APP CODE" in spans else html
    libs = libs_txt
    for pattern, label in FORBIDDEN_APIS:
        if re.search(pattern, app_code):
            errors.append(f"{label} detected in APP CODE: forbidden under file://")
        elif libs and re.search(pattern, libs):
            warnings.append(f"{label} present in LIBRARIES (often inert feature-detection code; check that no execution path uses it)")

    for m in re.finditer(r"new\s+Worker\s*\(\s*([^)]*)", app_code):
        arg = m.group(1).strip()
        blob_like = ("createObjectURL" in arg) or ("blob:" in arg.lower())
        if re.match(r"[\"'][^\"']*\.js[\"']", arg) or re.search(r"[\"']https?://", arg):
            errors.append("new Worker(<file/URL>) in APP CODE: a worker loaded from a file is blocked under file:// ('null' origin). Inline the worker script as a Blob")
        elif blob_like:
            warnings.append("new Worker(Blob) in APP CODE: works under file:// but behavior varies across browsers/versions. TO CONFIRM at the smoke test (Chrome, Edge AND Firefox)")
        else:
            warnings.append("new Worker(...) in APP CODE: check that the source is an inline Blob, not a file, then confirm at the smoke test")
    if re.search(r"workerSrc\s*=\s*[\"'][^\"']*\.js[\"']", app_code, re.I):
        errors.append("workerSrc points to a .js file, which is not loadable under file://. Inline the worker as a Blob and point workerSrc at the Blob URL (see references/libraries.md, pdf.js section)")

    if re.search(r"^\s*(import|export)\s", app_code, re.M):
        errors.append("Top-level import/export in APP CODE: use classic scripts")

    if re.search(r"v\d+\.\d+", html, re.I):
        oks.append("Version number visible")
    else:
        warnings.append("No version number (vX.Y) found: the header must show name + version + date")
    # Privacy sentence: recognized in English AND in French (delivered tools follow
    # the requester's language). Keep both regex pairs byte-identical: existing
    # French tools must keep passing. Any other language triggers the warning:
    # justify it in one sentence when that is deliberate.
    has_privacy_en = re.search(r"no data", html, re.I) and re.search(r"sent over the internet", html, re.I)
    has_privacy_fr = re.search(r"aucune donn", html, re.I) and re.search(r"n'est envoy", html, re.I)
    if has_privacy_en or has_privacy_fr:
        oks.append("Privacy sentence present")
    else:
        warnings.append("Privacy sentence missing (\"no data is sent over the internet\" / « aucune donnée n'est envoyée sur internet »)")

    import shutil, subprocess, tempfile
    raw_blocks = re.findall(r"<script\b([^>]*)>(.*?)</script", html, re.S | re.I)
    if shutil.which("node"):
        ok_count = 0
        for i, (attrs, content) in enumerate(raw_blocks, start=1):
            if not content.strip():
                continue
            if re.search(r"type\s*=\s*[\"']?(application/json|text/template)", attrs, re.I):
                continue
            if re.search(r"\bsrc\s*=", attrs, re.I):
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(content)
                tmp_path = f.name
            r = subprocess.run(["node", "--check", tmp_path], capture_output=True, text=True)
            os.unlink(tmp_path)
            if r.returncode != 0:
                lines = (r.stderr or "").strip().splitlines()
                msg = next((l.strip() for l in lines if "Error" in l), lines[0].strip() if lines else "see node --check")
                errors.append(f"<script> block #{i}: JS syntax error: {msg}")
            else:
                ok_count += 1
        if ok_count:
            oks.append(f"Valid JS syntax ({ok_count} <script> block(s) checked with node --check)")
    else:
        warnings.append("node not found: JS syntax of <script> blocks NOT checked: compensate with a careful re-read")

    n_open = len(re.findall(r"<script\b", html, re.I))
    n_close = len(re.findall(r"</script", html, re.I))
    if n_open != n_close:
        errors.append(f"Unbalanced <script> tags ({n_open} opening / {n_close} closing): likely an unescaped '</script' inside an inlined library")
    else:
        oks.append(f"Balanced <script> tags ({n_open})")

    if re.search(r"\blocalStorage\b", app_code):
        warnings.append("localStorage used in APP CODE: behavior varies under file://, the tool must work fully without it")

    oks.append("Reminder: run scripts/smoke_test.cjs when a browser is available (static analysis does not catch runtime errors)")

    print(f"\n=== Validation: {os.path.basename(path)} ===\n")
    for msg in oks:
        print(f"  OK      {msg}")
    for msg in warnings:
        print(f"  WARN    {msg}")
    for msg in errors:
        print(f"  ERROR   {msg}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
