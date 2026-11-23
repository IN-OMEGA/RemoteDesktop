# Nexus Repacks 2.0 — Aurora

Direction : une bibliothèque personnelle calme et lumineuse, avec un seul accent bleu glacier `#adefff`, du blanc bleuté `#effbff`, des neutres ardoise et un fond `#080f16`. L’accent est clair ; les surfaces restent sombres pour rendre les visuels et les textes lisibles. Grille de 8 px, navigation latérale persistante, un visuel principal encadré, actions groupées et collection horizontale sans changement de sélection à la molette.

## Mouvement

Une ouverture originale de 1,55 s dessine le monogramme N avec une lumière douce, puis révèle la fenêtre en 240 ms. Le clic passe l’intro. Le chemin réduit montre directement le logo final et retire le déplacement. La fenêtre et ses transitions ont des durées indépendantes : changer d’onglet pendant l’ouverture ne peut pas laisser la fenêtre transparente.

Entrées avec décélération, sorties avec accélération ; micro-interactions 90–120 ms, panneaux 280–300 ms, titre 460 ms, décalage des cartes 40 ms. Pas de déformation de texte, de rotation de grande surface ni de carrousel automatique. Les flous et les images de fondu sont calculés hors de la boucle d’événements Tk. Les animations se terminent au repos et ne gardent aucune boucle de fond permanente.

Le moteur demande temporairement des réveils Windows plus précis pendant les animations et libère cette demande après annulation ou fin. Les appels suivent le contrat [timeBeginPeriod / timeEndPeriod de Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/timeapi/nf-timeapi-timebeginperiod). Les intervalles sont mesurés dans le test natif ; il ne s’agit pas d’une garantie de rendu GPU à 60 images/s sur tous les PC.

## Revue des 19 skills demandés

Tous les skills installés ont été consultés. La livraison reste une application Windows native ; appliquer leurs principes ne signifie pas embarquer leurs runtimes web/vidéo.

| Skill | Décision pour Aurora |
|---|---|
| motion-art-direction | Une seule personnalité, calme, un seul accent et un point focal. |
| animation-principles | Hiérarchie titre / actions / cartes, décélération et décalages bornés. |
| micro-interaction | Retour immédiat sur pression, survol progressif et protection contre les clics répétés. |
| accessible-animation | Chemin réduit, réglage F8, absence de déplacement en mode réduit. |
| 60fps-animation | Préparer les effets coûteux, éviter les recalculs de disposition, mesurer les intervalles réels. |
| logo-animation | Monogramme original dessiné en moins de 2,5 s, statique final fourni. |
| svg-animation | Même géométrie de tracé dans le SVG, l’icône et le dessin natif. |
| kinetic-typography | Dévoilement par blocs, lignes stables, aucune déformation des caractères. |
| color-motion | Palette limitée, accent très clair peu saturé, neutres teintés dans la même famille et interpolation OKLab des fondus de couleur. |
| glassmorphism | Reflets fins et profondeur préparés dans les visuels ; pas de faux flou système prétendu. |
| shot-composition | Composition asymétrique, zones sûres, adaptation à 1120 × 740 et 1440 × 900. |
| motion-background | Halo discret à l’ouverture ; absence de boucle coûteuse dans la bibliothèque au repos. |
| page-transition-animation | Navigation persistante, sortie avant remplacement, annulation liée au cycle de vie. |
| gsap-web | Principe de timeline unique adapté au moteur natif ; GSAP et ScrollTrigger ne sont pas embarqués. |
| lottie-animation | Cycle fini, possibilité de passer et image finale statique ; pas de lecteur Lottie ajouté sans asset Lottie. |
| beat-sync-editing | Établir / dessiner / poser / révéler ; aucune musique ni synchronisation audio fictive. |
| after-effects | Séparer géométrie, couleurs et timing ; aucun projet After Effects ou export AE revendiqué. |
| remotion-video | Échantillons temporels reproductibles de l’intro pour vérification ; aucun export vidéo demandé ou ajouté. |
| ascii-animation | Évalué pour les états d’attente ; effet ASCII écarté car contraire à la direction visuelle choisie. |

## Vérification

`python -m tests.nexus_aurora_probe` contrôle l’intro normale, le mode réduit, le passage immédiat, la transparence finale, un changement d’onglet pendant la sortie et la libération de l’horloge au repos. Il capture l’intro au début, au milieu et à la fin, puis la bibliothèque en deux tailles.

Les tests de navigation et de dialogues vérifient aussi les rafales de clics, le rappel de sauvegarde, la molette et le retour de la zone de notification. Aucun jeu n’est lancé par ces tests.
