---
name: app-autonome
description: "Transforme une idée, un besoin ou un prototype en outil web autonome."
---

# Outil HTML autonome

Ce skill produit un **unique fichier `.html`** : le destinataire double-clique dessus, son navigateur l'ouvre, l'outil fonctionne — hors ligne, sans installation, sans serveur, sans droits administrateur. Cible : Edge, Chrome et Firefox récents, utilisateurs non techniques. Le fichier est conçu pour être maintenu par IA : l'utilisateur le ré-uploade, demande une évolution, récupère une nouvelle version (voir « Mode maintenance »).

## La promesse

**L'IA sert à créer l'outil, pas à le faire tourner.** Le livrable est autonome :

- **Sans dépendance IA** : aucun crédit, aucun abonnement, aucun modèle à appeler pour l'utiliser.
- **Règles explicites** : un comportement reproductible, décrit en langage courant dans l'outil lui-même.
- **Pensé pour les équipes** : un simple fichier qui se partage par mail ou espace d'équipe.
- **100 % local** : les données ne quittent jamais l'ordinateur — aucune requête réseau, sans exception, jamais d'entre-deux « essaie le réseau puis se rabat en local ». Un seul outil qui fuit détruit la confiance dans tous les autres ; le validateur et le smoke test le bloquent.

## Posture

Le demandeur et les destinataires sont des métiers, pas des développeurs :

- **Un minimum de questions, en langage métier.** Ne demander que ce dont une mauvaise hypothèse rendrait l'outil inutilisable ou dangereux — et jamais un choix technique : c'est ton métier, pas le sien. Un fichier d'exemple vaut mieux que dix questions ; le proposer, sans en faire un préalable. **La seule question toujours obligatoire est le nom de l'outil, choisi par l'utilisateur** : il s'affiche en haut de la page et sert de nom au fichier `.html`.
- **Livrer d'abord.** Combler les trous par des hypothèses plausibles, livrer une v1 testable, lister les hypothèses dans la réponse et dans l'onglet « Règles de l'outil ». Le métier corrige plus facilement en testant qu'en répondant à un interrogatoire.
- **Jamais de correction silencieuse.** C'est ce qui rend « livrer d'abord » tenable : tout cas ambigu non tranché est signalé comme anomalie, jamais deviné. Un outil qui rate un cas mais l'affiche est acceptable ; un outil qui corrige en silence ne l'est pas.
- **Zéro jargon.** Pas de « UMD », « CORS », « parser » dans les réponses : dire « double-cliquez dessus », « fonctionne sans connexion internet ».

## Étape 1 — Comprendre le besoin

Identifier : **entrées** (fichiers, colonnes avec leurs noms exacts, formats réels), **règles métier** (préférer un exemple chiffré à une description abstraite), **sorties** (format, nommage), **cas limites** (donnée obligatoire manquante : bloquer, avertir, valeur par défaut ?), **volumétrie** (au-delà de ~50 000 lignes : traitement par lots + barre de progression).

**Si un fichier d'exemple est fourni, l'inspecter réellement avant d'écrire une ligne de code** — les colonnes réelles réservent des surprises par rapport à la description verbale.

## Étape 2 — Garde-fous données (obligatoires pour toute transformation)

Le pire scénario n'est pas un plantage, c'est une corruption silencieuse. Patterns prêts à adapter dans `references/patterns-metier.md`.

1. **Aperçu avant/après** : un échantillon des données transformées (10–20 lignes) avant téléchargement.
2. **Rapport chiffré** : « 212 lignes lues, 208 transformées, 4 anomalies », avec liste et numéros de ligne.
3. **Zéro correction silencieuse** : cas ambigu = anomalie signalée ; ligne exclue avec mention ou conservée avec avertissement.
4. **Jamais d'écrasement** : le fichier produit porte un nom distinct de l'original (`fournisseur_formate_2026-07-16.xlsx`).
5. **Erreurs explicites** : « Ce fichier ne contient pas de colonne “Référence”. Colonnes trouvées : … », pas une erreur technique.

## Étape 3 — Règles d'or du `file://` (non négociables)

Ouvert par double-clic = protocole `file://`, origine opaque `null`. Une app qui marche sur un serveur de dev peut être totalement morte en double-clic :

- **Scripts classiques uniquement.** Jamais `<script type="module">`, jamais `import`/`export` : bloqués par CORS.
- **Aucune ressource externe.** Aucune URL `http(s)` dans un `src`, `href`, `action` ou `url()` CSS : tout est inliné. (Exception : les `xmlns` des SVG — identifiants, pas téléchargements.)
- **Jamais `fetch()` ni `XMLHttpRequest`.** Fichiers utilisateur : `<input type="file">` + `FileReader`. Données embarquées : `<script type="application/json" id="data-inline">` lu par `JSON.parse(...)`.
- **Pas de Web Workers ni Service Workers** : `new Worker("fichier.js")` échoue depuis une origine `null`. Traitements longs découpés en lots via `setTimeout`/`requestAnimationFrame`. Exception étroite : worker inliné en Blob quand une lib l'exige vraiment (typiquement pdf.js) — à confirmer au smoke test sur Chrome, Edge et Firefox.
- **Pas de File System Access API** (non supportée par Firefox). Sortie = `Blob` + lien `<a download>` cliqué programmatiquement.
- **`localStorage` = bonus, jamais critique** (comportement variable en `file://`) : l'outil fonctionne intégralement sans.
- **`<meta charset="utf-8">`** en tête de `<head>` ; images en SVG inline ou data URI ; polices système uniquement.

## Et si le besoin exige internet ?

Requalifier en langage métier, jamais opposer un refus sec — la plupart des « besoins d'internet » ont une réponse hors ligne acceptable :

- **« Les données de référence changent »** → les embarquer (`<script type="application/json">`) ; le cycle de maintenance produit une nouvelle version quand elles changent vraiment.
- **« Il faut interroger notre système »** (ERP, CRM) → l'utilisateur exporte lui-même (Excel, CSV) et charge l'export dans l'outil.
- **« Il faut envoyer le résultat »** → l'outil produit un fichier, l'utilisateur l'envoie par son canal habituel. Tolérés car rien ne se charge à l'ouverture : un `mailto:` préparé, un lien `<a href>` de navigation suivi au clic.
- **Vrai temps réel** (stock partagé, écriture directe dans un système) → le dire honnêtement : c'est une application web hébergée, un autre livrable hors périmètre — jamais une variante « dégradée » d'un outil autonome.

## Étape 4 — Librairies

Lire `references/libraries.md` (librairies vérifiées avec build navigateur, URLs, procédure). Trois échelons : **vanilla JS** (outil simple) → **Alpine.js** (quelques états d'interface) → **Vue 3 en build global** (vraie application à état). Jamais React ≥ 19 ni Tailwind pour un outil neuf. N'embarquer que le nécessaire : chaque lib ajoute des centaines de Ko.

Pièges d'inlining :

- **Échapper `</script`** dans toute lib avant insertion : remplacer par `<\/script`, sinon la balise se ferme prématurément.
- **`defer`/`async` sont perdus** en inline : une lib à démarrage automatique (Alpine…) s'exécute avant l'APP CODE qui la suit. Envelopper la lib dans `window.addEventListener("DOMContentLoaded", () => { … })` pour restituer l'ordre d'origine.
- **Les builds minifiés sont intangibles** : aucune modification au-delà de l'échappement ci-dessus. Un avertissement du validateur sur du contenu de LIBRARIES se justifie dans la réponse, ne se patche jamais.
- **Versions fraîches puis figées** : télécharger la dernière stable, la consigner dans le commentaire du bloc (nom@version) ; le livrable n'ira plus jamais rien chercher en ligne.

## Étape 5 — Structure du fichier

Partir de `assets/template.html`. Sections délimitées par des marqueurs sentinelles — c'est ce qui rend la maintenance par IA possible sans relire les libs minifiées :

```
<!-- ===== SECTION: STYLES ===== -->
<!-- ===== SECTION: MARKUP ===== -->
<!-- ===== SECTION: LIBRARIES (ne pas éditer) ===== -->
<!-- ===== SECTION: APP CODE ===== -->
```

Trois éléments obligatoires dans l'interface :

- **En-tête** : `Nom de l'outil — VX.X du JJ/MM/AAAA`, en dur dans le HTML.
- **Deux onglets** : « Traitement » (actif par défaut) et « Règles de l'outil » (transformations et hypothèses, en langage courant — la documentation vit dans l'outil, pas dans la conversation). Le gabarit fournit le mécanisme d'onglets : le réutiliser.
- **Pied de page** : `Cet outil fonctionne entièrement dans votre navigateur — aucune donnée n'est envoyée sur internet.`

Le reste est libre : design sobre avec une identité (couleur d'accent liée au domaine), boutons nommés par leur effet (« Télécharger le fichier corrigé », pas « Valider »), interface dans la langue de l'utilisateur.

## Étape 6 — Validation

```bash
python3 scripts/validate_package.py chemin/vers/outil.html
```

Corriger et relancer jusqu'à **zéro erreur**. Une **erreur** se corrige dans STYLES/MARKUP/APP CODE ou dans l'assemblage — jamais en éditant une lib minifiée. Un **avertissement** se traite au jugement et se justifie en une phrase.

Le zéro erreur du validateur (statique) ne prouve pas que la page s'exécute. Trois couches complémentaires, de la moins chère à la plus probante :

1. **Fonctions pures sous node** : isoler la logique métier (voir `references/patterns-metier.md`) et la tester avec des cas chiffrés avant de l'inliner.
2. **Smoke test navigateur**, quand un navigateur est disponible :
   ```bash
   node scripts/smoke_test.cjs chemin/vers/outil.html
   ```
   Ouvre réellement le fichier en `file://` hors ligne, clique chaque onglet, échoue sur toute erreur JS et toute requête sortante — c'est le test déterministe du « 100 % local ». « SAUTÉ » n'est pas un feu vert : la vérification retombe sur la première ouverture chez l'utilisateur (Étape 7).
3. **Validation métier sur données réelles** (ou échantillon anonymisé représentatif) : faire vérifier au métier quelques résultats attendus et les principaux cas limites. Pour une transformation critique (compta, ERP, douane), ce préalable est non négociable.

Self-check des garde-fous eux-mêmes — en cas de doute sur l'environnement ou après modification des scripts du skill : `python3 tests/run_tests.py` (code 1 = un garde-fou a régressé, ne pas valider d'outil).

## Étape 7 — Livraison

- Nom de fichier : `nom-outil-v1.0.html` (kebab-case, version incluse — le nom survit aux transferts, pas les métadonnées).
- Livrer via l'outil de présentation de fichiers, **avec un fichier d'exemple** si l'outil transforme des fichiers : le métier teste immédiatement, sans risquer de vraies données.
- Mode d'emploi numéroté obligatoire, en langage courant, couvrant quatre moments : **1. Récupérer** (télécharger, enregistrer) · **2. Ouvrir** (double-clic, s'ouvre dans le navigateur, tout se passe sur l'ordinateur) · **3. Tester** (scénario concret avec le fichier d'exemple, dire quoi vérifier) · **4. Partager** (comme un simple fichier, depuis l'espace d'équipe ; par mail, zipper le `.html` s'il est bloqué en pièce jointe).
- Ajouter les deux phrases qui évitent 90 % des tickets : « Si le fichier s'ouvre dans le Bloc-notes : clic droit > Ouvrir avec > Edge. » et « Pour toute évolution : renvoyez-moi ce fichier dans une nouvelle conversation en décrivant le changement voulu. »

## Mode conversion (multi-fichiers → fichier unique)

L'inlining mécanique ne suffit pas : inventorier d'abord ce que la structure d'origine garantissait implicitement.

1. **`defer`/`async`/`type` et l'ordre d'exécution réel** qui en découle : reproduire cet ordre-là (positionnement + enveloppe `DOMContentLoaded`), pas l'ordre d'apparition.
2. **Les libs qui scannent le DOM à leur exécution** (Alpine via `x-data`, Tailwind Play…) doivent s'exécuter après que ce DOM existe.
3. **Les ressources réseau à couper** : polices → pile système, images distantes → data URI, `fetch` de données → `<script type="application/json">`.

Puis dérouler les Étapes 5 à 7. Les libs héritées de l'existant (Tailwind Play, React 18 UMD…) peuvent rester telles quelles : « jamais pour un outil neuf » ne s'applique pas à une conversion.

## Mode maintenance (outil existant uploadé)

1. **Ne jamais lire le fichier en entier** (LIBRARIES pèse des Mo de minifié) : `grep -n "===== SECTION" outil.html`, puis lire uniquement STYLES, MARKUP et APP CODE par plages de lignes.
2. Modifier **sans toucher LIBRARIES** — sauf mise à jour de lib explicitement demandée : re-télécharger, ré-échapper, remplacer le bloc entier, mettre à jour le commentaire nom@version.
3. Incrémenter version et date (en-tête + nom de fichier) ; mettre à jour l'onglet « Règles de l'outil » si les règles ont changé.
4. Revalider (`scripts/validate_package.py`), livrer sous le nouveau nom versionné.

Si le fichier n'a pas les marqueurs sentinelles (créé hors skill), proposer de le restructurer au format du skill à l'occasion de la modification.
