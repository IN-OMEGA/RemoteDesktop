# Nexus View

**Version 0.4.3 :** presse-papiers texte partagé dans les deux sens, mot de passe obligatoire en plus du code Nexus, destinataires configurés dans l’exe, lecteur iPhone avec reprise automatique, souris virtuelle et clavier rétroéclairé. Voir [Qualité et performances](docs/QUALITY.md) et [comparaison technique](docs/REMOTE_TECHNOLOGY.md).

Partage du bureau Windows vers un navigateur : DXGI/D3D11, H.264 NVENC, WebRTC,
audio système WASAPI/Opus, clavier/souris SendInput, connexion avec code et mot de passe valides.

## Démarrer

1. Lancer `dist/NexusView/NexusView.exe` et conserver son dossier `_internal`.
2. Ouvrir **http://localhost:8080**, copier le code depuis la fenêtre de l’hôte.
   Depuis un autre appareil, ouvrir le **lien Cloudflare** affiché dans **Connexion**.
3. Cliquer **Se connecter** : un code valide ouvre directement le bureau, sans confirmation sur le PC hôte.
4. Toucher ou cliquer dans le bureau pour activer les commandes. Sur PC, autoriser la capture clavier en plein écran. **Échap maintenu 2 secondes** ou **3 pressions en 1,4 seconde** libèrent les commandes ; un Échap court est transmis au PC distant.
5. La croix et la réduction placent l’application dans la zone de notification ; le partage continue.
   Pour arrêter le serveur, choisir **Quitter Nexus View** dans le menu de l’icône ou dans la fenêtre.

Le son est coupé par défaut pour éviter une boucle audio en regardant ce même PC.
L’activer depuis un autre PC. Le code est conservé après redémarrage, chiffré avec Windows DPAPI
dans `%LOCALAPPDATA%/NexusView/connection-code.bin` pour ce compte Windows. Seul le bouton
**Connexion → Générer un nouveau code** le remplace ; l’ancien code et la session sont alors révoqués.
Journaux : `%LOCALAPPDATA%/NexusView/host.log`.

### Connexion et outils plein écran

Une connexion explicitement démarrée par une personne ouvre Chrome sur le PC contrôlé
et règle son écran principal à 125 %, sans dialogue Nexus supplémentaire. Ces actions
ne sont pas lancées au démarrage de l’exe ni lors des vérifications automatisées.
L’échelle présente avant la session est mémorisée puis restaurée à la déconnexion,
au remplacement de la session ou à la fermeture normale de l’application. Les fenêtres
Chrome/CMD ne sont pas fermées automatiquement, afin de conserver le travail ouvert.
Les applications qui ignorent les changements DPI à chaud peuvent nécessiter leur propre
redémarrage. Un échec du réglage Windows apparaît dans les diagnostics.

La barre d’icônes à droite du plein écran propose capture PNG, enregistrement vidéo,
CMD et Google Classroom (dans Chrome du PC distant). Capture et enregistrement proposent
écran entier ou sélection d’une zone. Les fichiers sont téléchargés sur l’appareil qui
ouvre le site, à la résolution vidéo reçue. Cliquer de nouveau sur Enregistrer pour
arrêter et télécharger. Le format MP4 ou WebM dépend du navigateur ; le son est inclus
si la piste reçue peut être capturée, sinon un message indique l’enregistrement sans son.
La capture ne contient pas la barre d’outils.

La flèche du bas masque complètement la barre. Après 3 secondes de souris dans le coin
inférieur droit, une poignée permet de la réafficher. Les touches Échap et la sortie
tactile restent disponibles lorsque la barre est cachée.

### E-mail automatique

Le fichier `.env` privé contient `mailto_email` (compte Gmail d’envoi uniquement)
et `mailto_key` (clé d’application Gmail). Au premier chargement, ces paramètres sont
enregistrés sous forme chiffrée par Windows DPAPI dans
`%LOCALAPPDATA%/NexusView/mail-settings.bin`. Ni `.env` ni la clé SMTP ne sont intégrés
aux ressources du site ou à l’exe. Pour installer sur un autre compte Windows, placer
son propre `.env` à côté de l’exe. Une variable `NEXUS_ENV_FILE` peut aussi indiquer son chemin.

Dans l’exe, ouvrir **Connexion → À qui envoyer les nouveaux liens ?**, saisir une ou
plusieurs adresses (une par ligne, ou séparées par virgules/points-virgules) et cliquer
**Enregistrer les destinataires**. Aucun destinataire n’est deviné depuis `.env`.
La liste est conservée chiffrée avec DPAPI, les doublons sont supprimés, et une liste
vide désactive l’envoi. À la mise à jour depuis 0.4.0, l’ancienne destination unique
est effacée afin de demander explicitement cette liste.

Chaque nouveau lien actif et vérifié déclenche un message individuel à chaque adresse
enregistrée, avec le lien et le **code Nexus**. Les destinataires ne voient pas les autres
adresses. Aucun mot de passe Windows n’est lu ou envoyé. Le statut indique les envois
réussis ou refusés ; **Envoyer le lien actuel** permet un envoi manuel. Le code reste
conservé d’un lien au suivant. `smtp_host` et `smtp_port` sont facultatifs ; par défaut,
Gmail utilise `smtp.gmail.com:465` avec TLS vérifié.

### iPhone : souris et clavier

Le pavé tactile est sélectionné par défaut : un glissement déplace la flèche virtuelle
et le pointeur Windows, sans déplacer le clic directement sous le doigt. Un toucher
clique à la position du pointeur ; deux doigts défilent et un appui long permet le glisser.
L’icône clavier de la barre droite ouvre **Nexus Keys**, avec police Space Grotesk locale,
rétroéclairage, dispositions FR/EN, accents/symboles, Ctrl/Alt/Win et flèches.
Le bouton du clavier du téléphone reste disponible pour la saisie native et les méthodes
de composition iOS. Les captures/enregistrements ne contiennent pas le clavier.

Sur iPhone, Baseline/720p30 reste imposé même si la case de compatibilité est décochée.
Le lecteur évite les sauts de lecture répétés et peut se reconstruire avec quelques
secondes de fragments récents si le décodage se fige. Le contrôle reste sur sa session.

### Souris, tactile et clavier

Sur iPhone, le lecteur reste dans la page : une touche clique, deux doigts défilent,
une touche à deux doigts fait un clic droit, trois doigts un clic milieu. Maintenir
450 ms puis glisser permet le glisser-déposer. Choisir **Pavé tactile** pour déplacer
le curseur par glissement plutôt que pointer directement. La barre contient le clavier
iOS, Ctrl, Alt, Win, Tab, Esc et des raccourcis explicites. Le texte Unicode, y compris
accents et emoji, passe par SendInput. Le plein écran conserve les commandes du site.

Sur Chrome/Edge en HTTPS (ou localhost), le clic dans le bureau demande le plein écran
et le verrouillage de toutes les touches autorisées : Ctrl+W est transmis au PC distant.
Le navigateur peut demander une permission. Sans Keyboard Lock, certains raccourcis
restent interceptés localement ; utiliser les boutons de raccourcis dans la barre.
Les combinaisons réservées au système, notamment Ctrl+Alt+Suppr, ne sont pas capturées.
L’aide Nexus apparaît une seule fois par navigateur et réapparaît après triple Échap.
Les notifications natives du navigateur restent gérées par celui-ci.

Le plein écran masque toutes les barres, boutons et mesures Nexus. Il conserve les
commandes : Échap maintenu 2 s ou trois pressions pour sortir ; sur iPhone, maintenir
trois doigts immobiles pendant une seconde. Pour retirer aussi les barres Safari sur
iPhone, ajouter le site à l’écran d’accueil et l’ouvrir comme application web.

### Internet avec Cloudflare Try

Lancer l’exe : le connecteur Cloudflare inclus démarre automatiquement en arrière-plan.
Dans **Connexion**, copier le lien HTTPS et le partager avec le code habituel.
Chaque relancement de l’exe crée un nouveau lien. **Nouveau lien Internet** termine
la session en cours et remplace le lien sans changer le code. La zone de notification
permet aussi de copier ou renouveler ce lien. Fermer normalement l’application arrête
son connecteur et invalide l’adresse. Aucun compte ngrok ou Cloudflare n’est requis.

Le navigateur tente d’abord WebRTC direct
avec le serveur STUN public Cloudflare. Si la connexion directe ne s’établit pas,
le flux revient automatiquement au tunnel WebSocket HTTPS. Le repli reste utilisable
sans port UDP ouvert ou service TURN. Le code est envoyé dans
le premier message authentifié, jamais dans l’URL.

Le tunnel utilise H.264/AAC en MP4 fragmenté : jusqu’à **1080p60 / 20 Mb/s** sur ordinateur,
**720p30 / 6 Mb/s** sur iPhone. Safari nécessite **iOS 17.1 ou supérieur** pour ManagedMediaSource.
La vidéo démarre automatiquement ; le son reste soumis aux permissions de lecture du navigateur.
La latence TCP peut dépasser celle du WebRTC local et dépend du débit montant et du tunnel.
Une nouvelle connexion avec le bon code termine la session précédente, même en cours
d’initialisation. Un ancien client ne peut pas déconnecter le nouveau.

Pour les NAT restrictifs, fournir son propre relais TURN dans la variable d’environnement
`NEXUS_ICE_SERVERS`, au format JSON de configuration ICE (urls, username, credential).
Exemple de STUN seul : `[{"urls":"stun:stun.cloudflare.com:3478"}]` ; `[]` force le repli
HTTPS sur les liens publics. Aucun compte TURN ni infrastructure privée n’est créé.

Cloudflare Try reste un service temporaire sans garantie de disponibilité ; son URL
ne doit pas être considérée comme une adresse permanente. `--no-tunnel` ou
`scripts/start.ps1 -LocalOnly` permet un démarrage sans accès Internet public.
Le connecteur cloudflared 2026.11.1 est livré dans `_internal/tools`, avec sa licence.
La compilation vérifie son SHA-256 avant empaquetage. Les paramètres d’un autre
connecteur Cloudflare installé sur le PC ne sont pas modifiés.

### Réseau local

`scripts/start.ps1 -LAN` écoute sur le LAN : ouvrir `http://IP-DU-PC-HOTE:8080`
depuis le PC qui contrôle. Une autorisation du pare-feu Windows pour le réseau privé
peut être nécessaire. Aucune règle de pare-feu ou redirection de port n’est créée.
La signalisation HTTP est destinée au LAN de confiance ; elle n’utilise pas TLS.
Les médias et commandes WebRTC utilisent DTLS/SRTP. Aucun relais Internet n’est utilisé.

## Construire

Windows 11, Python 3.12, Visual Studio C++ x64, Windows SDK et CMake :

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Package
```

Le script compile la DLL native, installe les dépendances dans `.venv` et produit
l’application portable dans `dist/NexusView`. Python/Visual Studio ne sont pas
requis sur le PC destinataire. Le pilote NVIDIA doit prendre en charge NVENC ;
le repli logiciel libx264 est explicitement signalé dans l’interface.

Sans empaquetage : `.venv/Scripts/python.exe -m host.server --port 8080`.
`build/RemoteCore.exe` conserve le diagnostic C++ initial : l’application de partage
est **NexusView.exe**.

## Modules

| Module | Fichiers et comportement |
| --- | --- |
| ScreenCapture | `src/ScreenCapture/Bridge.cpp`, DXGI, redimensionnement/rotation GPU ; `host/capture.py`, processus isolé et RAM partagée |
| VideoEncoder | `host/encoder.py`, FFmpeg/PyAV, H.264 NVENC vérifié par encodage/décodage, repli libx264, bitrate adapté par REMB |
| AudioCapture | `host/audio.py`, WASAPI loopback stéréo 48 kHz, file bornée et changement du périphérique par défaut ; Opus via aiortc |
| Network | `host/server.py`, signalisation aiohttp, WebRTC LAN, RTP/RTCP, DTLS/SRTP, canal SCTP de commandes |
| Input | `host/remote_input.py`, SendInput, suivi/relâchement des touches et boutons, watchdog, manette XInput facultative |
| Configuration | `host/configuration.py` et `host/code_store.py`, profils vidéo et code persistant protégé par DPAPI |
| Diagnostics | `host/server.py`, `web/app.js`, FPS, débit, capture/encodage, CPU/RAM, utilisation NVENC si disponible, pertes et statistiques navigateur exportables |
| Interface hôte | `host/host_ui.py`, autorisation des connexions par code, indicateur de partage, révocation et déconnexion |

Sur ce portable Optimus, initialiser CUDA/NVENC avant DXGI empêche Desktop Duplication
dans le même processus. La capture est donc isolée. Après traitement GPU, les images
passent par une lecture GPU → RAM partagée → NVENC : **ce pipeline n’est pas zéro copie**.
La RAM partagée est lue sans copie NumPy supplémentaire. Les images proviennent réellement
du bureau ; la dernière est répétée lorsque le bureau ne change pas.

Les ressources DXGI sont recréées après perte d’accès/changement de mode avec tentatives
bornées. Le bureau verrouillé/protégé reste inaccessible. SendInput ne commande pas une
fenêtre élevée depuis un processus non élevé, ni l’écran UAC. L’écran principal est capturé.
La sélection d’autres écrans et la composition du curseur matériel restent à implémenter.
La rotation est traitée en shader mais n’a pas été testée sur un écran physiquement pivoté.

## Manette

La bibliothèque `vgamepad` est incluse ; axes/boutons/gâchettes sont transmis vers une
Xbox 360 virtuelle via ViGEm. Le pilote n’est pas actif sur ce PC : fonctionnalité non validée.
Installation avec élévation Windows :

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-gamepad.ps1
```

Le script vérifie la signature et le SHA-256 de l’installeur officiel et ne force aucun
redémarrage. Relancer l’hôte après installation. Le navigateur doit utiliser localhost
ou HTTPS pour la Gamepad API. Source : https://github.com/yannbouteiller/vgamepad

## Tests et mesures

```powershell
.venv/Scripts/python.exe -m pip install playwright
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe tests/integration.py
.venv/Scripts/python.exe tests/input_probe.py
.venv/Scripts/python.exe tests/benchmark.py
.venv/Scripts/python.exe tests/benchmark.py --compare
```

L’intégration vérifie refus d’authentification/origine, refus de l’hôte, réception réelle
H.264, réception d’un bref signal réellement joué puis capturé par WASAPI, repli libx264,
vue mobile et déconnexion. La politique de connexion réelle est testée : code valide
sans dialogue, mauvais code refusé et connexions bloquées lorsque l’hôte les désactive. Le test SendInput
injecte dans sa propre fenêtre et restaure le curseur. Les résultats et captures du bureau
sont dans `test-results/`, ignoré par Git pour préserver la confidentialité.

Mesures initiales de la version 0.1 (16 novembre 2026), RTX 3050 Laptop, bureau **1920 × 1080**,
pipeline capture + encodage après démarrage, essais de 4 secondes :

| Cible | Résolution réellement produite | FPS mesurés |
| --- | --- | --- |
| 720p30 | 1280 × 720 | 30,1 |
| 1080p60 | 1920 × 1080 | 53,3 |
| 1080p120 | 1920 × 1080 | 47,7 |
| 1440p60 | plafonnée à 1080p | 57,8 ; 1440p non validé |
| 4K60 | plafonnée à 1080p | 56,1 ; 4K non validé |
| 4K120 | plafonnée à 1080p | 56,2 ; 4K/120 non validé |

Dans Chromium local : vidéo 720p décodée autour de 30 FPS, sans perte de paquets RTP
dans l’essai court. Ce ne sont pas des garanties en jeu ou sur un réseau distant.
Les profils sont des enveloppes maximales : aucun agrandissement artificiel au-delà
du bureau. Dans la version 0.1, le profil 720p30 est le défaut ; 60/120 FPS et haute résolution restent des cibles.

Comparaison contrôlée 720p30 : lecture/réduction CPU moyenne **10,00 ms**, contre
**7,85 ms** avec réduction GPU avant lecture (environ 21,5 % de moins). La cadence
reste limitée à 30,1 FPS. Encodage moyen : 2,31 puis 2,48 ms, sans gain démontré.
Les mesures courtes varient avec la charge du bureau.

La latence affichée est le **RTT des commandes**, pas la latence écran-à-écran.
Audio et vidéo partagent une horloge de capture, mais la synchro perceptuelle et la
latence écran-à-écran n’ont pas été mesurées sur deux machines physiques.
HEVC, zéro copie GPU et qualification de tous les profils ne sont pas finalisés.
Le tunnel Internet ngrok est disponible depuis la version 0.2.5 ; les profils 4K/120
restent limités au transport WebRTC direct et aux capacités réelles du matériel.
# Mot de passe obligatoire

La connexion exige le code Nexus **et** un mot de passe. Le formulaire obtient un accès temporaire après vérification des deux ; toutes les API et les connexions vidéo/commandes exigent cet accès. Les tentatives sont limitées. Le mot de passe n’est ni inclus dans les e-mails ni intégré aux fichiers distribués. Son empreinte scrypt salée est protégée avec Windows DPAPI dans `%LOCALAPPDATA%\NexusView\remote-password.bin`. Sans configuration, l’accès distant reste bloqué. Les accès temporaires expirent après huit heures et sont supprimés au redémarrage de l’hôte.


## Presse-papiers partagé

Le texte est synchronisé dans les deux sens pendant la session authentifiée, lorsque la page est active. Autorisez le presse-papiers dans Chrome/Edge. Ctrl+C/Ctrl+X copient depuis le PC distant et Ctrl+V transmet le texte local avant de coller. Une icône presse-papiers dans la barre droite propose aussi Copier depuis le PC et Coller sur le PC. Sur Safari/iPhone, les restrictions du navigateur peuvent imposer ce geste explicite. Texte Unicode uniquement, 32 Ko maximum ; les images et fichiers ne sont pas transférés. Le contenu reste en mémoire, sans historique Nexus, sans journalisation et sans inclusion dans les e-mails. La synchronisation s’arrête après la déconnexion.
