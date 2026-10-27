# MeloNX 562 — clavier Switch et boutons L3/R3 (27 octobre 2026)

Demandes d'un utilisateur (Discord, transmises par le mainteneur) :

1. « Ajouter un clavier intégré : le jeu plante quand il demande de taper au
   clavier » (capture : Hogwarts Legacy, écran « Finalise your character »,
   saisie du nom).
2. « Une option pour activer R3/L3 sur la manette virtuelle. »

## 1. Clavier : cause (établie dans les sources)

Un jeu Switch qui demande du texte ouvre l'applet clavier
(`SoftwareKeyboardApplet`). MeloNX le confie à `WindowBase.DisplayInputDialog`
(`Ryujinx.Library`, révision épinglée `13700519`), qui appelle
`AlertHelper.ShowAlertWithTextInput` :

- la requête JSON (`Title`, `Message`, `Placeholder`, `CallbackId`) part par le
  registre de callbacks du moteur, sous le nom `show_text_input` ;
- le thread HLE attend ensuite (`inputReceived.Wait()`) que l'hôte invoque
  `show_text_input_result_<CallbackId>`.

L'app MeloNX autonome enregistre ce callback (`AlertHandlers.swift`).
RewindBox ne l'avait jamais fait : `CallbackRegistry.Invoke` renvoyait faux, la
réponse n'arrivait jamais et le jeu restait bloqué sur son clavier. Le même
chemin sert au clavier « inline » (`NativeDynamicTextInputHandler`) et au nom
d'un amiibo.

## 2. Corrections (hôte uniquement, aucun moteur reconstruit)

- `MeloNXTextInput.swift` (nouveau) : enregistre `show_text_input` une fois par
  processus via les exports `RegisterCallback`/`InvokeCallback`, déjà présents
  dans le moteur. Il affiche un champ de texte UIKit au-dessus du jeu (titre et
  sous-titre du jeu, texte guide en indication). **OK** envoie le texte en
  UTF-8 ; **Annuler** envoie une réponse vide, et le moteur garde alors le texte
  initial du jeu, comme l'app autonome. Les requêtes passent l'une après
  l'autre et attendent la fermeture du menu en jeu. Toutes sont répondues
  avant chaque arrêt de session, pour qu'aucun thread du jeu ne reste bloqué.
  Le texte saisi n'est jamais écrit dans le journal, seulement sa longueur.
- `MeloNXRuntimeAPI.swift` : les deux exports sont facultatifs (un moteur plus
  ancien se charge toujours).
- Menu en jeu : **Boutons des sticks (L3/R3) : Activé/Désactivé**. C'est le
  réglage existant du Melo-Controller (« Show Stick Buttons (L3/R3) » de l'app
  autonome, clé `rewindbox.melonx.stickButton`). Il affiche L3 et R3 dans les
  deux orientations. Leur position se règle avec « Modifier les commandes
  tactiles ». La manette tactile est reconstruite aussitôt.
- Chaînes « Text input » et « Stick buttons (L3/R3) » en 12 langues
  (`build-utils/melonx/ui-strings.json`).

## 3. Vérifications (sans iPhone)

`test/melonx_text_input_test.py` :

- partout : le protocole contre les sources MeloNX et Melo-Controller
  épinglées, les signatures, le câblage (attache aux commandes, réponse avant
  chaque arrêt), la clé L3/R3 et les traductions ;
- sur macOS : le vrai `MeloNXTextInput.swift` s'exécute dans UIKit, sur
  simulateur iOS, contre un double du registre (19 contrôles) : texte UTF-8
  transmis, Annuler, file d'attente, attente du menu, fermeture de session,
  requête tardive, requête illisible, texte absent du journal.

Run hôte `40484359276` sur `9b40129f` : vérification de types avec le SDK
iPhone, double de l'ABI native, présentation UIKit, journal de performance,
parité et sonde clavier réussis (45 + 19 contrôles).

`melonx-display` échoue au même commit sur
`melonx_presentation_widgets_test.dart`. L'échec n'est pas causé par ce
changement : le même test échoue déjà au commit précédent (`9b40129f^`) dès
qu'il tourne après `melonx_display_test.dart`, comme dans ce workflow ; seul
dans une copie neuve, il passe. Ce test ne fait pas partie de la livraison.

Aucun jeu n'a tourné : le clavier dans Hogwarts Legacy et les boutons L3/R3
restent à confirmer sur iPhone.

## 3 bis. Livraison privée 562

Le numéro 561 est la livraison RPCS3 Core 561 d'une autre session
(`5dd6a5ae`). Celle-ci est donc la **562** : l'arbre produit 561 livré (Core
RPCS3 561, moteur MeloNX 558, tous les autres fichiers) avec seulement les
fichiers MeloNX de `9b40129f` (`.github/diagnostics/melonxinput562_tree.py`).
La recette 561 tourne inchangée dans une vue de l'arbre 561 (`as_561`, qui
régénère aussi les chaînes du contrôleur), et le run hôte `40484359276` est
lié à l'arbre épinglé (`validate_melonx_input562_ipa.py`).

## 4. Protocole iPhone

1. Hogwarts Legacy, création du personnage : la saisie du nom doit afficher
   un champ de texte. Taper le nom puis OK : le jeu doit continuer.
2. Menu (⋯) → « Boutons des sticks (L3/R3) » : Activé. L3 et R3 apparaissent ;
   les tester dans un jeu qui les utilise.
3. En cas de problème, exporter `app.log` : lignes `[MeloNX:launch] textInput …`.
