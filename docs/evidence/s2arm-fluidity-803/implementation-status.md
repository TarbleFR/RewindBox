# Lot 0171 — état et limites de validation

## Périmètre

- 0170 : correction de la provenance du mode de présentation générique, avec retour explicite `S2A_RB_NATIVE_CADENCE=0` ajouté par 0171.
- 0171 : protocole de 180 s, menu générique, compteurs bornés, audio/GC, ledgers et parcours mémoire complet après le score.
- Nextendo : Core déjà compilé et authentifié du run 44753917742, source `8988ced5014dd23caae2eefac70b3d37f5a5b7f0`, à intégrer dans la même IPA.
- Aucun budget de textures/prélecture, ordonnanceur audio, pas de simulation ou traducteur de shaders modifié par 0171.

## Vérifications source

Le contrôle existant `tools/weak_link_decl.py check` a d’abord signalé trois déclarations faibles non enregistrées, déjà présentes à 0170. Leurs consommateurs ont un repli explicite ; les annotations manquantes sont ajoutées auprès des déclarations (`nvn_rb_route_read`, `s2a_rb_guest_input_release`, `s2a_rb_mkw_measure`). Le même contrôle passe ensuite : 31 symboles host enregistrés, aucun flag de liaison manuscrit. Le contrôle n’est ni modifié ni désactivé.

Les revues indépendantes couvrent les familles, les crochets de présentation, les métadonnées host, la mémoire et la concurrence du collecteur. Elles ont notamment corrigé l’identité amont confondue avec le moteur patché, les préférences confondues avec les réglages actifs, les rappels de minuterie périmés et l’arrêt pendant l’initialisation du banc. La lecture VM utilise l’API iOS déjà employée par le moteur, avec des adresses de 64 bits.

Le premier run 0171 (44771503834) a refusé l’interface avant compilation : le nouvel appel du banc n’était pas déclaré dans `S2ArmGuestABI.h`. La déclaration partagée est ajoutée et employée par le menu et le pont. Les deux fournisseurs NativeAOT restent des symboles internes recherchés par le collecteur ; leur conservation est exigée et la CI vérifie leur présence dans le framework final. Le contrôle d’exports existant n’est pas modifié ni contourné.

L’analyseur de comparaison a été appliqué à deux exports privés existants : [comparaison refusée](legacy-comparison-refused.json), car aucun ne porte les marqueurs du protocole. Aucune différence de performance n’est produite. Il ne s’agit ni d’un banc synthétique ni d’un test d’exécution du moteur.

## Statut du moteur compilé

| Étape | État |
| --- | --- |
| Correctifs et instrumentation dans les sources | Intégrés et relus ; application de 0171 sur 0170 et contrôle des déclarations faibles réussis |
| Compilation du moteur 0170 | Réussie sur macOS 15 et 26, run 44759330364 ; zéro avertissement sur ses lignes ajoutées |
| Compilation du lot 0171 | Réussie sur macOS 15 et 26, run 44772035018, source `342f534efc856eedeba9b085df291757bc942d41` ; zéro avertissement sur les lignes ajoutées |
| Pin et IPA privée 803 | Moteur authentifié ; contrôle du pin et livraison en préparation |
| Gain de fluidité, chaleur, son, attribution mémoire sur iPhone | Non observé ; il manque les nouvelles mesures appareil |
| Régression des deux autres jeux Switch 2 | Non observée avec ce lot ; état satisfaisant rapporté par le mainteneur |

Les suites Flutter/natives approfondies ne sont pas exécutées, conformément à AGENTS.md. Les contrôles obligatoires de configuration, ABI, signatures, identité et livraison restent actifs. Aucun avertissement nouveau sur les lignes ajoutées n’est accepté lors de la revue des journaux CI.

## Décisions qui attendent les données

Le poste compressé dominant, le taux d’usage de la prélecture et les trous audio réellement entendus ne sont pas encore attribués. Il n’est pas justifié de réduire arbitrairement un cache ou de changer une échéance audio avant ces relevés. Le mode endurance et les retraits/désactivations de familles sont des propositions classées dans [l’audit](audit-803.md). La première IPA instrumentée est une référence ; elle ne transforme pas les anciens essais non appariés en un avant/après.

## Preuve de compilation

[Identité moteur et artefact](engine171-build.json) : 171 patchs correspondent exactement au dépôt. La chaîne shaders `0be3f28548fd` et la charge NS2Pro sont identiques à la base 802. Les trois nouveaux exports sont présents dans le framework final. Les 12 avertissements par plateforme existaient dans 0170, sur des lignes inchangées ; aucun sur les ajouts 0170/0171. L’annotation Actions relative à Node.js existait également avant ce lot.
