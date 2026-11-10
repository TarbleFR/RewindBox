# Core RPCS3 compilé après les retours BO2, GOW3 et AC

Le mainteneur demande la compilation du nouveau core. Le lot préparé dans
`17cc8faf` a été restauré depuis son export authentifié, en conservant les
documents de livraison privée603 ajoutés depuis sa base `f41eb5ef`.
La compilation concerne uniquement le core iPhone ; aucune IPA ni release.

Les correctifs de redémarrage SELF, de sauvegarde, de petits sommets et de
feedback couleur sont conservés. La compilation complète a révélé une
ambiguïté dans le réveil SPU : `named_thread<spu_thread>` possède deux bases
avec une méthode `notify`. L'appel est maintenant qualifié
`spu->cpu_thread::notify()`. Ce chemin notifie l'état CPU puis le latch hôte
via `thread_ctrl::notify`. Le harnais reproduit les deux parents et extrait
les vrais corps des notifiers ; l'appel non qualifié reproduit l'erreur.

Le patch canonique est
`70d694bb3ef812b87b8839e53335376028aa16476893512d012b77ef1952fd79`.
Une matérialisation neuve vérifie 326 postimages ; le delta inverse restaure
exactement les huit chemins du core de référence 378509e8. Les 318 autres
postimages restent identiques. L'alias SPU est limité au nouveau SHA exact ;
les six alias historiques et les identités PPU `a987639e9f838d1c` et
SPU `477a3fa442d27917` sont conservés.

## Tentatives conservées et contrôles réutilisés

| Source | Résultat réel |
|---|---|
| `82e318a1`, run 41112827942 | Échec de la validation source : `/var` est un lien macOS. Aucun test natif ni core compilé. Les répertoires temporaires sont maintenant résolus avant `git apply`. |
| `532ca40e`, run 41113741373 | Les 12 modes Apple passent ; la validation syntaxique iOS complète détecte ensuite l'appel SPU ambigu. Aucun core produit. |

Les 12 rapports de 532ca40e, leurs traces et les véritables sources capturées
par Clang 22.1.8 ARM64 sont authentifiés dans l'archive d'origine
`13005716946` (SHA256
`14bf88f0c5fb2698b82656932c174886b42778d55c562a38c17f5c1742a4bb74`).
Les dix programmes inchangés sont régénérés sans compilation et doivent
rester identiques aux captures Apple. Leur origine reste 532ca40e et
`native_executed_now` vaut `false`. Seuls les deux modes MFC affectés ont été
réexécutés sur Apple dans la tentative finale. Les 28 anciens modes de 378509e8 gardent aussi leur
origine et leurs archives authentifiées.

La recette du workflow `rpcs3-runtime592-core.yml` et le script de
compilation restent identiques à la recette historique.

## Livraison du core vérifiée

La source `a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a` réussit dans le
[run 41117115264](https://github.com/TarbleFR/RewindBox/actions/runs/41117115264),
job `124274114161`, tentative 1. Les deux modes MFC passent en normal et
ASan/UBSan ; dix autres modes sont réutilisés depuis 532ca40e. Aucun des 28
modes historiques n'est rejoué. Une seule tentative atteint la production
du binaire ; les deux précédentes s'arrêtent avant cette étape.

| Élément vérifié | Valeur |
|---|---|
| Archive core | Artefact 13007148559, 29 263 531 octets |
| SHA256 archive | `b260bb4fa48b72ff889d6e9c4eb061591676b18e12427c0160a44974c9ff2b07` |
| `libRPCS3Core.dylib` | 77 424 528 octets, iOS ARM64, ABI 30, exactement 88 exports |
| SHA256 dylib | `f2f167af5cfa7889e76af150b6c9f02e6a19b7f3e881de0397bcafe185dbe19a` |
| Diagnostics | Artefact 13006694440, SHA256 `3663b28d81f196509618a15a8cf18c61b39ac8d582ee800521a96f27f129284e` |
| Durée de compilation du core | 686 secondes |
| Durée totale du job | 1 262 secondes |

L'archive téléchargée et ses diagnostics passent les contrôles indépendants :
empreintes GitHub, CRC ZIP, vrais en-têtes Mach-O, install name, 88 exports,
identités, 326 postimages et fermeture des entrées source. Les rapports,
traces et sources C++ réellement capturées par le compilateur sont vérifiés,
avec une nouvelle lecture de l'archive d'origine 532ca40e. Le vérificateur
ne compile ni n'exécute de programme natif. Le contrôle CI du chargement
passif est une validation Mach-O ; il ne constitue pas un essai de jeu.

Le checkout a subi une remise à zéro de connexion, puis a réussi lors de la
reprise automatique. Les erreurs transitoires sont conservées dans le vrai
journal ; le run et toutes ses étapes finales sont réussis.

[Télécharger RewindBox-RPCS3Core-a4d0c9a5.zip](https://chatgpt.com/library?file_id=libfile_3c054d49988c8191a7296bfcc5c4a67c&account_id=personal).
Le fichier contient le core et ses identités ; aucune IPA ni release publique.
Les preuves texte originales sont conservées sous
`docs/evidence/rpcs3-device601-20261030/apple-core/`, avec le vérificateur
`test/verify_rpcs3_device601_core_archive.py`.


Les scénarios BO2 multijoueur, introduction GOW3 et torches AC restent à
rejouer sur iPhone. Les tests hôtes et la compilation ne démontrent pas leur
récupération. Le feedback couleur peut ajouter une copie par draw ; aucun
gain de FPS n'est revendiqué.
