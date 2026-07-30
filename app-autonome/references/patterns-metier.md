# Patterns métier réutilisables

Ces patterns reviennent d'un outil à l'autre quel que soit le domaine. Ils vivent dans la
section **APP CODE** (lisible, commentée, jamais minifiée). Ils sont adaptés au modèle
**fichier unique `file://`** : aucun `fetch`, aucune référence à un dossier `libs/`, tout est
inline. Copier-adapter, ne pas réinventer.

## 1. Glisser-déposer + sélection de fichier

L'`<input type="file">` reste la source de vérité ; le glisser-déposer n'est qu'un confort.

```html
<div id="zone-depot" class="zone-depot">
  Glissez votre fichier ici, ou <label for="input-fichier" class="lien">choisissez-le</label>
  <input type="file" id="input-fichier" accept=".xlsx,.csv" hidden />
</div>
```

```js
const zone = document.getElementById("zone-depot");
const input = document.getElementById("input-fichier");
["dragenter", "dragover"].forEach(evt =>
  zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.add("survol"); }));
["dragleave", "drop"].forEach(evt =>
  zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.remove("survol"); }));
zone.addEventListener("drop", e => traiterFichier(e.dataTransfer.files[0]));
input.addEventListener("change", e => traiterFichier(e.target.files[0]));
```

## 2. Panneau d'alertes par gravité (le garde-fou de l'Étape 2)

Ne jamais échouer en silence, ne jamais noyer une alerte critique dans 50 lignes d'info.
Séparer par gravité, afficher les erreurs en premier, avec le numéro de ligne.

```js
function validerLigne(ligne, index) {
  const alertes = [];
  const noLigne = index + 2; // +2 : en-tête + index 0
  if (!ligne.adresse) alertes.push({ gravite: "erreur", message: `Ligne ${noLigne} (${ligne.client ?? "client inconnu"}) : adresse manquante` });
  if (ligne.poids != null && ligne.poids <= 0) alertes.push({ gravite: "avertissement", message: `Ligne ${noLigne} : poids nul ou négatif, à vérifier` });
  return alertes;
}

function afficherResume(nbLignes, nbTransformees, toutesAlertes) {
  const erreurs = toutesAlertes.filter(a => a.gravite === "erreur");
  const avertissements = toutesAlertes.filter(a => a.gravite === "avertissement");
  document.getElementById("resume").innerHTML = `
    <p>${nbLignes} lignes lues, ${nbTransformees} transformées, ${erreurs.length + avertissements.length} anomalie(s).</p>
    ${erreurs.length ? `<div class="alerte erreur"><strong>${erreurs.length} erreur(s) à corriger</strong><ul>${erreurs.map(a => `<li>${a.message}</li>`).join("")}</ul></div>` : ""}
    ${avertissements.length ? `<div class="alerte avertissement"><strong>${avertissements.length} avertissement(s)</strong><ul>${avertissements.map(a => `<li>${a.message}</li>`).join("")}</ul></div>` : ""}
    ${!toutesAlertes.length ? `<div class="alerte ok">Aucune anomalie détectée.</div>` : ""}`;
}
```

Décider avec l'utilisateur, en Étape 1, si une erreur bloque **la ligne** (les autres passent) ou
**tout le traitement**. En général, bloquer ligne par ligne et continuer est plus utile — mais
confirmer, et toujours **signaler**, jamais deviner (règle « zéro correction silencieuse »).

## 3. Règles métier : fonctions pures et testables

Séparer « lire », « appliquer les règles » et « générer la sortie ». Ça permet de tester la logique
isolément (avec `node`, avant inlining — voir Étape 6) et évite qu'un bug de génération masque un
bug de calcul.

```js
// Fonction pure : vérifiable avec les exemples chiffrés donnés en Étape 1.
function calculerPalettes(colis, { volumeMax = 1.44, poidsMax = 800 } = {}) {
  const volume = colis.reduce((s, c) => s + c.longueur * c.largeur * c.hauteur, 0);
  const poids = colis.reduce((s, c) => s + c.poids, 0);
  return Math.max(Math.ceil(volume / volumeMax), Math.ceil(poids / poidsMax));
}
// Avant de brancher sur l'UI :
console.assert(calculerPalettes([{ longueur: 1, largeur: 1, hauteur: 1, poids: 500 }]) === 1, "cas simple");
```

Documenter en commentaire les constantes métier (seuils, arrondis) : ce sont les valeurs les plus
susceptibles de changer, et l'onglet « Règles de l'outil » de l'interface doit les refléter.

## 4. Regrouper par clé avant génération

```js
function grouperPar(lignes, cle) {
  return lignes.reduce((g, ligne) => {
    (g[ligne[cle] ?? "Non renseigné"] ??= []).push(ligne);
    return g;
  }, {});
}
```

## 5. Enchaînement complet : extract → génération multi-fichiers → ZIP

```js
async function traiterExtract(fichier) {
  const lignes = await lireExcel(fichier);            // voir references/libraries.md (SheetJS)
  const alertes = lignes.flatMap(validerLigne);
  const valides = lignes.filter((_, i) => !alertes.some(a => a.gravite === "erreur" && a.message.includes(`Ligne ${i + 2} `)));
  afficherResume(lignes.length, valides.length, alertes);

  const parClient = grouperPar(valides, "client");
  const zip = new JSZip();                            // voir references/libraries.md (JSZip)
  for (const [client, lignesClient] of Object.entries(parClient)) {
    const dossier = zip.folder(client);
    dossier.file("packing-list.xlsx", genererPackingList(lignesClient)); // -> Blob
    dossier.file("bordereau.pdf", await genererPdf(lignesClient));        // -> Blob/Uint8Array
  }
  const contenu = await zip.generateAsync({ type: "blob" });
  telechargerFichier(contenu, `export_${new Date().toISOString().slice(0, 10)}.zip`, "application/zip");
}
```

`telechargerFichier` est fournie dans le template (`assets/template.html`). Le téléchargement se
déclenche par un **clic explicite**, jamais automatiquement, et **après** que l'utilisateur a vu
l'aperçu et le résumé.

## 6. Ne jamais geler l'UI sur un gros traitement (sans Web Worker)

Pas de worker en `file://` (voir Étape 3). Un `await` par étape avec un compteur suffit pour la
quasi-totalité des volumétries métier ; au-delà, découper en lots avec `traiterParLots` (template).

```js
const barre = document.getElementById("progression");
for (let i = 0; i < clients.length; i++) {
  await traiterUnClient(clients[i]);
  barre.textContent = `${i + 1} / ${clients.length} clients traités`;
}
```
