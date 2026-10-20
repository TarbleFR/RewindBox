# Catalogue HD : RAR natif et téléchargements publics — 20 octobre 2026

Ce cycle ajoute le lecteur RAR et les résolveurs publics nécessaires pour télécharger davantage de packs depuis l’application. Il conserve les fichiers originaux, leurs tailles, SHA-256 et crédits, ainsi que les identités et plans des packs déjà validés. Les anciennes identités non attestées de nouveaux candidats sont corrigées à partir des archives et des publications des auteurs. NeoStation ne réhéberge ni ne reconstruit les archives.

Le catalogue `2026-10-20.28541bbfe23e` atteint **418 familles distinctes téléchargeables et installables avec le nouveau client**, contre 164 téléchargements directs auparavant. Il contient **503 profils**, dont **85 variantes** qui ne créent pas de familles supplémentaires : 271 packs complets, 73 partiels et 74 packs d’interface.

Les 231 anciens profils manuels vérifiés, représentant 191 familles, conservent leurs archives, identités et plans. Ce cycle ajoute 63 familles réellement nouvelles : **61 packs RAR et deux ZIP originaux**. Les anciennes versions peuvent télécharger 237 familles ; les 181 autres demandent les nouvelles capacités natives de la **Build 498**. Les 1 086 références antérieures sont conservées, pour 1 088 références au total.

Les huit nouvelles exécutions d’archives fournissent 85 observations exactes dans 13 artifacts non vides. Le registre canonique garde 682 IDs uniques ; 61 anciennes observations sont remplacées, et 69 observations historiques sont conservées sans modification. Dix échecs natifs et quatre archives sans édition attestée restent hors du total installable. Sept targets USA corrigés ont leur propre nouvelle vérification ; six autres profils restent limités à l’édition réellement installée. Shadow Hearts Covenant est limité au disque 1.

Bilan détaillé : [compteurs et exclusions](evidence/hd-direct400-catalogue-2026-10-20.json), [artifacts CI et raw exacts](evidence/hd-direct400-ci-artifacts.json).

## Implémentation et rétrocompatibilité

`NeoTextureRAR.h` utilise un sous-ensemble en lecture seule de libarchive **v3.8.10**, dont la provenance, les empreintes et les licences sont conservées dans `packages/neo_texture_catalog/ios/ThirdParty/libarchive/`. Ses symboles sont préfixés et ses allocations de décodage partagent un budget plafonné à **256 Mio**, ou à la limite inférieure demandée. Les lecteurs ZIP/7z existants restent distincts.

Le lecteur refuse les chemins dangereux, liens, doublons, tailles excessives et archives incomplètes. Les tailles cumulées déclarées sont contrôlées avant le décodage solide ; celui-ci progresse par blocs et reste annulable. Les CRC32 et BLAKE2 déclarés sont vérifiés avant validation des fichiers. L’extraction passe par le staging et les protections du même installateur. Pour un import RAR ARMSX2, une expansion privée est remise à son installateur habituel : confirmation de région/serial/CRC et restauration en cas d’échec sont conservées. Les fichiers exécutables ne sont pas installés.

Les résolveurs natifs couvrent les fichiers publics Google Drive, Yandex et MEGA, y compris un fichier précisément sélectionné dans un dossier MEGA. Ils utilisent les voies publiques normales, sans compte enregistré ; une restriction, un quota ou un défi arrête la tentative. Les liens HTTPS ordinaires, GameBanana et Dropbox utilisent le téléchargement direct. Le corps reçu doit correspondre à la taille et au SHA-256 attendus avant toute installation.

Les téléchargements résolus gardent uniquement une partie du corps pour reprendre avec `Range`, dont `Content-Range` est contrôlé. Pour MEGA, cette partie reste chiffrée ; le fichier complet est déchiffré sur place en mémoire bornée, puis vérifié. L’état de reprise ne conserve aucune URL CDN signée ni clé AES dérivée ; le catalogue conserve le lien public original de MEGA et sa clé publique de partage. Une pause conserve les octets réutilisables ; une annulation supprime le téléchargement. Les callbacks tardifs du résolveur ne lancent pas de transfert.

Le manifeste conserve un pack manuel vérifié et ajoute un descripteur `download.in_app`. Seul le nouveau client le transforme en téléchargement disponible, après validation des URL et de l’égalité **format, nom, taille et SHA-256** avec le fichier vérifié. Un descripteur invalide conserve le repli manuel. Les anciens clients gardent leur import manuel existant ; pour RAR, ils conservent le lien vers la page auteur et n’acquièrent pas le nouveau lecteur par une mise à jour du manifeste. Le cache garde le document source pour sa revalidation. Ces changements de livraison ne créent pas de nouvelles familles dans le compteur.

## Preuves natives

| Source / exécution | Résultat retenu |
|---|---|
| `2a7889e7` — [39456486483](https://github.com/TarbleFR/neostation-ios/actions/runs/39456486483) | Linux : 38 contrôles RAR, 103 contrôles de l’installateur et rejeu de 87 profils réussis. Les programmes macOS résolveurs, MEGA et compatibilité réussissent individuellement ; leur étape groupée échoue ensuite à la compilation de la fixture Store, sur une faute de macro de test. |
| `b9629075` | Correction de cette macro ; ce premier arrêt ne constitue pas une réussite du test Store. |
| `07923d59` — [39456927008](https://github.com/TarbleFR/neostation-ios/actions/runs/39456927008) | 169 contrôles Foundation, compilation et liaison de 36 sources pour `arm64-apple-ios17.4`, puis six téléchargements et installations réels réussis. Malgré la sélection `store,sdk,network`, la fixture Store était encore regroupée avec les fournisseurs et a été ignorée : cette exécution ne la valide pas. |
| `2a75a27b` — [39459576086](https://github.com/TarbleFR/neostation-ios/actions/runs/39459576086) | Store est séparé du groupe fournisseurs. Son exécution révèle une course : le dossier temporaire RAR ARMSX2 peut rester visible lorsque la completion arrive. Échec conservé, puis nettoyage avancé avant la completion. |
| `82819322` — [39460393849](https://github.com/TarbleFR/neostation-ios/actions/runs/39460393849) | Le nettoyage passe les 120 contrôles Store ; le programme Foundation suivant échoue ensuite sur un défaut de durée de vie dans les callbacks de progression. La correction supprime la capture devenue invalide ; cette exécution partiellement échouée ne valide pas la candidate finale. |
| `d8a11a7dc2f6273dc2a845fb076049301cd4e9c2` — [39461533070](https://github.com/TarbleFR/neostation-ios/actions/runs/39461533070), job `118761956389` | Réussite finale : résolveurs **223/0**, MEGA **76/0**, compatibilité **20**, Store **125/0**, Foundation **169/0**, compilation et liaison de **36 sources** pour `arm64-apple-ios17.4`. Les contrôles Store incluent le nettoyage et la durée de vie des callbacks corrigés. |

La fixture Store couvre notamment la reprise chiffrée, un serveur ignorant `Range`, un intervalle erroné, un SHA incorrect, une réponse HTML, un dépassement de taille, un refus HTTP 403, l’annulation du résolveur et les imports RAR Dolphin/ARMSX2. Elle vérifie aussi la conservation du pack précédent sur les échecs contrôlés. Les **125 contrôles réussis appartiennent uniquement à la dernière exécution**.

Les six téléchargements antérieurs restent une preuve de leur chemin HTTP/résolution/chiffrement : le préfixe Store correspondant, avant `Install`, est identique octet pour octet entre `07923d59` et le correctif final (SHA-256 `4f36e5ae26d6a40fb99ebd8a7fdab0a705455f3bd05a734fd0491ba26c42a95f`). Les corrections de nettoyage ARMSX2 sont couvertes par la nouvelle preuve Store/SDK, sans leur attribuer les anciens résultats réseau.

## Six fichiers originaux réellement téléchargés

Le test utilise le `NeoTexturePackStore`, `NSURLSession` et les adaptateurs Dolphin/PPSSPP de production, avec le User-Agent `NeoStation-iOS`, dans des dossiers temporaires. Aucun nouveau profil ni hôte de repli n’est essayé après un refus. Les six lignes ont `status: ok`, avec taille et SHA-256 vérifiés par le Store ; le rapport en conserve les empreintes exactes.

| Projet | Hébergeur / voie | Archive, octets | Fichiers installés |
|---|---|---:|---:|
| NSMB Wii — titre HD, TJShah | GameBanana | 40 935 | 1 |
| NSMB Wii — interface Shield x2, Moukrea | Google Drive | 1 492 083 | 72 |
| Paper Mario TTYD — boutons Xbox 360, jvook | MEGA, fichier de dossier | 311 694 | 25 |
| Digimon World Re:Digitize — interface HD | Dropbox | 1 095 028 | 43 |
| God of War: Ghost of Sparta — HUD, SkyDR4GON | HTTPS direct | 776 517 | 16 |
| Crash Nitro Kart — HD fixes, John30011887 | MEGA, fichier public | 3 543 762 | 245 |

Preuve conservée : [rapport natif réseau](evidence/hd-direct400-native-network-2026-10-20.json). L’entrée reproductible est `tools/textures/research/direct400-network-probes.json`. Le programme réseau écrit les échecs éventuels dans le JSON sans faire échouer son processus : **la preuve est le statut de chaque ligne**, pas seulement le résultat vert du job.

## Limites

RAR4 non solide et RAR5, dont les archives solides couvertes par les fixtures, sont pris en charge. **RAR4 solide, archives chiffrées, volumes RAR multiples et fichiers répartis entre volumes sont refusés** ; aucun mot de passe ni programme externe n’est utilisé. Un paquet concerné ne devient pas téléchargeable par cette capacité.

Yandex est couvert par les fixtures du résolveur, sans nouveau téléchargement intégral de son gros fichier dans les six sondes ci-dessus. Les contrôles réseau prouvent le téléchargement, l’intégrité et l’installation sur macOS, pas le rendu d’un jeu. Le rapport indique `activated: true` uniquement pour Crash Nitro Kart ; les cinq autres lignes ne prouvent pas une activation réussie. Toutes indiquent `physical_device_rendering: false`.

La liaison iPhone utilise les sources natives et le SDK réel, avec un stub de déclaration Flutter pour ce contrôle isolé. Elle ne constitue ni une compilation complète de l’application ni un essai sur appareil. **Aucun test physique iPhone, rendu en jeu ou nouvel IPA n’est attesté par ce cycle.** Les limites régionales, la couverture partielle et les contraintes mémoire des packs restent celles documentées par les sources.
