#!/usr/bin/env node
/*
 * Smoke test d'un outil HTML autonome : ouvre RÉELLEMENT le fichier en file://
 * dans un Chromium headless et vérifie ce que le validateur statique ne peut pas voir —
 * qu'aucune erreur JS ne survient au chargement, que les éléments d'interface clés
 * existent, ET qu'aucune requête réseau ne sort.
 *
 * C'est le test déterministe de la promesse « coupez le Wi-Fi » :
 *   - le contexte navigateur est passé HORS LIGNE (setOffline) ;
 *   - toute requête est interceptée AVANT la création de la page : file:// vers le
 *     document lui-même = autorisé, tout le reste = bloqué ET journalisé (y compris
 *     les WebSockets via routeWebSocket, et les requêtes émises par un worker Blob) ;
 *   - après chargement, chaque onglet .onglet est cliqué (une fuite peut attendre
 *     une interaction) ;
 *   - le DOM vivant est inspecté : un <link rel="preconnect"> ou dns-prefetch vers
 *     l'extérieur ouvre une connexion SANS émettre de requête interceptable — seul
 *     ce contrôle DOM peut le voir, et c'est un échec au même titre qu'une requête ;
 *   - verdict : la SEULE requête de toute la session doit être le fichier lui-même.
 *     Une URL construite dynamiquement (new Image().src = "https://...") est invisible
 *     pour l'analyse statique — c'est ici qu'elle se fait attraper.
 *
 * Usage :
 *   node smoke_test.cjs chemin/vers/outil.html
 *
 * Codes retour :
 *   0  = la page se charge sans erreur, les contrôles attendus sont présents,
 *        et zéro requête sortante
 *   1  = erreur JS, contrôle manquant, OU requête réseau sortante  -> À CORRIGER
 *   3  = aucun navigateur disponible (Playwright/Chromium absent) -> smoke test SAUTÉ,
 *        retomber sur le point de contrôle de première ouverture décrit à l'utilisateur
 *
 * Le validateur statique (validate_package.py) et ce smoke test sont complémentaires :
 * le premier attrape les violations de structure et de file:// AVANT exécution, le second
 * attrape les erreurs d'EXÉCUTION et les fuites réseau à l'exécution. Aucun des deux ne
 * prouve que la LOGIQUE MÉTIER est juste : ça reste la validation métier sur données
 * réelles.
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
    console.log("Usage: node smoke_test.cjs chemin/vers/outil.html");
    process.exit(2);
  }
  const abs = path.resolve(file);

  const pw = resolvePlaywright();
  if (!pw || !pw.chromium) {
    console.log("SAUTÉ  Playwright/Chromium introuvable dans cet environnement.");
    console.log("       Le smoke test automatique n'a pas pu tourner. À compenser par le");
    console.log("       point de contrôle de première ouverture (Étape 7 du skill) :");
    console.log("       demander à l'utilisateur de confirmer ce qui doit s'afficher.");
    process.exit(3);
  }

  let browser;
  try {
    browser = await pw.chromium.launch();
  } catch (e) {
    console.log("SAUTÉ  Chromium présent mais non lançable : " + (e.message || e).split("\n")[0]);
    process.exit(3);
  }

  // URL canonique du document (gère espaces/accents du chemin — ne pas concaténer
  // "file://" + abs à la main).
  const docUrl = require("url").pathToFileURL(abs).href;

  const jsErrors = [];
  const requetes = [];        // toutes les requêtes de la session, quel que soit leur sort
  let wsNonSurveille = false; // Playwright < 1.48 : pas de routeWebSocket

  // Toute l'instrumentation réseau est posée sur le CONTEXTE, AVANT la création de
  // la page : aucune requête ne peut précéder le filet.
  const context = await browser.newContext();
  await context.setOffline(true); // « coupez le Wi-Fi » émulé — n'affecte pas file://

  if (typeof context.routeWebSocket === "function") {
    // Un handshake WebSocket n'apparaît PAS dans route()/on('request') : routeWebSocket
    // est le seul capteur fiable — et tant qu'on n'appelle pas connectToServer(),
    // la connexion ne part jamais réellement.
    await context.routeWebSocket("**", (ws) => {
      requetes.push({ type: "websocket", url: ws.url() });
    });
  } else {
    wsNonSurveille = true;
  }

  await context.route("**", (route) => {
    const req = route.request();
    requetes.push({ type: req.resourceType(), url: req.url() });
    if (req.url().startsWith("file://")) {
      return route.continue(); // le document lui-même ; toute AUTRE file:// sera jugée au verdict
    }
    return route.abort("blockedbyclient"); // rien ne sort réellement, même pendant le test
  });

  const page = await context.newPage();
  page.on("pageerror", (e) => jsErrors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") jsErrors.push("console.error: " + m.text()); });

  let loadOk = true;
  try {
    await page.goto(docUrl, { waitUntil: "load", timeout: 15000 });
    // Laisser les scripts différés (DOMContentLoaded, microtâches) se dérouler.
    await page.waitForTimeout(1200);
    // Une fuite peut attendre une interaction : cliquer chaque onglet du gabarit.
    // (timeout court : un onglet masqué ne doit pas bloquer 30 s, et un échec de
    // clic n'est pas un échec du test — c'est le réseau qu'on observe ici.)
    for (const onglet of await page.$$(".onglet")) {
      await onglet.click({ timeout: 2000 }).catch(() => {});
      await page.waitForTimeout(300);
    }
    await page.waitForTimeout(1000); // beacons tardifs
  } catch (e) {
    loadOk = false;
    jsErrors.push("Échec de navigation : " + (e.message || e).split("\n")[0]);
  }

  // Invariants d'interface : titre, en-tête, et — pour un outil de fichiers — un input file.
  const info = await page.evaluate(() => ({
    title: document.title,
    hasHeader: !!document.querySelector("header, h1"),
    fileInputs: document.querySelectorAll('input[type="file"]').length,
    hasDownloadHook: /download/i.test(document.body ? document.body.innerHTML : ""),
    bodyLen: document.body ? document.body.innerText.trim().length : 0,
    // preconnect/dns-prefetch n'émettent AUCUNE requête interceptable (connexion
    // ouverte en avance, pas un chargement) : seule l'inspection du DOM vivant les
    // voit. On lit l.href (résolu) : une cible relative devient file:// et est
    // ignorée ; preload/prefetch émettent de vraies requêtes, déjà interceptées.
    preconnexions: Array.from(document.querySelectorAll("link[rel]"))
      .filter((l) => /\b(preconnect|dns-prefetch)\b/i.test(l.rel) && /^https?:\/\//i.test(l.href))
      .map((l) => "<" + l.rel + "> " + l.href),
  })).catch(() => null);

  await browser.close();

  // Verdict réseau : la SEULE requête légitime de toute la session est le document.
  // (data:/blob: ne génèrent jamais d'événement : pas de liste blanche à maintenir.)
  const violations = [];
  for (const r of requetes) {
    if (r.url === docUrl) continue;
    if (r.url.startsWith("file://")) {
      violations.push("<" + r.type + "> " + r.url + " (ressource file:// séparée — l'outil n'est pas monofichier)");
    } else {
      violations.push("<" + r.type + "> " + r.url);
    }
  }
  const violationsUniques = [...new Set(violations)];

  const preconnexions = info ? info.preconnexions : [];

  const problems = [];
  if (!loadOk) problems.push("la page n'a pas pu se charger");
  if (jsErrors.length) problems.push(jsErrors.length + " erreur(s) JS au chargement");
  if (info && !info.hasHeader) problems.push("aucun <header>/<h1> visible (interface vide ?)");
  if (info && info.bodyLen === 0) problems.push("le <body> est vide à l'écran");
  if (violationsUniques.length) problems.push(violationsUniques.length + " requête(s) sortante(s) détectée(s)");
  if (preconnexions.length) problems.push(preconnexions.length + " préconnexion(s) déclarée(s) vers l'extérieur");

  console.log("\n=== Smoke test : " + path.basename(abs) + " ===\n");
  if (info) {
    console.log("  titre        : " + JSON.stringify(info.title));
    console.log("  en-tête      : " + (info.hasHeader ? "présent" : "ABSENT"));
    console.log("  input file   : " + info.fileInputs + (info.fileInputs ? " trouvé(s)" : " (aucun — normal si l'outil ne lit pas de fichier)"));
    console.log("  bouton dl    : " + (info.hasDownloadHook ? "mention 'download' présente" : "aucune (à vérifier si l'outil produit un fichier)"));
  }
  if (violationsUniques.length) {
    console.log("  réseau       : " + violationsUniques.length + " requête(s) sortante(s) — PROMESSE CASSÉE :");
    violationsUniques.slice(0, 10).forEach((v) => console.log("    - " + v));
  } else {
    console.log("  réseau       : 0 requête sortante" +
      (preconnexions.length ? "" : " — promesse « coupez le Wi-Fi » tenue") +
      (wsNonSurveille ? " (WebSocket non surveillé : Playwright < 1.48)" : ""));
  }
  if (preconnexions.length) {
    console.log("  préconnexion : " + preconnexions.length + " déclarée(s) vers l'extérieur — PROMESSE CASSÉE :");
    preconnexions.slice(0, 10).forEach((p) => console.log("    - " + p));
    console.log("    (un preconnect/dns-prefetch ouvre une connexion sans requête : retirer la balise <link>)");
  }
  if (jsErrors.length) {
    console.log("\n  Erreurs détectées :");
    jsErrors.slice(0, 10).forEach((e) => console.log("    - " + e));
  }

  if (problems.length) {
    console.log("\nÉCHEC : " + problems.join(" ; ") + ".");
    console.log("Corriger puis relancer. (Rappel : ce test ne vérifie pas la justesse des calculs métier.)");
    process.exit(1);
  }
  console.log("\nOK : la page se charge sans erreur JS, l'interface s'affiche, aucune requête ne sort.");
  console.log("Reste à valider la LOGIQUE MÉTIER sur données réelles/représentatives (voir Étape 6).");
  process.exit(0);
}

main().catch((e) => {
  console.log("Erreur inattendue du smoke test : " + (e && e.message ? e.message : e));
  process.exit(1);
});
