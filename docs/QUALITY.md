# Nexus View 0.2 — qualité et performances

## Choisir la qualité

Dans le navigateur, **Premium Auto** demande la résolution native du bureau,
jusqu’à 3840 × 2160, une cadence cible de 120 FPS et un plafond de 60 Mb/s.
La résolution réellement transmise et les FPS reçus sont toujours affichés.
Il n’y a aucun agrandissement artificiel d’un bureau 1080p en « 4K ».

Pour ce PC, le réglage conseillé pour privilégier les détails et une cadence régulière
est **1080p qualité / cible 60 FPS**, avec **25 Mb/s**. Le menu « Qualité et bande
passante » permet de choisir de 1 à 100 Mb/s et de modifier le réglage NVENC :

| Mode | Réglage réel |
| --- | --- |
| Performance | NVENC P1, délai de réorganisation nul |
| Équilibré | NVENC P3, quantification adaptative spatiale |
| Premium | NVENC P4, quantification adaptative spatiale |

La sélection de profil H.264 suit les capacités annoncées par le navigateur :
High en priorité, Main ensuite, Baseline en dernier recours. Aucun profil n’est
annoncé comme utilisé avant sa négociation. Les images restent en 8 bits / 4:2:0.
Le débit baisse lorsque le retour réseau WebRTC signale une bande passante insuffisante.
Augmenter le plafond ne garantit pas de meilleurs FPS sur un réseau saturé.

## Obtenir de la vraie 4K

L’écran principal détecté sur ce poste est **1920 × 1080 à 144 Hz**.
Pour capturer du 3840 × 2160, Windows doit réellement disposer d’un affichage 4K,
physique ou virtuel. L’hôte propose un bouton ouvrant les paramètres d’affichage
Windows ; aucun mode non pris en charge n’est imposé et aucun pilote d’écran virtuel
n’est installé. Une fois un bureau 4K disponible, sélectionner 4K60 et vérifier
la résolution envoyée, le débit, les pertes et la cadence reçue avant de viser 120 FPS.
La 4K native et la 4K120 ne sont pas validées sur le matériel actuel.

## Optimisations réelles

- Redimensionnement et conversion BGRA → NV12 sur le processeur vidéo D3D11 lorsque pris en charge.
- Lecture de 1,5 octet/pixel en NV12 au lieu de 4 en BGRA : 62,5 % de données brutes en moins par image.
- Deux emplacements de RAM partagée : acquisition de N+1 pendant l’encodage de N, sans copie NumPy ni file d’images anciennes.
- Ressources et file bornées ; dernière image réelle répétée sur bureau statique.
- Horloge Windows à résolution fine uniquement pendant la session, restaurée à l’arrêt.
- Demande de tampon de lecture minimal au navigateur lorsqu’il propose ce réglage.

Le chemin Optimus conserve une lecture GPU → RAM et un transfert RAM → GPU NVIDIA :
il **n’est pas zéro copie GPU**. Si la conversion NV12 n’est pas disponible, le chemin
BGRA existant est conservé et indiqué dans les diagnostics.

## Résultats observés

Essais courts sur ce poste, RTX 3050 Laptop, écran 1080p/144 Hz, novembre 2026 :

| Mesure | Résultat observé |
| --- | --- |
| Pipeline 1080p qualité / cible 60 | environ 60 FPS après démarrage |
| Pipeline Premium Auto / cible 120 | environ 77 FPS à la résolution native 1080p |
| Pipeline 1080p fluidité / cible 120 | environ 80 FPS |
| Comparaison BGRA CPU → NV12 GPU, même cible 1080p120 | 66,5 → 77,3 FPS sur deux essais de 4 s |
| Exécutable distribué, navigateur Chromium local via adresse LAN, 1080p qualité | environ 49 FPS reçus, aucune perte RTP ni image ignorée au décodage lors du test |
| Dernier essai exécutable Premium Auto, H.264 Main, 1080p natif | 55,6 FPS reçus en moyenne sur 6 secondes, cadence variable, zéro perte RTP |

Les valeurs du pipeline ne sont pas celles du rendu navigateur. Le dernier essai fait
tourner capture, encodage et navigateur sur le même PC. Les performances sur un autre
appareil physique restent à mesurer ; 120 FPS et une qualité comparable à un service
commercial ne sont pas garantis. Les résultats bruts sont dans `test-results/`.

La latence des commandes affichée est leur aller-retour. Ce n’est pas une mesure de
latence écran-à-écran. Les valeurs capture, encodage, débit et FPS sont mesurées séparément.

## Connexion depuis un autre appareil

Nexus View écoute maintenant sur le LAN par défaut. Dans l’exécutable, ouvrir
**Connexion**, copier l’adresse `http://IP-DU-PC:8080` et l’utiliser sur l’autre appareil
du même réseau. `localhost` sur un téléphone désigne le téléphone, pas le PC.
Le réseau doit autoriser les connexions privées à Nexus View dans le pare-feu Windows.

Le contrôle d’origine a été corrigé pour les alias LAN et proxys : l’API vérifie
d’abord le code secret Bearer explicite. Elle ne repose sur aucun cookie d’authentification
automatiquement envoyé et n’ouvre aucun CORS générique. Depuis la version 0.2.1,
un code valide ouvre directement la session, sans dialogue de confirmation sur l’hôte.
L’hôte peut désactiver les connexions par code, révoquer les commandes ou déconnecter.

## Interface

Le tableau de bord et les icônes Nexus View reprennent le langage visuel et l’emblème
du projet GuestManager, à la demande de l’utilisateur. GuestManager n’a pas été modifié.
Exécutable : `dist/NexusView/NexusView.exe` ; conserver son dossier `_internal`.

Depuis la version 0.2.2, le code reste identique après fermeture, redémarrage ou mise à jour.
Il est enregistré chiffré avec Windows DPAPI pour le compte Windows courant. Le bouton
**Connexion → Générer un nouveau code** le remplace et révoque immédiatement l’ancien code
ainsi que la session active. Un fichier de code illisible n’est jamais remplacé automatiquement.

La croix et le bouton de réduction masquent la fenêtre dans la zone de notification, sans arrêter
le serveur. Double-cliquer sur l’icône pour rouvrir ; son menu propose **Déconnecter** et
**Quitter Nexus View**. Un badge rouge et l’infobulle signalent le partage actif.
L’option `--tray` permet de démarrer directement dans la zone de notification.

## iPhone / Safari — version 0.2.3

Le mode de compatibilité est activé automatiquement sur iPhone et iPad : H.264
Constrained Baseline, niveau 3.1 réellement vérifié dans le SPS NVENC, 720p/30 FPS maximum
et débit plafonné à 8 Mb/s. Les autres appareils conservent leurs profils habituels.

La vidéo reste muette et en ligne (`muted`, `playsinline`), séparée du flux audio.
La connexion déclenche la lecture et fait défiler le bureau à l’écran sur iPhone.
Les événements média et les retours au premier plan permettent de reprendre la lecture,
sans bouton « Afficher le bureau ». Le son demandé est lancé automatiquement séparément.
Les restrictions d’iOS peuvent néanmoins retarder la lecture automatique ; elles ne peuvent
pas être contournées de façon garantie par le site.

Les commandes tactiles sont accessibles dans la version mobile et un toucher déplace
le curseur avant de cliquer. Le plein écran utilise l’API vidéo native lorsqu’il n’existe
pas d’API plein écran DOM.

Vérification : encodage/décodage réel sous Chromium avec configuration iPhone, réception
audio, interface et reprise automatique sous WebKit Windows. Aucun test sur un iPhone
physique n’a été réalisé depuis ce poste.
Référence : [politiques vidéo WebKit](https://webkit.org/blog/6784/).

## Reprise réseau — version 0.2.4

Une déconnexion temporaire laisse maintenant 12 secondes de reprise avant fermeture.
Le navigateur ne ferme plus une session existante simplement parce que le callback
« connecté » de l’hôte n’a pas encore terminé. Les commandes sont relâchées pendant
une interruption réseau.

Sur une connexion LAN directe authentifiée, les candidats ICE mDNS sont conservés et
complétés par une tentative vers l’adresse privée observée sur la connexion HTTP, avec
le port annoncé dans le SDP. Cela permet une tentative directe lorsque Windows ne
résout pas les noms `.local` de Safari. Ce mécanisme ne s’applique pas aux proxys,
adresses publiques ou loopback et n’utilise aucun serveur STUN public.
Il ne remplace pas TURN pour une connexion Internet : ouvrir l’adresse LAN du PC depuis
le même Wi-Fi, plutôt qu’un lien d’aperçu public.

Les états de connexion, ICE et lecture du navigateur sont consignés dans le journal
local de l’hôte pour permettre de diagnostiquer un essai physique, sans enregistrer le code.

## ngrok et sessions — version 0.2.5

Les liens publics ou requêtes passant par un proxy utilisent automatiquement le même
tunnel HTTPS pour les médias et les commandes, via WebSocket. Le flux MP4 fragmenté
contient la vidéo H.264 Baseline (NVENC avec repli x264) et le son système AAC 48 kHz.
Des fragments de 100 ms conservent les durées des images et évitent les pertes de
décodage constatées avec un fragment par image. L’envoi attend le réseau et les files
du navigateur sont bornées. Le navigateur rejoint le direct si son retard dépasse 1,2 s.

Le transport TCP est limité à 1920 × 1080, 30 FPS et 12 Mb/s sur ordinateur ;
1280 × 720, 30 FPS et 6 Mb/s sur iPhone. Il ne garantit pas la latence du WebRTC LAN.
Safari iPhone utilise ManagedMediaSource (iOS 17.1 minimum), avec AirPlay désactivé.
La vidéo muette et l’élément audio ont des lecteurs indépendants avec horloge commune.
Le son reste soumis à la politique de lecture automatique du navigateur.

`tests/tunnel_integration.py` vérifie une vraie capture DXGI/NVENC et le décodage vidéo
et audio dans Chromium, le repli x264 sans audio, le remplacement d’une session,
le refus d’un mauvais code sans déconnexion et l’impossibilité pour un ancien client
de fermer la nouvelle session. L’essai 720p30 a reçu 136 images en environ 4,5 secondes.
`tests/session_gate_probe.py` vérifie aussi le remplacement d’une initialisation en attente.
Les essais avec configuration iPhone ne remplacent pas un test sur appareil physique.

Exécutable 0.2.5 vérifié à travers le tunnel ngrok HTTPS actif : 1920 × 1080 à
29,2 FPS reçus pendant 6 secondes ; configuration navigateur iPhone, 1280 × 720
à 27,9 FPS avec lecture audio. Il s’agit d’un trajet réel via ngrok depuis ce PC,
pas d’un essai entre deux appareils physiques. Mesures dans
`test-results/ngrok-desktop.json` et `test-results/ngrok-mobile.json` (ignorés par Git).

Références : [WebSockets ngrok](https://ngrok.com/docs/gateway/endpoints/http),
[Managed Media Source Apple](https://developer.apple.com/videos/play/wwdc2023/10122/).

## Commandes par appareil — version 0.2.6

Le premier geste sur le bureau active les commandes. Sur iPhone, le mode Toucher direct
convertit le toucher en souris Windows ; le mode Pavé tactile déplace un curseur relatif.
Ce mode ne prétend pas injecter des contacts tactiles Windows natifs. Clic droit à deux
doigts, clic milieu à trois doigts, défilement à deux doigts, appui long puis déplacement
pour glisser-déposer. Le clavier logiciel transmet le texte en Unicode UTF-16 avec
SendInput ; les touches spéciales et modificateurs sont accessibles dans la barre.

Le plein écran mobile reste une vue de la page, sans lecteur vidéo natif qui empêcherait
les interactions. Sur PC compatible, Fullscreen et Keyboard Lock capturent les touches
autorisées, dont Ctrl+W. Autorisation du navigateur et contexte sécurisé nécessaires.
L’aide Nexus ne se répète pas à chaque clic. Triple Échap la réaffiche et libère le clavier ;
un maintien de 2 s libère aussi les commandes. Un Échap court reste utilisable à distance.
Les pertes de focus et les interruptions libèrent les touches et boutons. Un keepalive
tant que la surface de saisie garde le focus évite de perdre les modificateurs maintenus.

Vérifications : `tests/browser_input_probe.py` pour les gestes via événements tactiles
Chromium, clavier Unicode, raccourcis et sortie Échap ; `tests/native_keyboard_probe.py`
injecte réellement Ctrl+W depuis Windows dans une fenêtre Chromium de test, vérifie que
l’onglet contrôleur reste ouvert et que le raccourci distant est émis. Les commandes de ce
test sont enregistrées sans agir sur les fenêtres de l’utilisateur. `tests/input_probe.py`
vérifie SendInput, Unicode et répétition dans sa propre fenêtre. WebKit Windows vérifie
la vue iPhone et le plein écran interactif ; aucun iPhone physique n’est accessible ici.

Approches consultées : [AnyDesk iOS](https://support.anydesk.com/docs/anydesk-for-ios-ipados-tvos),
[Chrome Remote Desktop iOS](https://support.google.com/chrome/answer/1649523?co=GENIE.Platform%3DiOS&hl=en-BW),
[Keyboard Lock Chrome](https://developer.chrome.com/docs/capabilities/web-apis/keyboard-lock).

## Plein écran et délai — version 0.2.7

Le plein écran n’affiche que le bureau : aucune barre Nexus, bouton, mesure ou message
« Commandes actives ». Les touches de sortie restent inchangées ; un maintien de trois
doigts pendant 1 s sort aussi de la vue mobile. Le manifeste et les métadonnées iOS
permettent l’ouverture depuis l’écran d’accueil sans l’interface Safari.

Les commandes du tunnel ont leur propre WebSocket, authentifié avec le code et limité
à l’identifiant de la session active. Une ancienne session ou un mauvais code ne peut
pas prendre ce canal. Le flux média reste disponible en repli si le canal dédié échoue.
NVENC/AAC/MP4 travaillent sur un seul thread distinct de la boucle qui reçoit les commandes.
La fermeture attend la fin de l’encodage avant de libérer la capture et la RAM partagée.

Le navigateur vérifie le direct toutes les 100 ms : accélération légère à partir de
200 ms de file, rattrapage au-delà de 400 ms vers une cible de 120 ms. Le son suit la même
vitesse. Les fragments restent de 100 ms, car des fragments plus courts ont produit
des irrégularités de décodage dans les essais. La capture conserve au maximum une lecture
GPU en cours et répète la dernière image réelle pendant une lecture lente, sans accumuler
de captures. Une cadence vidéo stable ne signifie donc pas autant de nouvelles images source.

Essai local réel DXGI/NVENC/AAC/Chromium : 131 images décodées en environ 4,5 s,
RTT de commandes 1 ms et file vidéo mesurée de 153 ms. Ce RTT local ne mesure ni le
réseau Internet ni la latence écran-à-écran. La latence ngrok et les lectures GPU lentes
peuvent ajouter du délai. Aucun chiffre avant/après n’est annoncé : l’essai initial sur
le tunnel a été interrompu par une nouvelle connexion et n’était pas comparable.

Vérifications : plein écran aux dimensions du viewport et barres masquées sous Chromium,
sortie tactile sous Chromium/WebKit, authentification et remplacement des canaux dans
`tests/tunnel_integration.py`. Le test physique Ctrl+W reste dans
`tests/native_keyboard_probe.py`.

Vérification de l’exe 0.2.7 via le tunnel ngrok actif : 720p à 28,9 FPS reçus,
audio en lecture, RTT de commandes de 234 ms et file vidéo instantanée de 421 ms.
La mesure locale de 153 ms ne doit donc pas être présentée comme une garantie Internet.
Les seuils de rattrapage sont vérifiés périodiquement et ne constituent pas une limite
stricte de la latence écran-à-écran. Résultat : `test-results/ngrok-0.2.7.json`.
