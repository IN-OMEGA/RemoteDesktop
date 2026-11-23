# Ajouter tes jeux au catalogue

Modifie **catalog.json**, à côté de l’EXE. **catalog.example.json** contient trois exemples : téléchargement ZIP, archive 7z et lien magnet. Ils sont désactivés pour éviter de lancer de faux téléchargements. Les images d’exemple sont dans **catalog-assets**.

Le catalogue réel commence vide. Copie les objets souhaités de `catalog.example.json` dans le tableau `games` de `catalog.json`, remplace les valeurs puis mets `enabled` à `true`.

```json
{
  "version": 1,
  "games": [
    {
      "id": "mon-jeu",
      "title": "Nom du jeu",
      "description": "Description du jeu.\n\nDeuxième paragraphe.",
      "icon": "catalog-assets/mon-jeu-icon.png",
      "image": "catalog-assets/mon-jeu-cover.jpg",
      "download_url": "https://ton-hebergeur.com/mon-jeu.zip",
      "folder": "Mon Jeu",
      "filename": "mon-jeu.zip",
      "referrer": "",
      "genre": "Adventure",
      "size": "8.5 GB",
      "enabled": true
    }
  ]
}
```

Les adresses ci-dessus sont des exemples à remplacer.

| Champ | Utilisation |
| --- | --- |
| `version` | Version du format JSON : garde `1`. Ce n’est pas la version de l’EXE. |
| `games` | Tableau des jeux. Ajoute une virgule entre les objets, sans virgule après le dernier. |
| `id` | Identifiant unique : lettres, chiffres, tirets et underscores. |
| `title` | Nom affiché. Obligatoire. |
| `description` | Description complète. Obligatoire. `\n` crée un retour à la ligne. |
| `icon` | Petite icône : chemin relatif ou adresse HTTP(S). Facultatif. |
| `image` | Grande image : chemin relatif ou adresse HTTP(S). Facultatif. |
| `download_url` | **Lien direct vers le fichier**, ou lien magnet complet. Obligatoire si le jeu est activé. |
| `folder` | Sous-dossier créé dans `REPACKS/downloads`. Facultatif ; utilise `id` s’il est absent. |
| `filename` | Nom du fichier téléchargé par HTTP(S). Facultatif ; le serveur choisit s’il est absent. |
| `referrer` | Adresse de la page d’origine, uniquement si l’hébergeur l’exige. Facultatif. |
| `genre` | Genre affiché et utilisable dans la recherche. Facultatif. |
| `size` | Texte de taille affiché, par exemple `8.5 GB`. Facultatif ; ne remplace pas la taille réelle du transfert. |
| `enabled` | `true` pour autoriser Download ; `false` pour afficher le jeu comme indisponible. Facultatif, `true` par défaut. |

Pour les images locales, utilise le dossier `catalog-assets/` avec des fichiers PNG, JPG, WebP ou ICO. Les sous-dossiers sont possibles. N’utilise pas de chemin absolu comme `C:\...`, ni de `../`. Les images doivent faire moins de 8 Mio et 20 millions de pixels. Une image manquante ou inaccessible dans l’interface affiche une vignette avec l’initiale du jeu ; la publication refuse une image locale référencée qui manque.

Un lien de page de jeu, CAPTCHA ou connexion ne suffit pas pour Download : récupère le lien direct de l’archive. Les pages web restent utilisables par le parcours manuel dans Downloads. Le catalogue démarre le transfert au premier clic sur Download, puis conserve l’analyse à la fin. Il ne lance pas automatiquement un installateur et n’exécute aucun jeu téléchargé.

## Voir puis partager tes changements

1. Enregistre `catalog.json` et tes images locales.
2. Dans l’EXE, ouvre **Catalog**, puis clique **Reload**. Les erreurs de JSON sont affichées sans planter l’application.
3. Quand tout est prêt, lance **Publish Update.bat**. La version suivante est calculée automatiquement, sans numéro à saisir.

Le script valide le JSON, copie les images référencées, puis les intègre à l’EXE avant de publier la mise à jour. Les autres utilisateurs reçoivent ainsi ton catalogue avec la nouvelle version. Ils n’ont besoin que de l’EXE.

Le catalogue à côté de ton EXE est une surcharge locale réservée à l’édition. Une personne qui place son propre `catalog.json` à côté de son EXE verra ce fichier prioritairement ; une mise à jour de l’EXE ne l’écrasera pas. Pour distribuer la version intégrée automatiquement, partage uniquement l’EXE.
