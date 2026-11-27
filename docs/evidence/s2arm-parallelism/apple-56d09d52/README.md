# Rejeu et synchronisation sur GPU Apple

Le [run Apple 46029548889](https://github.com/TarbleFR/RewindBox/actions/runs/46029548889) a exécuté sept configurations du moteur au commit `56d09d52`. Le GPU paravirtualisé a sélectionné Metal 3. Les résultats ci-dessous proviennent de son archive originale, dont l’ID est `15213084602` et le SHA-256 `31fd68ddb052837139669c9e72a56f6f5908cd82e3bff221d7ba17f1ca7f6357`. Les processus mesurent trois images chacun.

| Configuration de la scène | Exécutions | Images | Résultat |
| --- | ---: | ---: | --- |
| Découpage dynamique des passes, paramètres habituels | 35 | 105 | 4 scissions supplémentaires réparties sur les sept variantes. À chacune, la passe publie puis reprend sa dépendance. Une image du témoin a aussi attendu plus tôt au premier sous-échantillonnage. |
| Découpage fixé dans le banc | 28 | 84 | 0 scission. Les sept variantes conservent exactement les mêmes opcodes et masques par image, avec 14 opérations de synchronisation. |

**Les 63 exécutions conservent les pixels et l’état des dessins.** Les empreintes respectives sont `f2c8d5939b7f046b` et `22f104742e837afc`. Les deux modes de reprise entre files réussissent 14 assertions chacun. L’encodeur réussit 7 assertions par mode de publication. Le banc d’arrêt GPU confirme le refus de soumission et le retour immédiat du drain sur Metal 3.

**La configuration combinée a dégradé les images les plus lentes de cette scène.** Sans instrumentation, le p95 passe de 7,95 à 22,53 ms avec le découpage courant (12 images chronométrées par variante) et de 8,38 à 23,71 ms à travail fixé (9 images par variante). Le p99 passe respectivement de 8,64 à 26,74 ms et de 8,46 à 26,49 ms. Les échantillons sont petits et le Mac est virtualisé. Les options restent expérimentales. [Quantiles avec découpage courant](default-quantiles.csv) · [Quantiles à travail fixé](fixed-quantiles.csv).

Le premier contrôle de cette archive a échoué sur une image du témoin. Dans la passe d’éclairage, une scission à la 266e opération fait atteindre le seuil de 64 dessins avant le travail 338. Le code et le compteur de dessins expliquent le renouvellement du command buffer à cette frontière. La trace atteste directement le masque et sa position. Le moteur attend avant le vertex du premier sous-échantillonnage, qui lit au stade fragment la texture écrite par la passe d’éclairage. Le test attendait un masque fragment à cet endroit. Le contrôle révisé reconnaît cette séquence précise et vérifie encore le producteur, le consommateur, leur ordre, les masques adjacents et le nombre d’opérations. Le profil fixé continue d’exiger l’égalité exacte. Les contrôles négatifs déplacent le renforcement, modifient le seuil ou les masques, suppriment ou permutent des opérations et provoquent bien un rejet. Le correctif porte sur la lecture du banc.

[Contrôles par variante, profil dynamique](dynamic.json) · [Contrôles à travail fixé](fixed.json). Les deux fichiers gardent l’empreinte brute de chaque trace diagnostique, les positions des attentes renforcées et les empreintes de comparaison.

La capture est rattachée au moteur amont `6b6a571553f7a687af46e03e2cdbf8ef4d77f335`. Le manifeste `inputs.txt` de l’archive énumère 509 patchs. La liste ordonnée de leurs noms et sommes SHA-256 correspond au checkout du run et au [commit de production moteur 28b5ab49](https://github.com/TarbleFR/RewindBox/actions/runs/46029300326). Les modifications entre ces deux commits portent sur le banc. Les essais d’affichage sur A18 Pro restent à réaliser avec les options de ce lot.

Pour reproduire la vérification sur l’archive téléchargée depuis ce run :

```sh
python3 -B build-utils/s2arm/engine/tests/recheck_parallel_artifact.py capture.zip rapport --sha256 31fd68ddb052837139669c9e72a56f6f5908cd82e3bff221d7ba17f1ca7f6357 --inputs-sha256 c3987ee2cddaddc39786fb1b078f159628f0e888b7df482c10518b657e331491
```
