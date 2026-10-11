# Onglet consoles de la barre principale (Build 440, paquet C)

Demande du mainteneur du 11 octobre 2026 et décisions de
`docs/build440-plan.md` (section C). Base : `a434881e` (branche `Claude`).
Le SHA de la candidate est consigné à l’intégration de la Build 440 ; ce
document ne présente aucun essai sur iPhone.

## Ce qui change pour l’utilisateur (iOS)

- Une icône **console avec « + »** apparaît dans la barre principale, juste
  après la première icône (Systèmes) et avant la recherche. Même cellule
  (32.r), même boîte d’icône (16.r), même teinte au repos et sélectionnée,
  même indicateur animé que les autres onglets. LB/RB (et Q/E au clavier)
  passent Systèmes → Consoles → Recherche → … L’onglet n’existe que sur iOS
  et n’est pas masquable (aucune ligne dans Réglages › Général). Le bouton
  porte un libellé d’accessibilité traduit (« Ajouter des consoles »), comme
  désormais chaque onglet (nom déjà traduit de l’onglet).
- Le corps de l’onglet est la page des consoles intégrées, sans barre de
  titre, sous l’en-tête : bibliothèque de NeoStation (dossiers des consoles,
  déplacement d’une bibliothèque), puis les 17 consoles du moteur intégré.
  Chaque console indique sa place dans le menu principal :
  - « Dans le menu principal : Sega Genesis » (aucun bouton d’ajout) ;
  - « Masquée dans le menu principal : … » avec **Afficher dans le menu
    principal** ;
  - sinon **Ajouter au menu principal** ;
  - « Non incluse dans cette version de NeoStation » quand aucun cœur de la
    console n’est dans l’IPA (`availableCores` du pont) : l’ajout est alors
    désactivé.
  Import de jeux et Habillages restent sur chaque console.
- L’ajout est immédiat : la console apparaît dans le menu principal et dans
  Réglages › Systèmes, triée selon les réglages de tri existants, et la page
  se met à jour d’elle-même (elle suit le fournisseur de configuration).
- Réglages › Dossiers n’a plus l’entrée « Consoles intégrées » :
  `directories_settings_content.dart` est de nouveau, octet pour octet, la
  version revue `a5650b9b` (Rescanner, Ajouter/Retirer un dossier, dossier
  des données, ES-DE inchangés).
- Pas d’action « retirer » : le masquage reste dans Réglages › Systèmes.

## Fonctionnement

- **Identité des onglets** : `NavTab.consoles` est ajouté à la fin de l’enum
  (index 6, `AppTabs.consoles`) ; les index 0 à 5 ne bougent pas. L’ordre
  d’affichage, qui est aussi celui de LB/RB, est `navTabDisplayOrder`
  (`systems, consoles, search, achievements, scraper, settings, library`).
  `visibleNavTabs` suit cet ordre, `cycleNavTab` porte le cyclage (testable),
  et la cellule AirPlay suit le rang d’affichage : toujours juste après la
  recherche (après Consoles si la recherche est masquée).
- **Ajout** (`lib/services/libretro_main_menu.dart`) : une console est
  « présente » dès qu’un système détecté la représente, quel que soit son
  nombre de jeux. Le doublon se juge par console matérielle, d’après les
  liaisons de `LibretroCoreCatalog` : Genesis rend la Mega Drive présente,
  Famicom la NES, Neo Geo/CPS l’arcade ; la Sega Pico, liée à la Mega Drive
  seulement pour son cœur et ses réglages, n’est pas comptée. L’ajout
  enregistre le système d’import de la console par les API publiques
  existantes (`SystemRepository.addDetectedSystem`, insertion qui ignore un
  doublon, puis `refreshDetectedSystems`). Aucun scan, aucun dossier, jeu,
  fichier, réglage de système ou de tri n’est touché, et rien n’est supprimé.
- **Persistance** : le scanner (verrouillé, inchangé) ne garde que les
  systèmes ayant des jeux. Les consoles ajoutées sont donc aussi mémorisées
  dans SharedPreferences (`libretro_main_menu_v1`, identifiants de console,
  comme les choix de cœur par jeu). Un gardien attaché par `AppScreen` (le
  démarrage `main.dart` est verrouillé) remet une console mémorisée dès
  qu’un scan complet (dont celui du démarrage), l’actualisation d’un système
  ou le retrait du dernier dossier l’a retirée, en conservant son masquage
  de Réglages › Systèmes. Il agit au passage occupé → inactif du
  fournisseur et quand l’ensemble des consoles manquantes change ; un même
  ensemble n’est pas retenté avant le scan suivant (pas de boucle si la base
  refuse l’écriture). Il n’attend aucune entrée-sortie de préférences ou de
  fichier sur ce chemin.
- **Contrôleur** : la page pousse sa propre couche de navigation (comme les
  succès) ; LB/RB y changent d’onglet, sauf pendant un import, une action de
  bibliothèque ou un ajout, pour ne pas détruire la page en cours
  d’opération. Les messages de fin restent affichés si l’on change d’onglet
  au toucher (messager et langue capturés).

## Textes (douze langues, `LibretroLocale`)

Nouvelles clés en fin de chaque carte : `consolesTab`, `addToMainMenu`,
`showInMainMenu`, `inMainMenu` `{systems}`, `hiddenInMainMenu` `{systems}`,
`consoleAdded` `{console}`, `consoleAddFailed` `{error}` (détail technique
séparé), `consoleSystemUnknown`, `consoleUnavailable`. Valeurs reformulées :
`setupLibraryIntro` (assistant : « plus tard depuis l’icône console avec + de
la barre du menu principal, ou dans les réglages des dossiers »),
`skinManageFooter` (pied de la page Habillages en jeu, clé native inchangée)
et `embeddedConsolesIntro`. `embeddedConsolesSubtitle` n’est plus lue ;
elle est conservée pour ne pas gêner les autres paquets de la 440 et peut
être retirée à l’intégration.

## Hors champ (inchangé)

Aucun des dix fichiers verrouillés de bibliothèque, aucun fichier
`native_sha256`, aucun cœur, pont natif, helper JIT ni routage de lancement.
Sauvegardes, états, BIOS et habillages (`Documents/Libretro/*`) ne sont pas
touchés. Aucune migration SQLite ni champ `ConfigModel`. Seul le texte de la
clé native `skinManageFooter` atteint le menu en jeu.

## Vérifications

Exécutées sous Windows (Flutter 3.47.2, Python 3.12) :

- `test/nav_tabs_test.dart` (nouveau) : index canoniques, ordre iOS,
  absence hors iOS, non masquable, LB/RB avec bouclage et onglets masqués,
  libellé dans les douze langues et sélection du chinois traditionnel.
- `test/main_menu_tab_strip_test.dart` (étendu) : cellule Consoles après
  Systèmes et avant Recherche, même taille, AirPlay entre Recherche et
  Succès pour chaque combinaison masquée, indicateur aligné, icône manette
  + « + » dans la teinte de l’onglet.
- `test/libretro_main_menu_test.dart` (nouveau, base SQLite et fournisseur
  réels) : ajout immédiat sans jeu, double ajout sans écriture, règle par
  console matérielle, scan complet puis remise avant le tour suivant,
  actualisation d’un système, masquage conservé, relance (nouveau
  fournisseur, préférences relues, scan de démarrage), tables
  `user_roms`/`user_rom_folders`/`user_system_settings`/`user_config`
  inchangées, console masquée ré-affichée, système inconnu refusé, écriture
  refusée sans mémorisation, pas de boucle, cœurs absents de l’IPA.
- `test/libretro_consoles_tab_test.dart` (nouveau) : page sans barre de
  titre sous l’en-tête, ajout et message, console déjà présente via un autre
  système, console masquée, rafraîchissement en direct, Habillages, LB/RB et
  leur blocage pendant un ajout, page poussée inchangée, douze langues.
- `test/libretro_frontend_ui_contract_test.py` : l’ancien contrat
  (entrée dans des marqueurs `embedded_consoles` de Réglages › Dossiers) est
  remplacé par celui de la 440 : fichier des dossiers identique à
  `a5650b9b`, onglet ajouté en fin d’enum et affiché après Systèmes, page en
  mode barre principale, ajout par `LibretroMainMenu`.

Contrôles à faire sur iPhone (non démontrés ici) : rendu de l’icône dans
chaque thème (clair, sombre, OLED, personnalisé), place de la pilule sur le
plus petit iPhone en paysage et sur iPad, LB/RB à la manette, ajout d’une
console sans jeu puis relance à froid et mise à jour SideStore, sans
clignotement visible du menu principal pendant le scan de démarrage,
console masquée restant masquée après relance, import depuis l’onglet vers
la bibliothèque existante, actions de bibliothèque, page Habillages et son
pied de page traduit, absence de l’entrée dans Réglages › Dossiers.
