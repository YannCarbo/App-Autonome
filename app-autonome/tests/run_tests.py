#!/usr/bin/env python3
"""
Tests déterministes des garde-fous du skill : vérifient que validate_package.py et
smoke_test.cjs détectent bien CHAQUE canal réseau connu — et laissent passer un
outil conforme. C'est ce qui rend la promesse « rien ne sort de l'ordinateur »
vérifiable, pas seulement déclarée.

Chaque fixture de tests/fixtures/ contient soit zéro violation (fixtures « sain- »),
soit une violation précise. La table ATTENDUS ci-dessous déclare, pour chacune, le
code retour du validateur, les motifs qui doivent apparaître dans sa sortie, et le
verdict attendu du smoke test. Les fixtures « fuite-* » sont la clé de voûte :
elles PASSENT le validateur statique (URL ou constructeur construits dynamiquement,
invisibles sans exécution) et DOIVENT faire échouer l'assertion réseau du smoke
test — la preuve que les deux couches sont complémentaires. Cas particulier :
link-preconnect-externe est attrapée par LES DEUX couches (le smoke via son
contrôle du DOM vivant — seule défense pour un fichier sans la structure du
gabarit, qui échappe au validateur, comme la hero page docs/index.html).

Usage : python3 run_tests.py          (depuis n'importe quel répertoire)

Codes retour :
  0 = tous les tests passent (statique ET smoke)
  1 = au moins un écart attendu/obtenu -> un garde-fou a régressé, À CORRIGER
  3 = phase statique 100% verte mais smoke test sauté (node ou Playwright/Chromium
      absents) ; en CI, exiger 0 : un 3 signifie que l'environnement est incomplet

NOTE DE CONTRAT : les « motifs » sont des sous-chaînes des messages des scripts.
Tout changement de formulation dans validate_package.py ou smoke_test.cjs doit
être répercuté ici — c'est voulu : les messages font partie du contrat.
"""

import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
FIXTURES = ICI / "fixtures"
VALIDATEUR = ICI.parent / "scripts" / "validate_package.py"
SMOKE = ICI.parent / "scripts" / "smoke_test.cjs"

# smoke : "ok" = doit passer avec 0 requête sortante ; "fuite" = doit échouer sur
# une requête sortante ; "preconnexion" = doit échouer sur le contrôle DOM des
# préconnexions ; None = non concerné (la violation est purement statique).
ATTENDUS = [
    {"fixture": "sain-minimal.html", "exit": 0, "motifs": ["0 erreur"], "smoke": "ok"},
    {"fixture": "sain-lib-urls-inertes.html", "exit": 0,
     "motifs": ["0 erreur", "URL en chaîne dans LIBRARIES", "fetch() présent dans LIBRARIES"],
     "smoke": "ok"},
    {"fixture": "fuite-image-chargement.html", "exit": 0, "motifs": ["0 erreur"], "smoke": "fuite"},
    {"fixture": "fuite-au-clic-onglet.html", "exit": 0, "motifs": ["0 erreur"], "smoke": "fuite"},
    # WebSocket au constructeur résolu dynamiquement : invisible au statique, et un
    # handshake WS n'apparaît pas dans route() — exerce le capteur routeWebSocket.
    {"fixture": "fuite-websocket-dynamique.html", "exit": 0, "motifs": ["0 erreur"], "smoke": "fuite"},
    # preconnect : aucune requête interceptable — exerce le contrôle du DOM vivant.
    {"fixture": "link-preconnect-externe.html", "exit": 1,
     "motifs": ["ressource(s) chargée(s) au runtime", "<link>"], "smoke": "preconnexion"},
    {"fixture": "fetch-app-code.html", "exit": 1, "motifs": ["fetch() détecté dans APP CODE"], "smoke": None},
    {"fixture": "sendbeacon-app-code.html", "exit": 1, "motifs": ["sendBeacon"], "smoke": None},
    {"fixture": "websocket-app-code.html", "exit": 1, "motifs": ["WebSocket détecté dans APP CODE"], "smoke": None},
    {"fixture": "temps-reel-app-code.html", "exit": 1, "motifs": ["EventSource", "RTCPeerConnection"], "smoke": None},
    {"fixture": "script-src-externe.html", "exit": 1,
     "motifs": ["ressource(s) chargée(s) au runtime", "<script-src>"], "smoke": None},
    {"fixture": "img-src-relative.html", "exit": 1, "motifs": ["<img-src>"], "smoke": None},
    {"fixture": "srcset-distant.html", "exit": 1, "motifs": ["<srcset>"], "smoke": None},
    {"fixture": "a-ping.html", "exit": 1, "motifs": ["<ping>"], "smoke": None},
    {"fixture": "meta-refresh-url.html", "exit": 1, "motifs": ["<meta-refresh>"], "smoke": None},
    {"fixture": "link-css-relative.html", "exit": 1, "motifs": ["<link-stylesheet>"], "smoke": None},
    {"fixture": "css-url-mixte.html", "exit": 1,
     "motifs": ["url()/@import CSS externe", "url() CSS relative"], "smoke": None},
    {"fixture": "worker-et-module.html", "exit": 1,
     "motifs": ['type="module"', "new Worker("], "smoke": None},
]

MOTIF_SMOKE = {"ok": (0, "0 requête sortante"), "fuite": (1, "requête(s) sortante(s)"),
               "preconnexion": (1, "préconnexion")}


def lancer(cmd):
    """Exécute une commande, retourne (code, sortie). Timeout/absence = échec, pas crash."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT après 120 s"
    except FileNotFoundError as e:
        return -1, f"COMMANDE INTROUVABLE : {e.filename or cmd[0]}"


def verifier(nom, code_attendu, motifs, code, sortie, details):
    """Compare attendu/obtenu, alimente details en cas d'écart. Retourne True si OK."""
    ok = True
    if code != code_attendu:
        details.append(f"{nom} : code retour {code} (attendu {code_attendu})")
        ok = False
    for motif in motifs:
        if motif not in sortie:
            details.append(f"{nom} : motif absent de la sortie : « {motif} »")
            ok = False
    if not ok:
        extrait = "\n      ".join(sortie.strip().splitlines()[-8:])
        details.append(f"{nom} — dernières lignes de la sortie :\n      {extrait}")
    return ok


def main():
    manquantes = [a["fixture"] for a in ATTENDUS if not (FIXTURES / a["fixture"]).is_file()]
    if manquantes:
        print(f"ERREUR : fixture(s) introuvable(s) : {', '.join(manquantes)}")
        return 1

    details = []
    lignes = []
    statique_ok = True
    smoke_saute = False
    smoke_ok = True

    # --- Phase 1 : le validateur statique rend-il les verdicts attendus ? ---
    for a in ATTENDUS:
        chemin = FIXTURES / a["fixture"]
        code, sortie = lancer([sys.executable, str(VALIDATEUR), str(chemin)])
        ok = verifier(a["fixture"], a["exit"], a["motifs"], code, sortie, details)
        statique_ok = statique_ok and ok
        lignes.append([a["fixture"], f"exit {a['exit']} → {code}", "OK" if ok else "ÉCART"])

    # --- Phase 2 : l'assertion réseau du smoke test tient-elle ses promesses ? ---
    concernes = [a for a in ATTENDUS if a["smoke"]]
    for i, a in enumerate(concernes):
        chemin = FIXTURES / a["fixture"]
        code, sortie = lancer(["node", str(SMOKE), str(chemin)])
        if code == 3 or "COMMANDE INTROUVABLE" in sortie:
            # Pas de navigateur (ou pas de node) : environnement incomplet, pas une
            # régression — sauté pour toutes (inutile de réessayer les suivantes).
            smoke_saute = True
            for reste in concernes[i:]:
                lignes.append([reste["fixture"] + " (smoke)", "SAUTÉ", "SAUTÉ"])
            break
        code_attendu, motif = MOTIF_SMOKE[a["smoke"]]
        ok = verifier(a["fixture"] + " (smoke)", code_attendu, [motif], code, sortie, details)
        smoke_ok = smoke_ok and ok
        lignes.append([a["fixture"] + " (smoke)", f"exit {code_attendu} → {code}", "OK" if ok else "ÉCART"])

    # --- Rapport ---
    print(f"\n=== Tests des garde-fous ({len(ATTENDUS)} fixtures) ===\n")
    larg = max(len(l[0]) for l in lignes)
    for nom, attendu_obtenu, verdict in lignes:
        print(f"  {nom.ljust(larg)}  {attendu_obtenu.ljust(14)}  {verdict}")
    if details:
        print("\n  Écarts :")
        for d in details:
            print("    - " + d)

    if not statique_ok or not smoke_ok:
        print("\nÉCHEC : un garde-fou ne détecte plus ce qu'il doit détecter (ou bloque un outil conforme).")
        return 1
    if smoke_saute:
        print("\nPARTIEL : phase statique 100% verte, mais l'assertion réseau du smoke test n'a pas")
        print("pu être testée (node ou Playwright/Chromium absents). En CI, ce code 3 doit être un échec.")
        return 3
    print("\nOK : chaque canal réseau connu est détecté, et les outils conformes passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
