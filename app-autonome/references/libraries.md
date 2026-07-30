# Librairies vérifiées pour outils HTML autonomes

Toutes les librairies ci-dessous disposent d'un **build navigateur** (global/UMD/IIFE) : un fichier `.js` unique qui s'exécute dans une balise `<script>` classique et expose une variable globale. C'est la seule forme compatible avec le protocole `file://`.

## Trouver la dernière version stable

Ne jamais coder une version de mémoire. À la génération :

```bash
# Version stable la plus récente sur npm
curl -s https://registry.npmjs.org/vue/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])"
```

Puis télécharger le build en remplaçant `VERSION` dans l'URL du tableau ci-dessous.

## Tableau des librairies

| Besoin | Librairie | Variable globale | URL du build navigateur |
|---|---|---|---|
| UI réactive | Vue 3 | `Vue` | `https://unpkg.com/vue@VERSION/dist/vue.global.prod.js` |
| Réactivité légère dans le HTML | Alpine.js | `Alpine` | `https://unpkg.com/alpinejs@VERSION/dist/cdn.min.js` (charger avec `defer`) |
| Lire/écrire Excel (.xlsx, .xls) | SheetJS | `XLSX` | `https://cdn.sheetjs.com/xlsx-latest/package/dist/xlsx.full.min.js` |
| Parser/générer CSV | PapaParse | `Papa` | `https://unpkg.com/papaparse@VERSION/papaparse.min.js` |
| Graphiques | Chart.js | `Chart` | `https://unpkg.com/chart.js@VERSION/dist/chart.umd.js` |
| Graphiques avancés/scientifiques | Plotly | `Plotly` | `https://unpkg.com/plotly.js-dist-min@VERSION/plotly.min.js` (~4,5 Mo : seulement si Chart.js ne suffit pas) |
| Dates (parsing, formatage) | Day.js | `dayjs` | `https://unpkg.com/dayjs@VERSION/dayjs.min.js` |
| Créer/lire des ZIP | JSZip | `JSZip` | `https://unpkg.com/jszip@VERSION/dist/jszip.min.js` |
| Générer des PDF (dessin) | jsPDF | `jspdf` (puis `jspdf.jsPDF`) | `https://unpkg.com/jspdf@VERSION/dist/jspdf.umd.min.js` |
| Remplir un formulaire PDF (AcroForm) | pdf-lib | `PDFLib` | `https://unpkg.com/pdf-lib@VERSION/dist/pdf-lib.min.js` |
| Excel avec style riche / logo | ExcelJS | `ExcelJS` | `https://unpkg.com/exceljs@VERSION/dist/exceljs.min.js` |
| Compresser un PDF riche en images | pdf.js (+ pdf-lib) | `pdfjsLib` | `https://unpkg.com/pdfjs-dist@VERSION/build/pdf.min.js` (voir note worker) |
| Manipuler des .docx | docx | `docx` | `https://unpkg.com/docx@VERSION/build/index.umd.js` |
| Diff de textes | jsdiff | `Diff` | `https://unpkg.com/diff@VERSION/dist/diff.min.js` |

Notes :
- **jsPDF vs pdf-lib** : jsPDF *dessine* un PDF depuis zéro (texte, formes) ; **pdf-lib** *charge un PDF existant* et remplit ses champs de formulaire (AcroForm) — le bon choix pour reproduire un formulaire réglementaire à partir d'un template fourni. `form.getFields()` liste les noms de champs ; un champ absent doit être **signalé en anomalie**, pas ignoré.
- **ExcelJS vs SheetJS** : SheetJS suffit pour lire/écrire des données ; passer à **ExcelJS** seulement si la sortie exige un style riche (couleurs conditionnelles, bordures, logo image). Alternative souvent plus fiable : partir d'un classeur template mis en forme par l'utilisateur et n'y écrire que les cellules de données.
- **pdf.js et le Web Worker (important en `file://`)** : pdf.js veut un worker. En `file://`, un `workerSrc` pointant vers un fichier `.js` **ne se charge pas** (origine `null`, voir Étape 3 du SKILL). Deux options : (a) inliner le contenu de `pdf.worker.min.js` dans un Blob et pointer `workerSrc` sur l'URL du Blob — fonctionne, mais **à confirmer au smoke test** (Chrome/Edge/Firefox) ; (b) désactiver le worker et travailler sur le thread principal, plus lent, à découper en lots pour ne pas geler l'UI. La compression par rastérisation reste une compression **avec perte** qui transforme le texte en image (plus de texte sélectionnable) : l'annoncer clairement à l'utilisateur.
- **SheetJS** : les versions récentes ne sont plus publiées sur npm (bloqué en 0.18.5). Utiliser exclusivement `cdn.sheetjs.com` ; `xlsx-latest` pointe toujours vers la dernière version. Consigner la version réelle relevée dans l'en-tête du fichier téléchargé dans le commentaire `nom@version` du bloc inliné (section LIBRARIES).
- **Vue** : impérativement `vue.global.prod.js`. Ni `vue.esm-browser.js` (module ES, mort en `file://`), ni `vue.global.js` (build de dev, lourd et verbeux en console).
- Une librairie hors de ce tableau est utilisable **si et seulement si** elle passe la procédure de vérification ci-dessous.

## À proscrire

- **React ≥ 19** : plus aucun build UMD publié, et le JSX exige de toute façon une compilation. (React 18 en UMD reste techniquement possible mais Vue 3 global ou Alpine.js sont les choix par défaut ici.)
- **Tailwind CSS en production nécessite une compilation.** Nuance honnête : le script "navigateur" de Tailwind, auto-hébergé, fonctionne en `file://` — il compile les classes à la volée dans le navigateur. Mais c'est ~400 Ko de compilateur rechargé et ré-exécuté à chaque ouverture, déconseillé par Tailwind même, et du CSS écrit à la main est plus léger et plus lisible en maintenance. Ne l'accepter que pour réutiliser tel quel un existant déjà écrit en classes Tailwind ; jamais pour un outil neuf.
- **Alpine.js** se charge impérativement avec l'attribut `defer` (il scanne le DOM au chargement).
- **Tout package "ESM only"** (ex. `lodash-es`, beaucoup de librairies récentes) : la présence sur npm ne garantit rien, vérifier le contenu de `dist/`.
- **Polices web externes** (Google Fonts...) : pile de polices système uniquement.

## Vérifier qu'un build est réellement compatible `file://`

Après téléchargement, avant d'inliner :

```bash
# 1. Le début du fichier : on doit voir un wrapper UMD/IIFE, pas de mots-clés module
head -c 600 lib.js
# Mauvais signes : "import ", "export " en début de ligne
grep -nE '^\s*(import|export)\s' lib.js | head -5   # doit être vide

# 2. La séquence fatale pour l'inline (fermerait la balise <script> prématurément)
grep -c '</script' lib.js    # si > 0, remplacer '</script' par '<\/script'
python3 - <<'EOF'
data = open('lib.js', encoding='utf-8').read()
open('lib.js', 'w', encoding='utf-8').write(data.replace('</script', '<\\/script'))
EOF

# 3. Test d'exécution : la globale doit exister après chargement en contexte non-module
node -e "global.window=global; global.self=global; global.document={createElement:()=>({}),}; require('./lib.js'); console.log(typeof window.NomGlobale)" 2>/dev/null || echo "Test node non concluant — vérifier manuellement le wrapper UMD"
```

Le test node est indicatif (certains builds navigateur légitimes touchent au DOM au chargement) : en cas d'échec, inspecter le wrapper à l'œil. Le critère décisif reste l'absence d'`import`/`export` top-level et la présence d'une affectation à `window`/`this`/`self`.

## Charger les librairies dans le bon ordre

Dans la section LIBRARIES, chaque librairie occupe sa propre balise `<script>`, précédée d'un commentaire nom + version + URL d'origine :

```html
<!-- vue@3.5.17 — https://unpkg.com/vue@3.5.17/dist/vue.global.prod.js -->
<script>/* ...contenu minifié... */</script>
```

Ordre : les dépendances avant les dépendants (ex. Day.js avant un plugin Day.js). La section APP CODE vient toujours après LIBRARIES.
