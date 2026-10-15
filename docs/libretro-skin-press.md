# Enfoncement des touches des skins — frontend libretro embarqué

Travail sur `Claude`, par-dessus `4eab71c` (Build 459). Le renderer et le
suivi tactile sont communs aux plateformes du moteur embarqué, y compris
les consoles masquées. Un nouveau cœur d'une plateforme connue reprend ce
fonctionnement ; une nouvelle plateforme doit déclarer son profil de commandes.

## Diagnostic établi

`LibretroSkin.itemFromObject:` décodait déjà `asset.normal`, l'ancien
`asset.name`, les dimensions du graphisme et le capuchon indépendant des
sticks. PNG, JPEG et PDF sont contrôlés par leur contenu. Le défaut principal
était dans `LibretroSkinRenderer` : l'appui activait une forme blanche ou une
image blanche masquée, sans déplacer le graphisme. Les touches dessinées
uniquement dans le fond n'avaient pas de calque indépendant.

Sources et fichiers réellement examinés :

| Source | Constat |
| --- | --- |
| [Guide officiel Manic EMU](https://manicemu.site/guides/homemade-skins/) | Séparation fond/éléments ; `asset.normal`. `asset.selected` et `animation.begin/end` concernent la sélection des interrupteurs. Aucun champ standard `pressed` n'est supposé. |
| [RetroSkinner](https://github.com/Manic-EMU/RetroSkinner), `Python CLI/skin_common.py` | L'export Manic fournit les éléments séparés ; l'export Delta aplatit le rendu dans le fond. |
| Manic DS, PS1, GBA et SNES, révision `fbaeab79c214d5920bb51afa6f2d786fb2b12a58` | Contrôles PDF séparés et variantes téléphone/tablette, portrait/paysage. Les tests téléchargent DS/PS1 depuis Git LFS, avec taille et SHA-256 vérifiés. |
| NES Ignited et Control Center NES, LitRitt `8f788c6ea9c0cadb15ce700fc4208507c463131c` | Touches intégrées aux PDF du fond. Les textures ne permettent pas d'annoncer une séparation automatique fiable. |
| DMG-01 4NES, `delta-skins/delta-skins.github.io` `61dad28f552051bc05f519f968e913bf243d22eb` | Même limite pour les graphismes intégrés au fond. Une variante adaptée reste nécessaire si les contrôles ne peuvent pas être isolés. |

Les archives de référence restent externes au produit. Aucun code Manic,
aucun nouveau cœur et aucun fichier graphique tiers ne sont ajoutés à l'app.
L'association plateforme/skin, les profils `LibretroInputMap`, les descripteurs
et libellés des commandes du cœur, la sélection des variantes et les réglages
existants restent les chemins canoniques.

## Corrections

- Chaque contrôle possède un groupe graphique, borné au contrôle et à son
  ombre. Le contact applique immédiatement une réduction de 3,5 % et un
  enfoncement de 0,7 à 2 points. Le relâchement revient en 120 ms ; une nouvelle
  pression interrompt ce retour. « Réduire les animations » supprime
  l'interpolation du retour. Les zones tactiles restent fixes.
- Une croix monobloc s'enfonce et se déplace légèrement vers les directions
  effectivement résolues. Les flèches séparées s'animent comme des touches.
  Un stick conserve sa base et ne réduit que son capuchon mobile.
- Le halo blanc cesse d'être le retour principal des éléments séparés.
  L'ombre supplémentaire reste discrète ; les rectangles extraits ne
  reçoivent pas d'ombre artificielle.
- Un fond peut être adapté en mémoire si la zone, élargie de 6 points, reste
  dans le skin et hors des écrans et contrôles voisins. Un périmètre opaque
  doit correspondre à un fond uniforme ou à un léger gradient bilinéaire.
  Les fonds translucides et les zones vides, presque entièrement remplies, texturées ou incertaines
  sont refusées. Le fond original est masqué sous l'élément extrait et
  remplacé par un arrière-plan fixe ; la touche originale ne reste pas dessous.
- Cette préparation et le décodage se font sur la file des images, avec cache.
  L'appui ne déclenche ni lecture de fichier ni téléchargement. Le retour de l'éditeur conserve les
  éléments extraits. Les générations
  de disposition empêchent un ancien résultat de modifier un nouveau skin.
- Les directions visuelles proviennent de la même résolution tactile que
  l'entrée RetroPad. Le raccordement ne dépend pas du diagnostic tactile.
  La connexion d'une manette annule les contacts de jeu, en conservant le
  stylet DS/3DS. La déconnexion ne ressuscite pas les anciens contacts.
- Un remplacement de skin annule les contacts même si les deux imports
  réutilisent les mêmes identifiants. Les annulations du menu, de la rotation,
  de l'arrière-plan et de la fermeture sont conservées.
- Un avertissement sur les touches intégrées au fond est traduit dans les
  douze langues. Les imports existants le déduisent en mémoire d'`info.json` :
  leurs fichiers, leur identité et leurs sélections ne sont pas réécrits.

`selected` n'est jamais utilisé comme état d'appui. Cette modification des
contrôles momentanés n'ajoute pas les animations persistantes de sélection
ni les commandes personnalisées d'interrupteurs non prises en charge.

## Fichiers modifiés

| Fichiers | Fonction |
| --- | --- |
| `LibretroSkinRenderer.h/.m`, `LibretroSkinButtonCrop.h/.m` | Graphismes animés, préparation des fonds, masque et arrière-plan fixe. |
| `LibretroTouchTracker.h/.m`, `LibretroTouchOverlay.h/.m` | Directions résolues, publication commune, annulation des contacts désactivés. |
| `LibretroGameViewController.m` | Raccordement visuel et annulation au changement de représentation. |
| `LibretroSkin.h/.m`, `lib/services/libretro_skin_service.dart`, `lib/l10n/libretro_locale.dart` | Limites des fonds, imports existants, traductions et affichage de l'avertissement. |
| `test/libretro_host/frontend/{skin_test,touch_tracker_test,skin_button_crop_test}.m`, `test/libretro_frontend_test.py` | Comportement natif, extraction/refus, profils et dispositions. |
| `test/libretro_simulator/{probe.m,skin_press_probe.h}`, `test/libretro_simulator_probe.py`, `test/libretro_skin_press_probe.py` | Sessions réelles, contacts UIKit scriptés, entrées reçues et captures. |
| `test/libretro_skin_service_test.dart`, `.github/workflows/libretro-checks.yml` | Imports conservés et exécution des contrôles en CI. |

Les fichiers natifs du tableau se trouvent dans
`packages/libretro_internal_bridge/ios/Classes/`.

## Vérifications et limites

La sonde utilise le vrai `LibretroSession`, la surcouche UIKit, le renderer,
le verrouillage des entrées et le thread d'émulation. Les contacts sont
scriptés : ils ne constituent pas un essai de l'écran tactile physique.

Le Simulateur expose une manette inactive qui masque normalement les touches
et occupe un port. L'énumération des manettes est isolée dans l'exécutable de
test uniquement : aucune manette pendant les essais tactiles, puis une vraie
`GCVirtualController` Apple pendant l'essai du polling. Ni les profils et
valeurs de cette manette, ni le suivi tactile, ni l'état d'entrée du produit
ne sont remplacés. Ce contrôle ne vaut pas un essai de manette matérielle.

La matrice exécutée contient neuf sessions :

| Cas | Cœur / contenu | Graphismes | Appareils simulés |
| --- | --- | --- | --- |
| DS | DeSmuME réel / programme original | Manic DS, PDF indépendants | iPhone, iPad |
| Profil PSX | NeoTest / mire originale | Manic PS1, PDF indépendants | iPhone, iPad |
| NES | NeoTest / mire originale | Skin PNG original avec touches intégrées ; refus de NES Ignited réel | iPhone |
| PC Engine | Beetle PCE Fast réel / programme original | Skin vectoriel par défaut | iPhone, iPad |
| Profil N64 | NeoTest / mire originale | Skin par défaut et stick analogique | iPhone, iPad |

Les séquences vérifient le contact immédiat, le maintien, deux doigts sur une
même touche, le glissement, la diagonale avec un bouton, le relâchement et
l'annulation, les actions du menu de skins, les méthodes de cycle de vie,
le capuchon et les axes du stick, puis la connexion et la déconnexion de la
manette virtuelle. Les tests portables couvrent les profils et dispositions
portrait/paysage du téléphone et de la tablette.

Les captures combinent une vraie image Metal présentée et les calques du
renderer à leur disposition courante. Une alternance de trois captures
ne mesure pas la durée de l'animation de retour.

Restent à effectuer sur appareil : touchers physiques et latence perçue,
rotation réelle et changements de taille de fenêtre, manettes Bluetooth/USB,
variantes de skins propres à l'appareil et contrôles en jeux commerciaux.
Les profils PSX/N64 testés avec NeoTest ne sont pas des validations des vrais
cœurs PlayStation/Nintendo 64.

## Résultats exécutés — 15 octobre 2026

Révision testée : `d6cb962d5597f7ecd7c81bb17b633e559c95d8d6`.
[CI complète](https://github.com/TarbleFR/neostation-ios/actions/runs/38661616452) :
les jobs `native`, `dart` et `skin-press` sont réussis.

- Compilation et édition de liens des 70 sources du pont pour iPhone.
- 15 fichiers de tests de comportement natif, dont 6 025 vérifications du
  suivi tactile ; extraction et refus des fonds ; variantes et géométrie.
- Analyse Flutter ; 573 tests fonctionnels, 245 tests de stockage et les
  contrats du dépôt. Le stockage n'est pas modifié par ce travail.
- Neuf sessions iPhone SE (3e génération) / iPad mini (A17 Pro), iOS 26.2
  Simulator, Xcode 26.3 : 270 vérifications, zéro échec.
- Les images montrent un graphisme différent pendant le maintien et un
  retour pixel pour pixel au repos dans les neuf zones de touches contrôlées.
  Le raccord du fond simple ne laisse plus de liseré de masque.
- Le passage dans l'état d'édition puis sa sortie conserve l'image extraite.
  NES Ignited est refusé par l'extraction et porte l'avertissement attendu.

La sonde attend la fin effective des transitions du menu avant les contacts.
L'enfoncement visuel reste contrôlé synchroniquement au contact ; la réception
asynchrone par le cœur est attendue à son polling, avec une échéance de deux
secondes. Une entrée absente échoue toujours. Sur cette exécution finale,
aucune attente supplémentaire de polling n'a été nécessaire.

Artefact de preuves : `11939890679`, archive SHA-256
`f8ac05d2f299d2c2ad83667e0e69ed2314b9ab82fab5f1add6de30d24bfedd7a`.
Il contient les images originales, les résultats par session et le verdict.
Les documents seuls sont mis à jour après cette révision ; aucune validation
physique ni mesure de latence sur iPhone n'est déduite de la CI.
