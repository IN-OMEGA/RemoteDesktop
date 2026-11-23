# Recherche et changements vérifiés — 0.3.0

| Produit | Éléments publiés par l’éditeur | Conséquence pour Nexus |
| --- | --- | --- |
| AnyDesk | Codec propriétaire DeskRT, connexions directes possibles, cible de 60 FPS annoncée | Le tarif gratuit ne supprime pas ces avantages techniques ; le nom « Premium » ne prouve aucune supériorité |
| Getscreen.me | WebRTC prioritaire, STUN/TURN pour traverser les NAT, WebSocket de secours ; codecs AV1, H264 et VP8 selon les appareils | Éviter de forcer le transport média via ngrok lorsqu’un chemin direct fonctionne |
| Nexus 0.3.0 | DXGI/D3D11, NVENC H.264, audio WASAPI ; WebRTC prioritaire et repli H.264/AAC/WebSocket | Choix compatibles avec le navigateur et le GPU présent, sans reproduire DeskRT |

Sources primaires : [AnyDesk Performance](https://anydesk.com/en/performance),
[AnyDesk Connection Settings](https://support.anydesk.com/docs/settings),
[Getscreen Screen Image Quality](https://docs.getscreen.me/user-guides/quality/),
[WebRTC ICE](https://webrtc.org/getting-started/peer-connections),
[Cloudflare STUN](https://developers.cloudflare.com/realtime/sfu/get-started/connection-patterns/).

Les pages techniques consultées ne documentent pas assez l’implémentation interne pour
affirmer le langage, le chemin de capture ou les algorithmes exacts de tous leurs clients.
DeskRT n’est pas un codec que Nexus peut réutiliser directement dans un navigateur.

## Changements concrets

- Le site public essaie maintenant WebRTC direct. STUN découvre les adresses publiques ;
  il ne relaie pas les médias. Le tunnel HTTPS reste disponible si ICE échoue. Une
  infrastructure TURN distincte peut être configurée pour les NAT restrictifs.
- Le tunnel ordinateur passe de Baseline/30 FPS/12 Mb/s à High, cible 60 FPS et plafond
  20 Mb/s. NVENC utilise P4, VBR et l’allocation spatiale de qualité ; l’iPhone conserve
  Baseline/720p30 pour la compatibilité.
- Le profil réellement présent dans le MP4 est relu depuis le SPS pour annoncer au
  navigateur un codec correct. Un échantillon 1080p testé porte bien le profil High,
  avec une cadence codée moyenne d’environ 57,7 FPS. Les images répétées et perdues au
  décodage ne prouvent pas autant d’images source nouvelles ni une latence donnée.
- Les commandes gardent leur propre canal et le lecteur suit le direct. Les tampons,
  la capture GPU et le RTT restent des limites mesurables.

## Portée des essais

`tests/internet_transport_probe.py` établit une vraie session WebRTC derrière une
signalisation proxy et teste le repli HTTPS en retirant les candidats réseau distants.
`tests/tunnel_integration.py` vérifie H.264/AAC, sessions, autorisations d’actions Windows
et initialisation automatique une fois par connexion. Les effets externes y sont
remplacés par un faux lanceur pour ne pas ouvrir des applications à chaque test.

`tests/tools_probe.py` télécharge de vraies images PNG, enregistre puis redécode les
vidéos MP4/WebM en entier et sur une zone, et vérifie le délai de 3 secondes de la poignée.
Le réglage Windows 125 % a été appliqué et relu via GetScaleFactorForMonitor sur ce PC.
L’API privée de changement DPI est vérifiée à l’exécution ; elle peut être refusée par
une autre version Windows et ne force jamais de fermeture de session ou d’écriture de
registre nécessitant un redémarrage.

Aucun essai comparable écran-à-écran contre AnyDesk ou Getscreen sur deux appareils
physiques n’a été effectué. Aucun gain de supériorité global n’est donc annoncé.

## Déclenchement corrigé en 0.3.1

Chrome et le réglage 125 % exigent une demande explicite issue d’une connexion par
une personne et une session effectivement connectée. Le démarrage de l’exe ne les
déclenche pas. Le client exclut les navigateurs de test automatisés ; les requêtes
sans ce drapeau n’activent pas la préparation du bureau. Ce drapeau exprime une
intention d’interface, pas une preuve cryptographique de présence humaine. Le code
de connexion et l’identifiant de session restent les conditions d’autorisation.
Les tests de ce comportement utilisent un faux lanceur et vérifient aussi qu’une
connexion automatisée réelle n’appelle jamais ce lanceur.

Le compte ngrok a renvoyé ERR_NGROK_725 (quota mensuel épuisé). Un tunnel temporaire
Cloudflare a été démarré sans modifier ce compte. Une connexion à son URL publique
a établi WebRTC avec audio : l’ICE a choisi des adresses privées sur ce même PC, ce
qui vérifie la signalisation publique et le choix direct, pas la traversée de tous
les NAT entre deux réseaux physiques. Le lien temporaire change si le tunnel est recréé.

## Lien automatique et restauration — 0.3.2

Nexus lance et possède son connecteur Cloudflare Try. Il utilise une configuration
vide dédiée dans son dossier local, sans lire les identifiants d’un tunnel nommé
installé par ailleurs. Le connecteur inclus est épinglé à 2026.11.1 et vérifié par
SHA-256 lors de la compilation. Un relancement ou le bouton Nouveau lien produit
une autre URL ; le code persistant reste conservé. La fenêtre et le menu de notification
proposent la copie du lien. Les anciens assistants manuels ngrok et Cloudflare de
cette session ont été arrêtés ; aucun démarrage ngrok n’est prévu.

Avant de régler 125 %, Nexus mémorise la valeur relative, l’adaptateur et la source
d’affichage. La déconnexion attend une préparation Windows déjà en cours, puis restaure
la valeur mémorisée. Cela évite qu’un réglage tardif laisse 125 % après la déconnexion.
Une restauration refusée est signalée et peut être réessayée. Une fermeture forcée du
processus ne permet pas de garantir une restauration.

Vérifications : `tests/quick_tunnel_probe.py` pour les processus et URL renouvelés ;
`tests/quick_tunnel_live_probe.py` pour deux vrais liens Cloudflare routant vers un
serveur de santé uniquement, sans session de bureau ; `tests/desktop_restore_probe.py`
pour l’échelle simulée, l’annulation et la restauration. Les tests de session vérifient
la restauration lors d’une reprise par un autre client.

## Lecture mobile et notifications — 0.4.0

Les journaux d’un iPhone réel montraient des lectures 1920 × 1080 alors que le profil
mobile devait être actif. Le serveur applique désormais aussi la compatibilité selon
le User-Agent iPhone/iPad, indépendamment de la case client. Cette règle conserve
H.264 Baseline/720p30. Les requêtes d’image-clé NVENC forcent un IDR ; le profil mobile
réduit l’intervalle des images-clés à une demi-seconde.

Le MP4 est déclaré en direct (durée infinie et plage de recherche mise à jour). Le
lecteur préfère MediaSource standard lorsqu’il est disponible, garde ManagedMediaSource
pour iPhone, et évite les recherches trop fréquentes près du dernier fragment. Une
absence de progression du rendu pendant 2,5 s provoque une demande d’image-clé et une
reprise locale : rattachement WebRTC ou reconstruction MSE à partir de l’initialisation
et de trois secondes de fragments bornés en mémoire. Le code et l’identifiant de session
ne changent pas. Le contrôle ne dépend pas de ce décodeur vidéo.

`tests/live_motion_probe.py` filme une vraie fenêtre Windows qui alterne deux couleurs,
vérifie les pixels reçus dans Chromium en configuration iPhone, puis reconstruit le
lecteur et vérifie que les pixels changent encore dans la même session. Cela évite
de confondre un compteur vidéo qui avance avec une image réellement mise à jour.
Aucun iPhone physique n’est pilotable depuis cet environnement : le correctif Safari
reste à confirmer sur l’appareil de l’utilisateur.

Le clavier est codé en HTML/CSS, avec une police Space Grotesk variable sous licence OFL,
et n’ajoute aucun service de police externe. Les caractères sont envoyés en Unicode ;
les raccourcis du clavier virtuel utilisent des touches logiques Windows pour éviter
les inversions de dispositions. `tests/neon_keyboard_probe.py` vérifie les accents,
Shift, Ctrl+A, le suivi du pointeur et la mise en page à 390 px.

L’e-mail part uniquement depuis Windows, via SMTP/TLS authentifié. Les secrets restent
hors des routes HTTP et sont protégés par DPAPI au repos ; seuls le lien et le code
Nexus sont envoyés au destinataire configuré. L’envoi attend une réponse HTTPS valide,
ignore les doublons de journal et les liens déjà remplacés. Les tests SMTP utilisent
un faux serveur et ne diffusent aucun secret réel.

Sources : [Apple Managed Media Source](https://developer.apple.com/videos/play/wwdc2023/10122/),
[régression WebKit de lecture après recherche](https://bugs.webkit.org/show_bug.cgi?id=321919),
[AnyDesk iOS](https://support.anydesk.com/docs/anydesk-for-ios-ipados-tvos),
[SMTP Gmail](https://developers.google.com/workspace/gmail/imap/imap-smtp),
[options NVENC FFmpeg](https://ffmpeg.org/ffmpeg-codecs.html).

## Destinataires explicites — 0.4.1

Le compte SMTP de `.env` n’est plus une adresse destinataire implicite. La liste est
vide au départ et se configure dans la fenêtre Windows, page Connexion. Elle accepte
plusieurs adresses, supprime les doublons et refuse la liste entière si une adresse est
invalide. Enregistrer la liste n’envoie pas de message ; les prochains liens sont
envoyés automatiquement, ou le bouton Envoyer le lien actuel permet un envoi explicite.
Une liste vide désactive les envois. L’ancien champ unique 0.4.0 n’est pas migré comme
destination confirmée, car il pouvait avoir été choisi automatiquement.

Les paramètres restent protégés par DPAPI. Chaque adresse reçoit son propre message
sans les adresses des autres. Un refus SMTP individuel ne bloque pas les adresses
suivantes ; le statut compte les succès et échecs. `tests/link_mailer_probe.py` vérifie
ces règles, la persistance, les doublons, le refus d’une adresse invalide et l’absence
totale d’envoi lorsque la liste est vide, sans envoyer d’e-mail réel.
