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
| Pin et IPA privée 803 | Pin contrôlé par le run 44774890033 ; IPA 803 livrée en privé et vérifiée, run 44775472323 |
| Gain de fluidité, chaleur, son, attribution mémoire sur iPhone | Non observé ; il manque les nouvelles mesures appareil |
| Régression des deux autres jeux Switch 2 | Non vérifiée sur appareil avec 803 ; état satisfaisant rapporté sur les versions précédentes |

Les suites Flutter/natives approfondies ne sont pas exécutées, conformément à AGENTS.md. Les contrôles obligatoires de configuration, ABI, signatures, identité et livraison restent actifs. Aucun avertissement nouveau sur les lignes ajoutées n’est accepté lors de la revue des journaux CI.

## Décisions qui attendent les données

Le poste compressé dominant, le taux d’usage de la prélecture et les trous audio réellement entendus ne sont pas encore attribués. Il n’est pas justifié de réduire arbitrairement un cache ou de changer une échéance audio avant ces relevés. Le mode endurance et les retraits/désactivations de familles sont des propositions classées dans [l’audit](audit-803.md). La première IPA instrumentée est une référence ; elle ne transforme pas les anciens essais non appariés en un avant/après.

## Preuve de compilation

[Identité moteur et artefact](engine171-build.json) : 171 patchs correspondent exactement au dépôt. La chaîne shaders `0be3f28548fd` et la charge NS2Pro sont identiques à la base 802. Les trois nouveaux exports sont présents dans le framework final. Les 12 avertissements par plateforme existaient dans 0170, sur des lignes inchangées ; aucun sur les ajouts 0170/0171. L’annotation Actions relative à Node.js existait également avant ce lot.

## Livraison privée 803

La [livraison](../rewind803/delivery.json) provient de `c5422386b72ec4ea88b010dab3826075ee7e79f8`, run 44775472323, tentative 1. Les quatre pièces chiffrées, les reçus, les 97 images natives et les 10 identifiants de bundles concordent. [Identités exactes de S2Arm et Nextendo](../rewind803/s2arm-identity803.json). IPA : 333553734 octets, SHA-256 `d7d2cb41d3683bc20d804adfdf346aa3d12cf34abe3b55b83f5e669c9f90510b`.

La [revue de compilation application](../rewind803/application803-warnings.json) ne trouve aucun avertissement dans les cinq fichiers modifiés, soit 249 lignes ajoutées. Les sources des avertissements S2Arm ailleurs sont inchangées depuis 802 ; leur émission dans 802 n’a pas été vérifiée, son journal étant indisponible. Les diagnostics du moteur sont documentés [séparément](../rewind803/engine171-warnings.json). Le framework libretro recompilé a des relais générés par le linker différents mais équivalents : code principal et données identiques, mêmes destinations `_objc_msgSend`, avec UUID et signature différents. Le [classement binaire](../rewind803/libretro-image-difference.json) conserve les détails.

L’IPA a été remise en privé après vérification ; la clé privée de transport a été supprimée après conservation des reçus. Aucun essai physique iPhone, aucune validation de partie, aucun gain de FPS ou de chaleur n’est déclaré. La comparaison 803/802 selon le protocole reste indisponible : 802 n’avait pas ce protocole. 803 constitue la première référence instrumentée.
