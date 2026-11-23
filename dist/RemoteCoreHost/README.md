# RemoteCore

Partage du bureau Windows vers un navigateur : DXGI/D3D11, H.264 NVENC, WebRTC,
audio système WASAPI/Opus, clavier/souris SendInput, validation locale obligatoire.

## Démarrer

1. Lancer `dist/RemoteCoreHost/RemoteCoreHost.exe` et conserver son dossier `_internal`.
2. Ouvrir **http://localhost:8080**, copier le code depuis la fenêtre de l’hôte.
3. Cliquer **Se connecter**, puis accepter sur le PC hôte.
4. Activer **Clavier et souris**, cliquer dans la vidéo ; **Échap** libère les commandes.
5. L’hôte peut révoquer les commandes, déconnecter ou fermer sa fenêtre pour arrêter le serveur.

Le son est coupé par défaut pour éviter une boucle audio en regardant ce même PC.
L’activer depuis un autre PC. Le code change à chaque lancement et reste en mémoire.
Journaux : `%LOCALAPPDATA%/RemoteCore/host.log`.

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
l’application portable dans `dist/RemoteCoreHost`. Python/Visual Studio ne sont pas
requis sur le PC destinataire. Le pilote NVIDIA doit prendre en charge NVENC ;
le repli logiciel libx264 est explicitement signalé dans l’interface.

Sans empaquetage : `.venv/Scripts/python.exe -m host.server --port 8080`.
`build/RemoteCore.exe` conserve le diagnostic C++ initial : l’application de partage
est **RemoteCoreHost.exe**.

## Modules

| Module | Fichiers et comportement |
| --- | --- |
| ScreenCapture | `src/ScreenCapture/Bridge.cpp`, DXGI, redimensionnement/rotation GPU ; `host/capture.py`, processus isolé et RAM partagée |
| VideoEncoder | `host/encoder.py`, FFmpeg/PyAV, H.264 NVENC vérifié par encodage/décodage, repli libx264, bitrate adapté par REMB |
| AudioCapture | `host/audio.py`, WASAPI loopback stéréo 48 kHz, file bornée et changement du périphérique par défaut ; Opus via aiortc |
| Network | `host/server.py`, signalisation aiohttp, WebRTC LAN, RTP/RTCP, DTLS/SRTP, canal SCTP de commandes |
| Input | `host/remote_input.py`, SendInput, suivi/relâchement des touches et boutons, watchdog, manette XInput facultative |
| Configuration | `PROFILES` dans `host/server.py`, choix de la résolution/cadence/débit dans le navigateur, une session simultanée |
| Diagnostics | `host/server.py`, `web/app.js`, FPS, débit, capture/encodage, CPU/RAM, utilisation NVENC si disponible, pertes et statistiques navigateur exportables |
| Interface hôte | `host/host_ui.py`, acceptation locale obligatoire, indicateur de partage, révocation et déconnexion |

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
vue mobile et déconnexion. Le substitut d’autorisation est limité au processus de test :
l’application distribuée n’a aucune option d’acceptation automatique. Le test SendInput
injecte dans sa propre fenêtre et restaure le curseur. Les résultats et captures du bureau
sont dans `test-results/`, ignoré par Git pour préserver la confidentialité.

Mesures du 16 novembre 2026, RTX 3050 Laptop, bureau **1920 × 1080**,
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
du bureau. Le profil 720p30 est le défaut ; 60/120 FPS et haute résolution restent des cibles.

Comparaison contrôlée 720p30 : lecture/réduction CPU moyenne **10,00 ms**, contre
**7,85 ms** avec réduction GPU avant lecture (environ 21,5 % de moins). La cadence
reste limitée à 30,1 FPS. Encodage moyen : 2,31 puis 2,48 ms, sans gain démontré.
Les mesures courtes varient avec la charge du bureau.

La latence affichée est le **RTT des commandes**, pas la latence écran-à-écran.
Audio et vidéo partagent une horloge de capture, mais la synchro perceptuelle et la
latence écran-à-écran n’ont pas été mesurées sur deux machines physiques.
HEVC, Internet, zéro copie GPU et qualification de tous les profils ne sont pas finalisés.
