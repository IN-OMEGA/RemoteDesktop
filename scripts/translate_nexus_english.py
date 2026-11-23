"""One-time migration of the native UI and its existing assertion messages."""
from pathlib import Path

TRANSLATIONS = r'''
Une erreur d’interface a été enregistrée. Rouvre cet écran.	An interface error was logged. Reopen this screen.
Prêt · aucun jeu lancé automatiquement	Ready · no game is launched automatically
 · mises à jour	 · updates
Une opération est en cours. Elle continue en arrière-plan.	An operation is running in the background.
Recherche de tes repacks…	Looking for your repacks…
 jeux · flèches pour naviguer · F11 plein écran	 games · arrow keys to browse · F11 fullscreen
Recherche de la fiche · seul le titre est envoyé à Wikipédia…	Finding game details · only the title is sent to Wikipedia…
Fiche Wikipédia ajoutée · vérifie la correspondance du titre	Wikipedia details added · check the title matches
Les fichiers du programme ont changé. Lance une analyse manuelle depuis Protection.	Program files have changed. Run a manual scan from Protection.
Programme modifié · vérification manuelle requise. Aucune analyse automatique relancée.	Program changed · manual verification required. No automatic rescan started.
 · aucun indicateur détecté · rapport enregistré	 · no indicators detected · report saved
 · consulte Protection	 · see Protection
Une analyse Windows a signalé une détection ou une erreur pour ce jeu. Résous le problème puis relance un Scan Windows avant de jouer.	A Windows scan reported a detection or error for this game. Resolve it, then run Windows Scan again before playing.
Seuls les EXE, BAT et CMD peuvent être lancés.	Only EXE, BAT and CMD files can be launched.
La cible est hors du dossier du jeu.	The target is outside the game folder.
Demande de lancement envoyée à Windows · 	Launch request sent to Windows · 
Lancé · 	Launched · 
Lancement bloqué	Launch blocked
Changer le dossier REPACKS	Change REPACKS folder
Détecter mes repacks	Find my repacks
Importer un dossier de jeu	Import a game folder
Importer un jeu	Import a game
Dossier contenant le jeu	Folder containing the game
Aucun EXE, Run Me ou Run détecté dans ce dossier.	No EXE, Run Me or Run found in this folder.
Importé · 	Imported · 
Choisir un autre lanceur	Choose another launcher
Choisis un lanceur à l’intérieur du dossier du jeu.	Choose a launcher inside the game folder.
Choisir une image	Choose an image
Chercher une description en ligne	Find a description online
Modifier la description	Edit description
Personnaliser · 	Customize · 
Copier le SHA-256 complet	Copy full SHA-256
Analyse le jeu pour obtenir son SHA-256.	Scan the game to get its SHA-256.
SHA-256 complet copié dans le presse-papiers.	Full SHA-256 copied to clipboard.
SHA-256 complet copié.	Full SHA-256 copied.
Attends la fin de l’opération en cours.	Wait for the current operation to finish.
Colle une adresse de page, un lien direct ou un magnet.	Paste a web page address, direct link or magnet link.
Inspection du lien · lecture de la page et des en-têtes uniquement…	Inspecting link · reading only the page and headers…
Recherche de liens annulée.	Link search cancelled.
Choisir un lien	Choose a link
Liens de téléchargement trouvés	Download links found
 lien(s) trouvé(s) sur 	 link(s) found on 
Choisis un lien à vérifier. Aucun fichier n’est encore téléchargé.	Choose a link to verify. No file has been downloaded yet.
Vérifier ce lien →	Verify this link →
Ouvrir la page dans le navigateur	Open page in browser
Confirmer le téléchargement	Confirm download
Vérifie le fichier avant de télécharger.	Check the file before downloading.
Hôte : 	Host: 
Fichier : 	File: 
Taille : 	Size: 
taille non fournie par le serveur	size not provided by server
 octets	 bytes
Nom du dossier dans REPACKS/downloads	Folder name in REPACKS/downloads
Le téléchargement commencera uniquement après ton clic ci-dessous.\nLe fichier sera analysé ensuite ; aucun programme ne sera lancé.	The download starts only after you click below.\nThe file will then be scanned; no program will be launched.
Choisis un nom de dossier simple, sans caractères Windows réservés.	Choose a simple folder name without reserved Windows characters.
Confirmer et télécharger	Confirm and download
Donne un nom de dossier simple au téléchargement.	Enter a simple folder name for this download.
Téléchargement en cours · progression dans Téléchargements	Downloading · track progress in Downloads
aria2 a terminé avec le code 	aria2 exited with code 
. Consulte le journal et reprends le même lien.	. Check the log and resume using the same link.
Téléchargement terminé · analyse statique des fichiers…	Download complete · scanning files…
Téléchargement terminé · 	Download complete · 
 · extrais le ZIP puis analyse le jeu avant lancement	 · extract the ZIP, then scan the game before launching
Téléchargement annulé · fichiers partiels conservés	Download cancelled · partial files kept
Téléchargement annulé	Download cancelled
Téléchargement en pause	Download paused
 · fichiers partiels conservés	 · partial files kept
Extraction terminée · 	Extraction complete · 
 · analyse requise avant lancement	 · scan required before launch
Vérifier avant de jouer.	Check before you play.
Protection locale au lancement dans Nexus. Aucun pilote de surveillance système. Aucune garantie contre tous les malwares.\nUn résultat incomplet ou suspect bloque le lancement ; les fichiers ne sont jamais envoyés à un service d’analyse.	Local protection when launching from Nexus. No system monitoring driver. No guarantee against every threat.\nIncomplete or suspicious results block launch; files are never sent to a scanning service.
Signatures connues · scripts Ren’Py · charges masquées · DLL proxy · scripts sensibles	Known signatures · Ren’Py scripts · hidden payloads · proxy DLLs · sensitive scripts
Annuler l’analyse	Cancel scan
Mettre le dossier en quarantaine	Quarantine folder
Voir le rapport	View report
Aucun rapport pour ce jeu. Lance une analyse.\n\nLes noms setup.py / Setup.exe et la petite taille sont des indices, pas une preuve.\nLes archives RAR/7z, chiffrées ou hors budget doivent être extraites puis analysées.\nLe contenu des EXE/DLL peut être obfusqué : un résultat sans indicateur ne garantit pas la sécurité.	No report for this game. Run a scan.\n\nNames such as setup.py / Setup.exe and file size are clues, not proof.\nRAR/7z, encrypted or oversized archives must be extracted and scanned.\nEXE/DLL content may be obfuscated: no indicators detected does not guarantee safety.
 fichiers inventoriés	 files inventoried
SHA-256 DES FICHIERS ACTIFS	SHA-256 OF ACTIVE FILES
La quarantaine est limitée aux dossiers dans REPACKS/games. Aucun dossier Epic ou Microsoft ne sera déplacé.	Quarantine is limited to folders in REPACKS/games. No Epic or Microsoft folders will be moved.
Déplacer le dossier de 	Move the folder for 
 en quarantaine ? Tu pourras le restaurer depuis le dossier de quarantaine.	 to quarantine? You can restore it from the quarantine folder.
Dossier déplacé en quarantaine · aucune suppression définitive	Folder quarantined · nothing permanently deleted
Vérification de la disponibilité de Microsoft Defender…	Checking Microsoft Defender availability…
Moteur Microsoft Defender introuvable.	Microsoft Defender engine not found.
Microsoft Defender n’est pas actif. Termine ton analyse Malwarebytes ; Nexus ne modifie pas tes réglages antivirus.	Microsoft Defender is inactive. Complete your Malwarebytes scan; Nexus does not change antivirus settings.
Analyse Windows en cours · aucune remédiation automatique demandée…	Windows scan in progress · no automatic remediation requested…
Analyse Windows : détection ou erreur (code 	Windows scan: detection or error (code 
). Consulte le rapport et Sécurité Windows. Aucun lancement.	). Check the report and Windows Security. Launch blocked.
Analyse Windows terminée · aucune menace signalée par cette commande · rapport enregistré	Windows scan complete · no threats reported by this command · report saved
Une opération est en cours. Quitter et interrompre cette opération ?	An operation is running. Quit and interrupt it?
Jeu lancé · zone de notification indisponible : 	Game launched · notification area unavailable: 
Ouvrir Nexus Repacks	Open Nexus Repacks
Quitter Nexus	Quit Nexus
Le contrôle statique réduit le risque. Il ne garantit pas l’innocuité du jeu.	Static inspection reduces risk. It does not guarantee the game is safe.
Prêt pour ta prochaine session. Analyse le dossier avant de jouer ; ajoute une fiche en ligne ou personnalise ta bibliothèque.	Ready for your next session. Scan the folder before playing; add game details or customize your library.
Importe un dossier de jeu, un jeu Microsoft ou démarre un téléchargement.	Import a game folder, a Microsoft game or start a download.
L’application est lancée par Windows. Ce moteur ne peut pas inspecter les paquets WindowsApps protégés.	Windows launches this app. This engine cannot inspect protected WindowsApps packages.
Choisir un jeu Microsoft / Xbox installé	Choose an installed Microsoft / Xbox game
Identifiant Microsoft non valide.	Invalid Microsoft identifier.
BIBLIOTHÈQUE PERSONNELLE	PERSONAL LIBRARY
TES JEUX. TON UNIVERS.	YOUR GAMES. YOUR WORLD.
Ta prochaine aventure commence ici.	Your next adventure starts here.
Agrandis ton univers.	Expand your universe.
LANCEMENT PAR WINDOWS · NON ANALYSÉ	WINDOWS LAUNCH · NOT SCANNED
PAS ENCORE ANALYSÉ	NOT SCANNED YET
Analyser et jouer	Scan and play
Analyser · 	Scan · 
Ajouter à Nexus	Add to Nexus
Cible invalide	Invalid target
Dossier invalide	Invalid folder
Dossier REPACKS	REPACKS folder
Application Microsoft	Microsoft application
Source : Wikipédia ↗	Source: Wikipedia ↗
Scan Windows	Windows scan
Code retour : 	Exit code: 
disponible après analyse	available after scanning
Ton prochain univers commence ici.	Your next world starts here.
Ton jeu, ton univers. Retrouve ta collection et reprends l’aventure.	Your game, your world. Browse your collection and pick up the adventure.
 jeux dans ta collection personnelle	 games in your personal collection
Toute ta collection	Your entire collection
À L’AFFICHE  /  TA SÉLECTION	IN THE SPOTLIGHT  /  YOUR PICK
POUR NAVIGUER	TO BROWSE
A U R O R A   /   2.1\n\nF11  Plein écran\nF8   Animations	A U R O R A   /   2.2\n\nF11  Fullscreen\nF8   Animations
ESPACE PERSONNEL	PERSONAL SPACE
Entre dans un\nnouvel univers.	Enter a\nnew world.
Ajouter mon premier jeu	Add my first game
Ajouter un jeu	Add a game
animations normales	standard motion
mouvements réduits	reduced motion
Pense à sauvegarder dans le jeu avant de le quitter.\nNexus ne peut pas enregistrer une progression restée en mémoire\nune fois le jeu fermé.	Remember to save in the game before quitting.\nNexus cannot save progress left in memory\nafter the game closes.
Pense à sauvegarder	Remember to save
Ne perds pas ta progression.	Keep your progress.
Compris — lancer le jeu	Got it — launch game
Une opération est en cours. Attends sa fin avant de lancer le jeu.	An operation is running. Wait for it to finish before launching the game.
Première analyse requise	First scan required
Aucune fiche correspondante trouvée. Tu peux ajouter une description manuellement.	No matching game details found. You can add a description manually.
Aucune fiche correspondante	No matching game details
Rechercher un jeu installé…	Search installed games…
NOUVEAU TÉLÉCHARGEMENT	NEW DOWNLOAD
Ajoute ton prochain jeu	Add your next game
Lien de téléchargement	Download link
https://… ou magnet:…	https://… or magnet:…
Nom du dossier	Folder name
Ex. Mon prochain jeu	e.g. My next game
Vérifier le lien	Check link
Choisir un .torrent	Choose a .torrent
Page web · lien direct · magnet · torrent\nLe fichier est confirmé avant le transfert.	Web page · direct link · magnet · torrent\nConfirm the file before transferring.
PRÊT À TÉLÉCHARGER	READY TO DOWNLOAD
Aucun transfert en cours	No active transfer
Le téléchargement démarre après ta confirmation.	The download starts after your confirmation.
TEMPS RESTANT	TIME LEFT
Ouvrir le dossier	Open folder
OÙ TROUVER DES REPACKS ?	WHERE TO FIND REPACKS
Ouvre un site, trouve un jeu, puis copie son lien ici.	Open a site, find a game, then paste its link here.
Liens externes · Un fichier volumineux peut aussi contenir du code malveillant.	External links · Large files can contain malicious code too.
Afficher le journal	Show log
Masquer le journal	Hide log
Extraire un ZIP	Extract ZIP
CONNEXION EN COURS	CONNECTING
TÉLÉCHARGEMENT EN COURS	DOWNLOADING
ARRÊT EN COURS…	STOPPING…
EN PAUSE · REPRISE DISPONIBLE	PAUSED · READY TO RESUME
ANNULÉ · FICHIERS PARTIELS CONSERVÉS	CANCELLED · PARTIAL FILES KEPT
TRANSFERT TERMINÉ · ANALYSE EN COURS	TRANSFER COMPLETE · SCANNING
TERMINÉ · ANALYSE EFFECTUÉE	COMPLETE · SCANNED
TRANSFERT INTERROMPU	TRANSFER INTERRUPTED
taille à déterminer	size pending
Vérifie le lien, puis confirme le fichier à télécharger.	Check the link, then confirm the file to download.
 · Données reçues conservées sur le disque.	 · Downloaded data kept on disk.
Une nouvelle aventure, à portée de lien.	A new adventure, one link away.
Clique pour entrer	Click to enter
Lanceur de l’échantillon Ren’Py analysé	Launcher from the analyzed Ren’Py sample
Archive du chargeur malveillant Ren’Py	Malicious Ren’Py loader archive
Charge ZIP masquée par XOR	XOR-hidden ZIP payload
Hôte EventEmitter utilisé par cet échantillon	EventEmitter host used by this sample
DLL proxy malveillante ETWProviders	Malicious ETWProviders proxy DLL
Configuration masquée du chargeur	Hidden loader configuration
AUCUN INDICATEUR DÉTECTÉ	NO INDICATORS DETECTED
À EXAMINER	NEEDS REVIEW
BLOQUÉ	BLOCKED
Analyse annulée.	Scan cancelled.
Annulé	Cancelled
Archive chiffrée : contenu non vérifié.	Encrypted archive: contents not verified.
Archive conservée à côté du jeu : non utilisée pour ce lancement. Analyse séparée depuis Téléchargements.	Archive stored alongside the game: not used for this launch. Scan it separately from Downloads.
Archive imbriquée à extraire et analyser séparément.	Nested archive: extract and scan separately.
Archive non inspectée. Extrais-la sans lancer son contenu, puis analyse le dossier extrait.	Archive not inspected. Extract it without running its contents, then scan the extracted folder.
Archives imbriquées : limite atteinte.	Nested archive limit reached.
Aucun bloc Ren’Py inspectable.	No inspectable Ren’Py blocks.
Chemin de sortie d’archive dangereux : 	Unsafe archive output path: 
Code Python décodé puis exécuté dynamiquement.	Python code decoded then executed dynamically.
Combinaison DLL proxy ETW et runtime Rust de la charge analysée.	ETW proxy DLL and Rust runtime combination from the analyzed payload.
Combinaison de fonctions suspectes : 	Suspicious function combination: 
Configuration cachée du chargeur Ren’Py : charge XOR et exécutable cible.	Hidden Ren’Py loader configuration: XOR payload and target executable.
Domaine de signalement présent dans l’échantillon analysé.	Reporting domain found in the analyzed sample.
Dossier inaccessible.	Folder inaccessible.
Entrée RPA hors limites ou trop grande.	RPA entry out of bounds or oversized.
Entrée RPA non interprétable.	Cannot interpret RPA entry.
Fichier actif trop volumineux pour l’inspection du contenu ; SHA-256 calculé.	Active file too large for content inspection; SHA-256 calculated.
Format Ren’Py compilé non reconnu : inspection impossible.	Unrecognized compiled Ren’Py format: inspection unavailable.
Grand fichier apparemment rempli de zéros : bourrage possible, à examiner.	Large file appears filled with zeros: possible padding, review required.
Index RPA excessif	RPA index too large
Inspection impossible : 	Inspection unavailable: 
Lien de fichier non inspecté.	File link not inspected.
Lien ou jonction ignoré : inspection incomplète.	Link or junction skipped: incomplete inspection.
Limite ZIP	ZIP limit
Limite de fichiers atteinte.	File count limit reached.
Limite d’inspection ZIP atteinte pour un fichier actif.	ZIP inspection limit reached for an active file.
Nexus Static 1.1 / règles RenPy-ETW 2026-11-19	Nexus Static 1.1 / RenPy-ETW rules 2026-11-19
Petit paquet avec setup : vérifier sa provenance. Taille et nom seuls ne prouvent pas une infection.	Small package with setup: check its source. Size and name alone do not prove infection.
Pickle incomplet	Incomplete pickle
PowerShell encodé ou évaluation dynamique dans un lanceur.	Encoded PowerShell or dynamic evaluation in a launcher.
RPC tronqué	Truncated RPC
Raccourci exécutable : cible non validée, lancement bloqué.	Executable shortcut: target not validated, launch blocked.
Référence exécutable dangereuse dans le pickle : 	Dangerous executable reference in pickle: 
Sélectionne un dossier de jeu.	Select a game folder.
Taille décompressée excessive	Uncompressed size too large
Taux de compression excessif : décompression évitée.	Excessive compression ratio: decompression skipped.
Tentative de modifier ou désactiver Microsoft Defender.	Attempt to modify or disable Microsoft Defender.
Trop d’entrées ZIP.	Too many ZIP entries.
Version d’archive Ren’Py non prise en charge.	Unsupported Ren’Py archive version.
Webhook Discord dans le contenu actif.	Discord webhook in active content.
 fichiers · 	 files · 
 fichiers	 files
Inspection · 	Inspecting · 
Archive chiffrée, lien ou chemin dangereux : extraction refusée.	Encrypted archive, link or unsafe path: extraction refused.
Archive tronquée.	Truncated archive.
Archive trop grande pour l’extraction automatique.	Archive too large for automatic extraction.
Chemins dupliqués dans le ZIP.	Duplicate ZIP paths.
Choisis un nouveau dossier vide pour extraire le ZIP.	Choose a new empty folder to extract the ZIP.
Extraction · 	Extracting · 
Le binaire aria2 embarqué manque ou a été modifié. Téléchargement bloqué.	The bundled aria2 binary is missing or modified. Download blocked.
Le dossier d’extraction a changé.	The extraction folder changed.
Lien invalide.	Invalid link.
Nom de fichier Windows réservé.	Reserved Windows filename.
Nom de fichier de sortie invalide.	Invalid output filename.
Page de provenance invalide.	Invalid source page.
Utilise un lien HTTP(S), un lien magnet ou un fichier .torrent.	Use an HTTP(S) link, magnet link or .torrent file.
). Ouvre la page dans ton navigateur si une connexion ou un CAPTCHA est requis.	). Open the page in your browser if login or a CAPTCHA is required.
Aucun lien public utilisable trouvé. Le bouton peut dépendre de JavaScript, d’une connexion, d’un CAPTCHA ou d’un hébergeur non pris en charge.	No usable public link found. The button may require JavaScript, login, a CAPTCHA or an unsupported host.
Fichier local	Local file
Fichier proposé	Suggested file
Impossible de résoudre ce domaine.	Cannot resolve this domain.
Le serveur a changé de réponse entre l’inspection et la lecture. Réessaie le lien direct.	The server response changed between inspection and reading. Retry the direct link.
Le serveur a répondu sans contenu.	The server returned no content.
Le serveur refuse l’inspection (HTTP 	The server refused inspection (HTTP 
Les pages du réseau local ne sont pas explorées.	Local network pages are not inspected.
Lien contenant des identifiants ou des caractères de contrôle : refusé.	Link with credentials or control characters: refused.
Lien magnet invalide : identifiant BitTorrent manquant ou incorrect.	Invalid magnet link: missing or incorrect BitTorrent identifier.
Page trop volumineuse pour l’inspection automatique (limite 2 Mio).	Page too large for automatic inspection (2 MiB limit).
Redirection de la page	Page redirect
Seuls les liens HTTP(S) publics sont analysés.	Only public HTTP(S) links are inspected.
Une adresse locale ou réservée a été refusée.	A local or reserved address was refused.
Torrent magnet	Magnet torrent
Recherche de mise à jour…	Checking for updates…
Mise à jour installée.	Update installed.
Version invalide	Invalid version
Adresse HTTPS requise	HTTPS address required
Empreinte invalide	Invalid digest
Taille de mise à jour invalide	Invalid update size
Téléchargement trop volumineux	Download too large
Mise à jour corrompue	Corrupted update
EXE invalide	Invalid EXE
Mise à jour indisponible · réessayer	Update unavailable · retry
Mise à jour 	Update 
 · téléchargement…	 · downloading…
 prête · appliquée à la fermeture	 ready · applied on exit
 · à jour	 · up to date
Bibliothèque	Library
Téléchargements	Downloads
Téléchargement	Download
Reprendre	Resume
Annuler	Cancel
CONNEXIONS	CONNECTIONS
VITESSE	SPEED
Actualiser	Refresh
Importer	Import
Jouer	Play
TOUT	ALL
Rapport	Report
Quarantaine	Quarantine
Description	Description
Images	Images
Fermer	Close
Enregistrer	Save
Retour	Back
Quitter	Quit
 Gio	 GiB
 Mio	 MiB
'''


def main():
    root = Path(__file__).resolve().parents[1]
    pairs = [line.split('\t', 1) for line in TRANSLATIONS.splitlines() if '\t' in line]
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    for path in [*(root/'nexus_repacks').glob('*.py'), *(root/'tests').glob('*nexus*.py')]:
        # Keep the resolver's multilingual discovery keywords in their original languages.
        text = path.read_text('utf-8-sig')
        for french, english in pairs:
            text = text.replace(french, english)
        path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
