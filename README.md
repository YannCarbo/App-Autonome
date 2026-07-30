# App Autonome

[![Licence : MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)

**Utilisez l'IA pour créer votre outil. Pas pour le faire tourner.**

Transformez vos procédures en applications locales grâce à l'IA, puis utilisez-les sans elle. Des outils explicables et reproductibles, faciles à partager, qui gardent vos données sur votre poste.

- **100 % local** — les données ne quittent jamais l'ordinateur.
- **Pensé pour les équipes** — partagez un simple fichier HTML à vos collègues.
- **Sans dépendance IA** — aucun crédit, aucun abonnement, aucun modèle à appeler.
- **Règles explicites** — comportement reproductible, facile à faire évoluer.
- **Créé en quelques minutes** — décrivez vos règles, obtenez un outil immédiatement.

## Installer sur votre IA

Le skill suit le format ouvert **Agent Skills** (un dossier `SKILL.md` + ressources), commun à Claude, ChatGPT/Codex, Mistral et Gemini : **une seule source** s'installe partout. La Release fournit **deux fichiers identiques** — le `.skill` (à importer tel quel) et sa copie `.zip` (à décompresser pour les IA qui importent un « dossier ») :

| IA | À fournir | Où l'ajouter |
|---|---|---|
| **Claude** | le fichier `.skill` | [Réglages → Skills](https://claude.ai/new#settings/customize-skills) |
| **ChatGPT** | le fichier `.skill` | [chatgpt.com/skills](https://chatgpt.com/skills) |
| **Mistral** | le `.zip` décompressé (dossier) | [chat.mistral.ai/skills](https://chat.mistral.ai/skills?dialog=create) |
| **Gemini Entreprise** | le `.zip` / dossier | [docs.cloud.google.com — Skills](https://docs.cloud.google.com/gemini/enterprise/docs/skills?hl=fr) |

Les deux fichiers se téléchargent depuis la [dernière Release](https://github.com/YannCarbo/App-Autonome/releases/latest).


## Licence

Publié sous licence [MIT](LICENSE) : réutilisation, modification et redistribution libres, attribution conservée.
