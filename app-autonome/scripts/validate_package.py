#!/usr/bin/env python3
"""
Valide qu'un outil HTML autonome respecte les contraintes du protocole file://
et la structure imposée par le skill app-autonome.

Usage : python3 validate_package.py chemin/vers/outil.html
Sortie : rapport ERREUR / AVERTISSEMENT / OK ; code retour 0 si zéro erreur, 1 sinon.

Principe de séparation ERREUR / AVERTISSEMENT :
- Une ressource RÉELLEMENT chargée par le navigateur au runtime (balise <script src>,
  <link rel=stylesheet>, <img src> distante, <iframe>/<video>/<source> src, url()/@import
  CSS externe) est une ERREUR, où qu'elle soit — y compris dans LIBRARIES : c'est ce qui
  casse la promesse « 100% hors ligne ».
- Une URL http(s) présente seulement comme CHAÎNE INERTE dans du code minifié (attribution
  de licence, détection de fonctionnalité...) reste un AVERTISSEMENT : la patcher serait plus
  dangereux que de la laisser.
Le scanner ci-dessous fait cette distinction en respectant la sémantique HTML : le contenu
d'un bloc <script>...</script> est du texte brut, donc un « <script src=... » qui y apparaît
est une chaîne, pas une balise — il n'est jamais chargé.
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

# APIs interdites en file:// — erreur dans APP CODE, avertissement dans LIBRARIES
# (les librairies contiennent souvent du code de détection de fonctionnalité inerte)
FORBIDDEN_APIS = [
    (r"\bfetch\s*\(", "fetch()"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"navigator\.serviceWorker", "Service Worker"),
    (r"\bimportScripts\s*\(", "importScripts()"),
    (r"\bimport\s*\(", "import() dynamique"),
    (r"\bshowOpenFilePicker\b|\bshowSaveFilePicker\b", "File System Access API (non supportée par Firefox)"),
    # Canaux d'ENVOI de données : rien ne doit sortir, pas seulement rien n'entrer.
    # sendBeacon( sans le préfixe navigator. : le minifié aliase souvent l'objet.
    (r"\bsendBeacon\s*\(", "navigator.sendBeacon()"),
    # new exigé pour WebSocket/EventSource/RTCPeerConnection : le mot seul apparaît
    # dans du texte ou des tests de fonctionnalité ("WebSocket" in window).
    (r"\bnew\s+WebSocket\s*\(", "WebSocket"),
    (r"\bnew\s+EventSource\s*\(", "EventSource (Server-Sent Events)"),
    (r"\bnew\s+(?:webkit)?RTCPeerConnection\s*\(", "RTCPeerConnection (WebRTC)"),
]

# rel de <link> qui déclenchent un chargement : pour ceux-là, un href même RELATIF
# est une ressource réelle (une feuille de style à côté du fichier casse le monofichier).
LINK_RELS_CHARGEANTS = {
    "stylesheet", "icon", "shortcut", "apple-touch-icon",
    "preload", "prefetch", "modulepreload", "manifest",
}


def find_section_spans(html):
    """Retourne {nom_section: (debut, fin)} d'après les marqueurs sentinelles."""
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


def _attr(tag, nom):
    """Valeur d'un attribut dans une balise, quotée ou non, ordre libre. '' si absent."""
    m = re.search(r"\b" + nom + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))", tag, re.I)
    if not m:
        return ""
    return next((g for g in m.groups() if g is not None), "").strip()


def strip_script_bodies(html):
    """
    Retourne le HTML sans les corps de <script>...</script> (balises conservées).
    Le texte d'un bloc script n'est jamais parsé comme CSS/HTML : le retirer permet
    de chercher les url()/@import CSS réels sans faux positifs venus des chaînes JS.
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
    Parcourt le HTML en respectant la règle du texte brut des blocs <script> :
    tout ce qui se trouvé entre un <script ...> et le </script suivant est ignore
    (c'est du contenu de librairie, jamais une balise a charger).
    Retourne une liste de tuples (type, extrait) pour chaque ressource RÉELLEMENT chargée.
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
                rels_chargeants = set(rel.split()) & LINK_RELS_CHARGEANTS
                if rels_chargeants and not hl.startswith(("data:", "#")):
                    # stylesheet/icon/preload... : relatif ou absolu, ça charge.
                    loads.append(("link-" + sorted(rels_chargeants)[0], href))
                elif hl.startswith(("http://", "https://", "//")):
                    loads.append(("link", href))

        m_media = re.match(r"<(img|iframe|video|audio|source|track|embed)\b", tag, re.I)
        if m_media:
            m = re.search(r"\bsrc\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
            if m and not m.group(1).strip().lower().startswith(("data:", "#", "javascript:")):
                loads.append((m_media.group(1).lower() + "-src", m.group(1)))
            # srcset : candidats séparés par ", " (une data URI contient une virgule
            # SANS espace derrière — ce split la préserve), URL = 1er token du candidat.
            srcset = _attr(tag, "srcset")
            if srcset:
                candidats = [c.strip().split()[0] for c in re.split(r",\s+", srcset) if c.strip()]
                if any(not c.lower().startswith(("data:", "#")) for c in candidats):
                    loads.append(("srcset", srcset))
            poster = _attr(tag, "poster")
            if poster and not poster.lower().startswith("data:"):
                loads.append(("poster", poster))

        if re.match(r"<(a|area)\b", tag, re.I):
            # ping= envoie un POST en arrière-plan au clic : une transmission,
            # contrairement au href de navigation (toléré, voir count_external_anchors).
            ping = _attr(tag, "ping")
            if ping:
                loads.append(("ping", ping))

        if re.match(r"<meta\b", tag, re.I) and re.search(r"http-equiv\s*=\s*[\"']?refresh", tag, re.I):
            content = _attr(tag, "content")
            if re.search(r"url\s*=", content, re.I):
                # un refresh SANS url= recharge le même fichier : inoffensif.
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
            # <use href="#icone"> (sprite interne) est le cas légitime ; une cible
            # externe est un chargement.
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
    """Compte les liens <a href="http(s)://..."> — navigation au clic, pas un chargement."""
    return len(re.findall(r"<a\b[^>]*\bhref\s*=\s*[\"']?https?://", html, re.I))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"ERREUR  Fichier introuvable : {path}")
        return 1

    errors, warnings, oks = [], [], []

    size = os.path.getsize(path)
    size_mb = size / (1024 * 1024)
    if size_mb > 15:
        errors.append(f"Taille {size_mb:.1f} Mo — beaucoup trop lourd, réduire les librairies embarquees")
    elif size_mb > 6:
        warnings.append(f"Taille {size_mb:.1f} Mo — lourd pour un partage par mail, vérifier que chaque librairie est nécessaire")
    else:
        oks.append(f"Taille : {size_mb:.2f} Mo")

    if not path.lower().endswith(".html"):
        errors.append("L'extension doit être .html")

    raw = open(path, "rb").read()
    try:
        html = raw.decode("utf-8")
        oks.append("Encodage UTF-8 valide")
    except UnicodeDecodeError:
        errors.append("Le fichier n'est pas de l'UTF-8 valide")
        html = raw.decode("utf-8", errors="replace")

    if re.search(r"<meta[^>]+charset\s*=\s*[\"']?utf-8", html, re.I):
        oks.append('<meta charset="utf-8"> présent')
    else:
        errors.append('<meta charset="utf-8"> manquant (obligatoire en file://)')

    if re.search(r"type\s*=\s*[\"']module[\"']", html, re.I):
        errors.append('<script type="module"> détecté — bloqué par CORS en file://')
    else:
        oks.append("Aucun module ES")

    spans = find_section_spans(html)
    if "LIBRARIES" in spans:
        lib_deb, lib_fin = spans["LIBRARIES"]
        libs_txt = html[lib_deb:lib_fin]
    else:
        lib_deb = lib_fin = None
        libs_txt = ""

    loads = scan_real_loads(html)
    if loads:
        aperçu = "; ".join(f"<{k}> {v[:60]}" for k, v in loads[:4])
        if len(loads) > 4:
            aperçu += f" ... (+{len(loads) - 4})"
        errors.append(
            f"{len(loads)} ressource(s) chargée(s) au runtime — l'outil doit être 100% inline/hors ligne. "
            f"Inliner (script/CSS) ou convertir en data URI (images) : {aperçu}"
        )
    else:
        oks.append("Aucune ressource chargée au runtime (tout est inline)")

    hors_libs = (html[:lib_deb] + html[lib_fin:]) if libs_txt else html

    def count_css_ext(txt):
        n = len(re.findall(r"url\(\s*[\"']?https?://", txt, re.I))
        n += len(re.findall(r"@import\s+[\"']?https?://", txt, re.I))
        return n

    # Le CSS réel (balises <style>, attributs style=) vit hors des corps de <script> :
    # on scanne le HTML débarrassé de ces corps pour éviter les faux positifs des
    # chaînes JS, et on y traque l'externe (http) ET le relatif (fichier à côté).
    sans_scripts = strip_script_bodies(html)

    def count_css_rel(txt):
        n = 0
        for m in re.finditer(r"url\(\s*([\"']?)([^\"')]+)\1\s*\)", txt, re.I):
            cible = m.group(2).strip().lower()
            if not cible.startswith(("data:", "#", "blob:", "http://", "https://", "//")):
                n += 1
        n += len(re.findall(r"@import\s+[\"'](?!https?://|data:)[^\"']+[\"']", txt, re.I))
        return n

    css_ext = count_css_ext(sans_scripts)
    css_rel = count_css_rel(sans_scripts)
    css_ext_libs = count_css_ext(libs_txt)
    if css_ext:
        errors.append(f"{css_ext} url()/@import CSS externe(s) — inliner ou convertir en data URI")
    if css_rel:
        errors.append(f"{css_rel} url() CSS relative(s) — un fichier séparé (image, feuille de style) casse le fichier unique. Inliner ou convertir en data URI")
    if css_ext_libs:
        warnings.append(f"{css_ext_libs} occurrence(s) url()/@import http(s) dans LIBRARIES — probablement des chaînes inertes de lib minifiee. NE PAS patcher la lib : vérifier qu'aucun chemin d'exécution ne les charge")

    url_strings_libs = len(re.findall(r"[\"']https?://[^\"']+[\"']", libs_txt))
    if url_strings_libs:
        warnings.append(f"{url_strings_libs} URL en chaîne dans LIBRARIES — normal pour du minifie (source maps, liens de licence). Vérifier au smoke test qu'aucune n'est fetchee a l'exécution")

    n_anchors = count_external_anchors(hors_libs)
    if n_anchors:
        warnings.append(f"{n_anchors} lien(s) externe(s) <a href=\"http...\"> — n'empêchent pas l'outil de tourner hors ligne, mais ne s'ouvriront pas sans connexion. OK si assumé")

    missing = [s for s in SENTINELS if s not in spans]
    if missing:
        errors.append(f"Marqueur(s) sentinelle(s) manquant(s) : {', '.join(missing)}")
    else:
        oks.append("Les 4 sections sentinelles sont présentes")
        order = [name for _, name in sorted((v[0], k) for k, v in spans.items())]
        if order.index("LIBRARIES") > order.index("APP CODE"):
            errors.append("La section APP CODE doit venir APRÈS la section LIBRARIES")

    app_code = html[spans["APP CODE"][0]:spans["APP CODE"][1]] if "APP CODE" in spans else html
    libs = libs_txt
    for pattern, label in FORBIDDEN_APIS:
        if re.search(pattern, app_code):
            errors.append(f"{label} détecté dans APP CODE — interdit en file://")
        elif libs and re.search(pattern, libs):
            warnings.append(f"{label} présent dans LIBRARIES (souvent du code inerte de détection — vérifier qu'aucun chemin d'exécution ne l'utilisé)")

    for m in re.finditer(r"new\s+Worker\s*\(\s*([^)]*)", app_code):
        arg = m.group(1).strip()
        blob_like = ("createObjectURL" in arg) or ("blob:" in arg.lower())
        if re.match(r"[\"'][^\"']*\.js[\"']", arg) or re.search(r"[\"']https?://", arg):
            errors.append("new Worker(<fichier/URL>) dans APP CODE — un worker chargé depuis un fichier est bloqué en file:// (origine 'null'). Inliner le script du worker en Blob")
        elif blob_like:
            warnings.append("new Worker(Blob) dans APP CODE — fonctionne en file:// mais comportement variable selon navigateur/version. A CONFIRMER au smoke test (Chrome, Edge ET Firefox)")
        else:
            warnings.append("new Worker(...) dans APP CODE — vérifier que la source est un Blob inline et non un fichier, puis confirmér au smoke test")
    if re.search(r"workerSrc\s*=\s*[\"'][^\"']*\.js[\"']", app_code, re.I):
        errors.append("workerSrc pointe vers un fichier .js — non chargeable en file://. Inliner le worker en Blob et pointer workerSrc vers l'URL du Blob (voir references/libraries.md, section pdf.js)")

    if re.search(r"^\s*(import|export)\s", app_code, re.M):
        errors.append("import/export top-level dans APP CODE — utilisér des scripts classiques")

    if re.search(r"v\d+\.\d+", html, re.I):
        oks.append("Numéro de version visible")
    else:
        warnings.append("Aucun numéro de version (vX.Y) trouvé — l'en-tete doit afficher nom + version + date")
    if re.search(r"aucune donn", html, re.I) and re.search(r"n'est envoy", html, re.I):
        oks.append("Phrase de confidentialité présente")
    else:
        warnings.append("Phrase de confidentialité absente (« aucune donnée n'est envoyée sur internet »)")

    import shutil, subprocess, tempfile
    blocs_bruts = re.findall(r"<script\b([^>]*)>(.*?)</script", html, re.S | re.I)
    if shutil.which("node"):
        nb_ok = 0
        for i, (attrs, contenu) in enumerate(blocs_bruts, start=1):
            if not contenu.strip():
                continue
            if re.search(r"type\s*=\s*[\"']?(application/json|text/template)", attrs, re.I):
                continue
            if re.search(r"\bsrc\s*=", attrs, re.I):
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(contenu)
                chemin_tmp = f.name
            r = subprocess.run(["node", "--check", chemin_tmp], capture_output=True, text=True)
            os.unlink(chemin_tmp)
            if r.returncode != 0:
                lignes = (r.stderr or "").strip().splitlines()
                msg = next((l.strip() for l in lignes if "Error" in l), lignes[0].strip() if lignes else "voir node --check")
                errors.append(f"Bloc <script> n{i} : erreur de syntaxe JS — {msg}")
            else:
                nb_ok += 1
        if nb_ok:
            oks.append(f"Syntaxe JS valide ({nb_ok} bloc(s) <script> vérifié(s) par node --check)")
    else:
        warnings.append("node introuvable : syntaxe JS des blocs <script> NON vérifiée — a compenser par une relecture attentive")

    n_open = len(re.findall(r"<script\b", html, re.I))
    n_close = len(re.findall(r"</script", html, re.I))
    if n_open != n_close:
        errors.append(f"Balises <script> déséquilibrées ({n_open} ouvertures / {n_close} fermetures) — probable '</script' non échappé dans une librairie inlinée")
    else:
        oks.append(f"Balises <script> equilibrees ({n_open})")

    if re.search(r"\blocalStorage\b", app_code):
        warnings.append("localStorage utilisé dans APP CODE — comportement variable en file://, l'outil doit fonctionner intégralement sans")

    oks.append("Rappel : lancer scripts/smoke_test.cjs si un navigateur est disponible (le statique ne détecté pas les erreurs d'exécution)")

    print(f"\n=== Validation : {os.path.basename(path)} ===\n")
    for msg in oks:
        print(f"  OK      {msg}")
    for msg in warnings:
        print(f"  ATTN    {msg}")
    for msg in errors:
        print(f"  ERREUR  {msg}")
    print(f"\n{len(errors)} erreur(s), {len(warnings)} avertissement(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
