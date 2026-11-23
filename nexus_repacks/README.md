# Nexus Repacks

**Correctif 2.1.1.** Choisir un `.torrent` reste disponible pendant un téléchargement ou une autre opération. Le choix prépare seulement le formulaire suivant et n’interrompt pas le transfert actif ; démarrer ce nouveau téléchargement attend toujours la fin ou l’arrêt de l’opération précédente et une confirmation.

**Version 2.1 — Téléchargements.** Tableau de bord avec barre visuelle, pourcentage décimal, volume reçu / total, vitesse, estimation du temps restant, connexions et seeders. Le journal sans séquences de couleur ANSI est replié par défaut. Pause conserve une reprise dans la session avec le même lien, le même dossier, le nom de fichier et le Referer. Annuler arrête le transfert ou l’analyse de ce téléchargement en conservant les fichiers partiels ; aucune suppression n’est effectuée. Après fermeture du lanceur, reprendre passe par le même lien et le même dossier, avec confirmation. Les données de progression restent en mémoire lors des changements d’onglet ; une taille encore inconnue n’affiche pas un faux pourcentage.

**Version 2.0 — Aurora.** Nouvelle navigation latérale, accent bleu néon pâle, visuels encadrés et nouvelle icône. Une intro originale dessine le logo à l’ouverture avant de révéler la bibliothèque ; cliquer permet de la passer. F8 conserve le choix Normal / Mouvements réduits / Auto. L’intro et les changements d’onglet peuvent être interrompus sans laisser une fenêtre transparente. Les effets coûteux sont préparés hors de la boucle d’interface ; l’horloge précise temporaire est libérée au repos. Le SHA-256 complet est visible après analyse et peut être copié par clic.

Lanceur Windows indépendant de NexusView, réservé aux repacks : bibliothèque avec visuels plein cadre, transitions et apparition progressive des options, téléchargements aria2 et analyse statique locale. F11 active le plein écran, Échap le quitte, les flèches changent le jeu sélectionné. Aucun réglage visuel de Windows n’est modifié.

Après un lancement réussi, Nexus se masque dans la zone de notification. Double-cliquer sur son icône ou choisir « Ouvrir Nexus Repacks » permet de le retrouver. « Quitter » ferme le lanceur. Un lancement bloqué ou échoué laisse la fenêtre ouverte.

La molette ne change plus le jeu sélectionné. Les flèches et le clic sur une tuile restent disponibles. Avant chaque lancement, un rappel invite à sauvegarder dans le jeu avant de le quitter. Aucune modification des mécanismes de sauvegarde des jeux n’est installée et Nexus ne prétend pas enregistrer un état en mémoire après fermeture.

La version 1.4 protège les actions contre les clics répétés, réutilise la fenêtre d’avertissement déjà ouverte et regroupe les changements d’onglet demandés pendant une transition. Les animations sont liées à leur écran : une vue fermée ne peut plus modifier la suivante. Cliquer sur l’onglet déjà actif ne reconstruit pas l’écran.

La version 1.4.1 corrige les faux positifs du moteur Python/Ren’Py : la présence de symboles de compilation dans une DLL ou de décodage et d’exécution dans des fonctions distinctes ne suffit plus à signaler un chargeur. Les anciens fichiers RPYC/RPYMC compressés en zlib sont désormais inspectés avec pickletools, sans désérialiser leurs objets. Les fonctions exécutables dangereuses référencées par un pickle restent bloquantes ; aucun dossier Ren’Py n’est globalement exempté.

## Exécutable et compilation

Depuis la racine de RemoteDesktop :

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm NexusRepacks.spec
```

Le fichier autonome est `dist/Nexus Repacks.exe`. Les données personnelles restent dans `%LOCALAPPDATA%/NexusRepacks` (bibliothèque JSON, réglages, images, rapports, quarantaine). Le moteur aria2 et sa provenance sont embarqués dans l’EXE. À la demande de l’utilisateur, le lanceur demande les droits administrateur via UAC à son ouverture.

Les jeux EXE et BAT/CMD ne doivent pas hériter de l’élévation du lanceur : lorsque Nexus est administrateur, ils sont créés avec le jeton non élevé du bureau interactif Windows. Si ce lancement standard est impossible, Nexus affiche une erreur et ne retente pas en administrateur. La demande UAC concerne Nexus, pas une autorisation générale d’élever les repacks.

## Bibliothèque

- `REPACKS/games` : détection de dossiers, choix d’un EXE de jeu en priorité sur les installateurs/crash handlers ; Run Me / Run / CMD détectés comme alternatives. Le menu ••• permet de choisir explicitement le lanceur.
- Epic Games et Microsoft/Xbox ne sont plus proposés ni détectés. Leurs anciennes entrées sont retirées de la bibliothèque Nexus ; aucun jeu de ces plateformes n’est supprimé du PC.
- Icônes : fichiers locaux usuels ou extraction statique des ressources ICO du PE, sans chargement ni exécution du fichier. Images personnalisées possibles.
- Descriptions : recherche Wikipédia avec le titre uniquement. Correspondance à vérifier ; les petits jeux n’ont pas toujours de fiche. Description et image peuvent être personnalisées. Aucun fichier de jeu, cookie, jeton ou mot de passe n’est envoyé. Le menu de recherche manuelle permet aussi de récupérer une image Wikipédia disponible.

## Téléchargements

La version 1.5 accepte aussi l’adresse d’une page web : **Analyser le lien** lit la page, propose les liens détectés et permet de vérifier celui choisi. Une confirmation distincte affiche l’hôte final, le fichier, la taille annoncée par le serveur et l’adresse complète. aria2 ne démarre qu’après **Confirmer et télécharger**. Annuler ne lance aucun transfert. Les liens directs et magnets passent eux aussi par cette confirmation.

L’inspection lit les en-têtes HTTP et au maximum 2 Mio de HTML/JSON ; elle n’exécute pas le JavaScript de la page. Elle reconnaît les liens relatifs, certains boutons à URL explicite, les redirections et les métadonnées de téléchargement. Elle n’importe aucun cookie de navigateur. Les pages nécessitant une connexion, un CAPTCHA ou du JavaScript complexe peuvent nécessiter de récupérer le lien manuellement. Les liens proposés ne constituent pas une validation de sécurité ou d’authenticité.

HTTP(S), fichier torrent local et magnet. Jusqu’à 16 connexions par serveur HTTP, 16 segments, taille minimale 1 Mio, reprise, pas de préallocation, cinq tentatives et aucune limite artificielle de débit. La vitesse réelle dépend du serveur, du disque, du réseau et des pairs. La pause conserve les fichiers ; reprendre le même lien avec le même nom de téléchargement réutilise les données. aria2 ne lance aucun hook et ignore les configurations externes ; son SHA-256 est vérifié avant chaque utilisation.

Les téléchargements arrivent dans `REPACKS/downloads/<nom>`. Une analyse statique suit la réussite du transfert. Aucun jeu ou installateur n’est exécuté à la fin. L’extraction ZIP est explicite et refuse les sorties de dossier, chemins absolus, flux ADS, liens, noms Windows réservés, doublons et écrasements. Après extraction, le dossier est analysé. RAR, 7z et ISO doivent être extraits séparément sans exécuter leur contenu, puis importés.

## Protection : portée exacte

Nexus Static est un filtre ciblé, **pas un antivirus complet, une sandbox ou une garantie de sécurité**. Il ne protège pas les lancements réalisés hors de Nexus, n’installe aucun pilote et ne surveille pas les processus après lancement. Un nouveau malware, une charge obfusquée, un format non couvert, une dépendance système ou un téléchargement effectué par le jeu peuvent lui échapper. Le verdict est « aucun indicateur détecté », jamais « fichier sûr ».

Les règles incluent les SHA-256 confirmés dans l’analyse du chargeur Ren’Py/ETW, la configuration Base64/XOR de cette campagne, les scripts des archives RPA-3/RPC2, les combinaisons de décodage et lancement discret, les DLL proxy ETW/Rust de la campagne, le vol de secrets navigateur/Discord en code lisible, les webhooks dans du code actif et la modification de Defender. Les noms setup.py / Setup.exe et la petite taille servent de contexte : ils ne déclenchent pas seuls un verdict malveillant. Les signatures sont locales, sans service de mise à jour automatique à ce stade.

Les archives Ren’Py sont parcourues comme des données avec pickletools : aucun pickle.load, exec, import de jeu ou chargement de DLL. Les EXE/DLL sont hachés et recherchés pour des indicateurs lisibles ; il ne s’agit pas d’une décompilation ou d’une émulation de toutes leurs instructions. Les limites de mémoire/décompression et les formats inconnus sont signalés. Une erreur, une analyse annulée ou un contenu actif non inspectable bloquent le lancement.

Les archives de distribution voisines d’un jeu déjà extrait ne sont pas des dépendances de ce lancement : elles sont inventoriées et explicitement signalées comme non inspectées. Leur contenu peut être contrôlé depuis le flux de téléchargement ; leurs fichiers extraits sont contrôlés au lancement. ZIP et RPA ont des budgets d’inspection pour éviter les bombes de décompression. Les caches, données et formats non couverts ne sont pas exhaustivement interprétés.

Une analyse réussie est conservée entre les ouvertures de Nexus dans un cache protégé par Windows DPAPI, lié à l’utilisateur courant. Le rapport JSON lisible seul ne permet pas de valider un jeu. Au clic « Jouer », les métadonnées des fichiers actifs inspectés et le SHA-256 du lanceur sont vérifiés. Les sauvegardes, journaux et archives de distribution inutilisées ne déclenchent plus de réanalyse. Aucun scan complet n’est automatiquement relancé après une analyse réussie : si le programme change, Nexus ouvre Protection et demande une analyse manuelle. Une cible différente ou un cache illisible nécessite aussi une première vérification valide. Le bouton « Analyser » reste disponible. Ce cache et la vérification de métadonnées ne constituent pas une protection contre un attaquant déjà actif sous le même compte ; ils ne fournissent pas un verrouillage système atomique.

Le bouton **Scan Windows** utilise Microsoft Defender uniquement sur demande et seulement s’il est actif. Il ne réactive ni ne reconfigure l’antivirus, et demande une analyse personnalisée sans remédiation automatique. Détection ou erreur bloque le jeu dans Nexus jusqu’à une analyse Windows ultérieure réussie. Il faut examiner les rapports et terminer le traitement dans son antivirus. Ne pas lancer ce contrôle en parallèle d’une analyse Malwarebytes en cours.

La quarantaine déplace le dossier complet, sans suppression définitive, vers `%LOCALAPPDATA%/NexusRepacks/quarantine/<id>` ; un JSON voisin conserve son emplacement d’origine. Elle est limitée aux sous-dossiers de `REPACKS/games`. Fermer les jeux avant de les déplacer. La restauration peut se faire manuellement à partir du JSON ; ne pas restaurer une détection sans l’avoir vérifiée.

## Validation

Les animations 1.5 utilisent une famille de courbes cohérente : sortie rapide, entrée progressive, dévoilement décalé des éléments, retour immédiat sur les boutons et interruption propre lors des changements d’onglet. F8 ou le bouton du pied de fenêtre alterne Auto / Normal / Mouvements réduits. Auto suit le réglage d’animations Windows ; le mode réduit retire les déplacements et raccourcit les fondus. Le moteur natif Tk ne garantit pas 60 images/s sur tous les PC.

À la demande de l’utilisateur, 19 skills ont été installés avec la CLI skills : les deux collections [web-animation-skills](https://github.com/iart-ai/web-animation-skills), [motion-design-skills](https://github.com/iart-ai/motion-design-skills), ainsi que [kinetic-typography](https://github.com/iart-ai/kinetic-typography-skills). Les instructions animation-principles, motion-art-direction, micro-interaction, accessible-animation, 60fps-animation, page-transition-animation et kinetic-typography ont guidé cette adaptation native. Les outils réservés à la vidéo ou au web ne sont pas embarqués dans l’EXE.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_nexus_repacks.py -v
.\.venv\Scripts\python.exe -m tests.nexus_download_integration
.\.venv\Scripts\python.exe -m nexus_repacks.app --smoke-test
.\.venv\Scripts\python.exe -m tests.nexus_motion_probe
.\.venv\Scripts\python.exe -m tests.nexus_navigation_stress
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_nexus_link_resolver.py -v
.\.venv\Scripts\python.exe -m tests.nexus_download_confirmation
```

Les tests utilisent des fixtures inoffensives, un serveur HTTP local et le binaire aria2 officiel vérifié. Ils ne lancent aucun jeu ni malware. La détection de fichiers connus renommés, la lecture de RPA sans désérialisation, les changements de dépendances, les refus d’archives dangereuses et les commandes sans shell sont couverts. Le cache protégé est testé après relecture, corruption et modification du programme ; ni les sauvegardes ni les journaux ne provoquent une réanalyse automatique. Le test d’interface mesure la progression des animations, l’apparition décalée des lignes, la navigation rapide et le masquage/retour depuis la zone de notification.

Sources techniques : [aria2 officiel](https://aria2.github.io/manual/en/html/aria2c.html), [publication aria2 1.37.0](https://github.com/aria2/aria2/releases/tag/release-1.37.0), [API MediaWiki](https://www.mediawiki.org/wiki/API:REST_API/Reference), [MpCmdRun Microsoft](https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus), [PyInstaller](https://pyinstaller.org/en/stable/usage.html).
