# Compilation du core RPCS3 après les retours BO2, GOW3 et AC

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
`native_executed_now` vaut `false`. Seuls les deux modes MFC affectés seront
réexécutés sur Apple. Les 28 anciens modes de 378509e8 gardent aussi leur
origine et leurs archives authentifiées.

La recette du workflow `rpcs3-runtime592-core.yml` et le script de
compilation restent identiques à la recette historique. Les résultats de
compilation et les identités du binaire seront ajoutés après le véritable
succès et la vérification des octets téléchargés.

Les scénarios BO2 multijoueur, introduction GOW3 et torches AC restent à
rejouer sur iPhone. Les tests hôtes et la compilation ne démontrent pas leur
récupération. Le feedback couleur peut ajouter une copie par draw ; aucun
gain de FPS n'est revendiqué.
