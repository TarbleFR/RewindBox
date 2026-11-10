# RewindBox — approfondissement RPCS3 après les retours du build 595

Trois changements supplémentaires sont intégrés au patch canonique, après le
lot local `543996ad1e79330fda81d086af27566dce0fd79e`. Le dernier état distant de
`Claude` a été revérifié pendant ce travail :
`c0df3394d81d957eb7b28c85802278b69cc0f71b`. Le checkout est isolé. Aucun push,
Core, IPA ou release n'est produit ; les recettes et les binaires épinglés restent
historiques. Ces sources ne sont donc pas présentes dans l'IPA 595 testée.

## Modifications réelles

### Corriger la vue des textures temporaires Vulkan

La clé du cache décrit le contenu de l'image, mais n'inclut pas le remappage de
ses canaux. Une requête réutilisant ce contenu avec un autre remappage pouvait
recevoir la vue créée pour la requête précédente. Le chemin Vulkan iOS
`create_temporary_subresource` sélectionne maintenant la vue correspondant au
remappage courant, en conservant le format de la vue mise en cache.

L'image et ses copies restent réutilisées. `get_view` possède déjà un accès
rapide pour la dernière vue ; la répétition du même remappage n'alloue rien.
Les vues appartiennent toujours à l'image. Les invalidations, les mises à jour
dynamiques, le retour nul en cas d'échec et la libération de fin de frame suivent
les mêmes chemins. Aucun verrou ou barrière GPU n'est supprimé. Les cinq sites
d'appel Vulkan passent par le type concret corrigé.

Le test reproduit le mauvais résultat avant la correction et vérifie la bonne
sélection après. Cela établit un défaut réel de cache, **pas encore la correction
sur iPhone des armes de BO2 ou des torches d'Assassin's Creed**.

### Réutiliser le tampon d'expirations du timer SPU

Le worker iOS du décrémenteur conserve son vecteur de travail entre les réveils.
Il le vide après les notifications, hors verrou, au lieu de détruire son
allocation à chaque itération. Le vecteur contient des entrées triviales, sans
référence propriétaire vers un thread. Sa capacité maximale reste retenue
jusqu'à l'arrêt du worker : 24 octets par emplacement dans l'adaptateur testé.

La réservation demeure avant la compaction de la file. Un échec d'allocation ne
consomme donc pas d'expiration. L'ordre des publications, des notifications, des
entrées restantes et des échéances est conservé. Les identités JIT PPU/SPU restent
inchangées grâce à l'alias limité à l'empreinte exacte de ce fichier ; une autre
modification ou un autre chemin ne bénéficie pas de cet alias.

### Réduire le tampon de couverture des surfaces RSX

Dans le repli qui élimine les surfaces entièrement recouvertes, le marquage iOS
utilise un bit par octet invité au lieu d'un octet. Le traitement applique des
masques sur des mots de 64 bits, en préservant le parcours, le découpage des lignes
et l'ordre des invalidations. Le chemin desktop est identique après prétraitement.

Pour une portée d'adresses de 4 Mio, le tampon passe exactement de **4 194 308 à
524 296 octets**, sentinelle incluse. Il s'agit de la taille de ce tampon lorsque
ce repli est exécuté, pas d'une baisse mesurée de la mémoire du jeu. Ce chemin
concerne la collecte de surfaces recouvrantes ; son activation dans les captures
fournies n'est pas établie. Le garde existant de portée inférieure à 64 Mio reste
actif, avec vérification des bornes avant le marquage.

## Vérifications effectuées

Six nouveaux modes natifs passent sous GCC 13.3, Linux x86_64 : mode optimisé et
AddressSanitizer/UndefinedBehaviorSanitizer pour chacun des trois changements.
Les assertions sont actives. Les appels Vulkan, le planificateur et les objets
de surface périphériques sont adaptés au test hôte ; aucune exécution GPU,
ARM64/iPhone ou validation LeakSanitizer n'est revendiquée.

| Chemin | Résultat par mode |
| --- | --- |
| Remappage | 373 277 contrôles, dont 373 248 requêtes couvrant 20 736 remappages valides × neuf opérations × couleur/profondeur ; 373 230 mauvaises sélections avant, zéro après |
| Durée de vie des vues | 373 278 créations et destructions ; aucune allocation sur répétition du même remappage ; mêmes allocations d'images et copies de contenu ; recyclage du mapping natif vérifié |
| Timer | 210 matrices, réentrance et arrêt, deux échecs d'allocation initiale et un échec de croissance tardive ; 47 752 notifications, 6 145 tokens périmés rejetés, aucun callback sous verrou |
| Allocations du timer | 128 réveils stables : 128 → 1 allocation ; 1 024 réveils variables : 768 → 4 ; mêmes ordres de publication et échéances |
| Couverture | 391 754 comparaisons de lignes et 10 128 cas de géométrie ; mêmes invalidations dans le même ordre avant/après et sur desktop |
| Bornes de couverture | Intervalles sur bitmap vierge, lignes vides, frontières 63/64/65/127/128/129, trous entre mots, portée 64 Mio − 1 et adresses invitées proches de la limite 32 bits |
| Canonique | 314 postimages vérifiées depuis les préimages amont ; cinq modifiées, 309 inchangées ; diff inverse identique à la base |
| JIT | 40 entrées physiques et empreinte LLVM externe inchangée authentifiées ; PPU `a987639e9f838d1c`, SPU `d070cb361bdef607` |

Une seule invocation CMake en mode script a vérifié les identités et les rejets
de chemins/empreintes inconnus. Aucun Core n'a été configuré ou compilé. Les six
modes du lot précédent sont réutilisés après authentification de leurs programmes
générés et de toutes leurs entrées exactes ; ils ne sont pas relancés.

Les mesures synthétiques sont conservées intégralement, y compris les cas
défavorables. Pour le timer à six entrées expirées, la médiane hôte passe de
30,48 à 18,99 ns ; sans entrée expirée, elle passe de 16,82 à 17,90 ns. Quatre des
douze cas du timer ont une médiane plus lente. Pour la couverture de 64 Kio en
lignes de 16 octets, le temps passe de 83,10 à 85,37 µs ; pour 1 Mio en lignes de
256 octets, de 511,47 à 89,91 µs. Un des neuf cas de couverture est plus lent.
Ces derniers chronométrages ont partagé l'hôte avec la validation sanitizer :
leur amplitude est indicative. Les réductions de taille et d'allocations sont
déterministes dans les scénarios testés ; aucun gain de FPS n'en est déduit.

Le premier compilateur du test de remappage a signalé une initialisation partielle
dans le décodeur existant extrait. La suppression du seul avertissement
`missing-field-initializers` est limitée à ce helper dans le harnais ; son premier
échec est conservé. Aucun diagnostic de production n'a été désactivé. Les premiers
essais du harnais de couverture ont également nécessité une correction de
frontière d'extraction, l'alias `usz` et le formatage du pilote de test. Les
résultats finaux correspondent aux sources et aux harnais actuels.

## Symptômes persistants et pistes suivantes

Les observations du build 595 restent celles du rapport précédent. BO2 conserve
les défauts armes/avant-bras et les saccades signalés ; AC conserve le scintillement
des torches et les baisses de débit. La correction de remappage est pertinente
pour les contenus de texture réutilisés, mais son lien avec ces scènes reste à
vérifier sur appareil. Elle ne supprime pas les coûts de streaming et de soumission.

Pour GOW3, les traces existantes établissent une attente RSX sur `0x60300510`,
attendu `0x6F0E`, observé `0x6F0D`. Elles montrent encore des opérations SPU pendant
le gel ; elles ne prouvent pas un hot-spin GETLLAR ni l'origine du signal absent.
Les chemins existants de polling atomique, de traitement des requêtes GPU et de
restauration MFC ont été relus. Aucun changement du producteur n'est justifié
par ces seules données. Le label n'est pas forcé et les réglages du jeu ne sont
pas modifiés. Le gel reste ouvert.

Les prochaines étapes ciblées sont la validation Apple/ARM64 des sources
modifiées, puis, lors d'un Core explicitement autorisé, la vérification des mêmes
scènes pour la cohérence des vues. Côté moteur, restent à approfondir le producteur
du label GOW3 et le coût du streaming et des soumissions MoltenVK. Fusionner des
soumissions portant des fences distinctes ou retirer des barrières sans preuve
d'équivalence n'est pas une optimisation retenue. Les pistes ARM64 de copie
chevauchante et de vectorisation explicite n'ont pas fourni de remplacement sûr
et avantageux ; elles ne sont pas intégrées.

## Sources et reproduction sans compilation

Patch canonique :
`037d620eb0148b7311da74d711dd2099d06e1285ad6f3079df9586a920a1a0e0`.
Diff lisible : `test/fixtures/rpcs3_device595_followup.diff`.
Preuves : `docs/evidence/rpcs3-device595-followup-20261029/` et
`docs/evidence/rpcs3-temporary-remap-20261029/`.

```sh
python test/rpcs3_device595_followup_contract_test.py /path/to/candidate \
  --baseline /path/to/core-from-543996ad \
  --original-baseline /path/to/core-from-c0df3394 \
  --report /tmp/followup-verification.json
```

Ce contrôle authentifie les six nouveaux modes, les six modes précédents
inchangés et la preuve JIT, sans exécuter de programme natif ou CMake. Pour une
nouvelle plateforme, les programmes affectés sont
`test/rpcs3_temporary_remap_test.py`, `test/rpcs3_spu_timer_reuse_test.py` et
`test/rpcs3_surface_coverage_test.py`, chacun avec source, `--baseline`, `--report`,
en mode ordinaire et `--sanitizer address,undefined`. Les tests du lot précédent
nécessitent aussi leur première validation Apple ; leurs résultats Linux ne
remplacent pas cette étape. Les anciennes preuves binaires ne doivent pas être
présentées comme une compilation de ces nouvelles sources.
