# RewindBox Glacier · Kit Claude

Donner à Claude **ce dossier complet** et le texte de `PROMPT-CLAUDE.md`. La référence de disposition est `02-Reference/MENU-CIBLE.png`. L’application doit conserver l’organisation du menu présenté dans cette image. Le pack et le prompt sont des ressources d’intégration ; l’application actuelle est celle du dépôt.

## Le System Art

L’archive de `01-System-Art/` contient directement le dossier `rewindbox-glacier/`. À la racine de ce dossier se trouvent `theme.json`, `backgrounds/`, l’aperçu, le registre des alias, l’inventaire et les crédits. Le répertoire utilisé par le code existant est `<ConfigService.getUserDataPath()>/themes/rewindbox-glacier/`. Sous iOS avec l’emplacement par défaut, cela correspond à `Documents/user-data/themes/rewindbox-glacier/`. Un emplacement personnalisé peut différer. Le sélecteur de l’application découvre les dossiers déjà extraits ; la recette du prompt demande à Claude d’ajouter une installation embarquée et hors ligne.

## Étendue

84 profils de l’offre iOS, couvrant 106 identifiants visuels. Les 12 définitions de catalogue supplémentaires et les 3 collections sont également illustrées. Leur présence artistique ne change pas la liste des plateformes lançables. Pour les variantes de ROM hacks, les portraits reprennent le matériel de base et l’application fournit le nom de la variante. Les noms de fichiers des alias sont maintenus pour les installations existantes. Les illustrations sont des interprétations artistiques, y compris des symboles pour les systèmes logiciels ou les collections.

Les 8 glyphes de navigation sont fournis à part pour le chrome du menu. La galerie de référence comporte 18 exemples ; les deux planches de contrôle couvrent les 121 identifiants.

## Contrôle de distribution

Le vérificateur fourni utilise Python 3 et Pillow. Depuis la racine de ce kit :

    python3 04-Verifications/verify_distribution.py 01-System-Art/RewindBox-Glacier-System-Art.zip --inventory 04-Verifications/registre-art.json --expect-size 512

Le rapport fourni atteste le contenu de l’archive. Les essais de rendu Flutter et d’installation iOS font partie de l’implémentation demandée à Claude. Le menu final doit rester interactif au tactile et à la manette.
