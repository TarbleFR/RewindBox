# RPCS3 iOS 573 — mémoire des textures et préparation des textures (God of War III)

27 octobre 2026. Ce Core part des journaux du **build 567** de God of War III
(`BCES00510`, iPhone A18 Pro). **Aucun gain 573 n'est mesuré sur iPhone.**

## 1. Ce que montrent les journaux

| God of War III, build 567 | Valeur |
|---|---|
| Empreinte mémoire | 4,75 Go, dont 1,25 Go compressés par iOS |
| Textures en cache (pool) | jusqu'à 1,72 Go |
| Après le recyclage « moderate » (fenêtre 12) | 366 Mo, puis 1,56 Go 75 s plus tard |
| Blocs VMA | 2,76–2,83 Go, dont jusqu'à 1,99 Go inutilisés |
| Images par seconde | ~10–25 |
| Préparation des textures | ~7–12 ms par image |
| Hachage de validation des textures | 5,4–12,7 Go et 0,4–0,85 s par fenêtre de 5 s, ~8 ms par image |
| Points de validation (époques) | ~9 par image, même sur un écran à 9 dessins |
| Relecture d'une cible de rendu par le CPU | 1 par image (3,7 Mo) |

La PS3 n'a que 512 Mo de mémoire en tout. 1,72 Go de textures, c'est surtout
des textures **mortes**.

## 2. Le mécanisme

**Mémoire.** Sur iOS, les textures ne sont pas protégées par pages (les
exceptions Mach passent par le débogueur du JIT). Leur contenu est vérifié par
hachage quand une recherche les utilise. Quand le jeu réécrit la mémoire d'une
texture avec autre chose (GoW3 diffuse ses niveaux dans la même mémoire),
l'ancienne texture n'est découverte périmée que si elle est recherchée à
nouveau. Celles qui ne le sont plus jamais gardent leur image GPU. Le recyclage
de pression les purge d'un coup, puis le pool regrossit. Les blocs VMA, eux,
restent réservés.

**Préparation des textures.** Avec la validation par lot FIFO (559), une
texture déjà vérifiée n'est pas re-hachée avant le prochain point de
synchronisation. Mais chaque écriture du RSX lui-même faisait avancer l'époque
globale :
- relecture d'une cible de rendu pour le CPU ;
- engagement d'une cible de rendu.

**Toutes** les textures étaient alors re-hachées, même loin de la zone écrite.

## 3. Les changements

### `CELL573_TEXTURE_RESIDENCY` (`ios/IOSTextureResidency.h`)

- Toutes les 16 images, si les textures vivantes (pool moins images
  recyclables) dépassent **768 Mo**, des textures inactives sont libérées,
  au plus 128 Mo par passe :
  1. d'abord celles recouvertes par une section utilisée après elles et qui
     déborde d'elles (leur mémoire contient autre chose), inactives depuis
     8 images ;
  2. puis les moins récemment utilisées, inactives depuis 64 images.
- Jamais une texture liée à un emplacement de texture (fragment ou vertex).
- Les descripteurs de ces textures sont recherchés à nouveau avant usage.
- Une texture libérée que le jeu échantillonne à nouveau est rechargée depuis
  sa mémoire, comme à sa première utilisation.
- Une validation de maintenance (`trim_sections`) ne compte pas comme un usage.
- Réglage *Experimental → FPS Experiments → Texture residency cap*
  (`experimental.texture_residency`). Automatique : God of War III.

### `CELL573_SCOPED_RSX_WRITES`

- Une cible de rendu relue pour le CPU (`flush_set`) ne fait revalider que les
  sections qui recouvrent les sections relues.
- Un engagement de cible de rendu (`committed_as_fbo`, `superseded_by_fbo`) ne
  fait revalider que les sections de la plage touchée, élargie à toutes les
  sections piétinées. Ce sont les octets que l'écriture différée 560 peut
  écrire.
- L'époque globale avance toujours sur : PUT du jeu, sémaphores, défauts
  d'écriture CPU, démappages, fin d'image.
- Réglage *Scoped texture revalidation*
  (`experimental.scoped_texture_revalidation`). Automatique : God of War III.

Journal de démarrage : `texture_residency=1 scoped_revalidation=1`.
Identités de codegen inchangées : aucune recompilation à froid. Hors iOS, le
code compilé est celui du 571.

## 4. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell573-host-linux.json`](evidence/rpcs3-cell573-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152`. La fixture
  reconstruit exactement les préimages 571. Les 9 tests statiques existants
  passent sur le Core rematérialisé.
- Vérification syntaxique ARM64 avec `RPCS3_IOS` des 7 unités touchées :
  aucune erreur ni aucun avertissement nouveau. Sans `RPCS3_IOS`, chaque ligne
  de code est celle du 571.
- **Éviction.** `evict_idle_sections` est copiée telle quelle du Core dans un
  modèle de cache. Le modèle reproduit GoW3 :
  - 384 Mo utilisés à chaque image ;
  - une zone revisitée toutes les 300 images ;
  - une texture par image diffusée dans un anneau de 160 Mo sur des textures
    mortes.

| 6 000 images | Sans | Avec |
|---|---|---|
| Pic des textures vivantes | 10,3 Go (sans fin) | 828 Mo |
| Textures vivantes à la fin | 10,3 Go | 768 Mo |
| Rechargements de textures utilisées | — | 0 |
| Rechargements de la zone revisitée | — | 0 |

  Aucune texture liée ni utilisée dans les 8 dernières images n'est libérée.
- **Revalidation ciblée.** Le modèle utilise le vrai `buffered_section::sync`
  et les vrais blocs iOS de `flush_set` et `invalidate_range_impl_base`. Avec
  5 textures, dont 2 sous la cible de rendu :

| | Re-hachées avant | Re-hachées après |
|---|---|---|
| Relecture de cible de rendu | 5 | 2 |
| Engagement de cible de rendu | 5 | 3 |

  Chaque changement est détecté, y compris l'écriture différée hors de la
  plage du défaut. Les causes CPU avancent toujours l'époque globale.
- Le gain réel dépend du nombre d'époques qui viennent d'écritures RSX parmi
  les ~9 par image, que les journaux ne séparent pas.

Ce sont des modèles sur l'hôte, pas des mesures sur iPhone.

## 5. À relever sur iPhone (God of War III)

- `MEMPROF527` : empreinte et compression en baisse.
- `JITMEM` : `gpu_textures_requested` et `vma_block_bytes` plafonnés vers
  ~0,8–1,2 Go au lieu de 1,7 et 2,8 Go.
- `JITMEM texture_hash_bytes` / `texture_hash_ticks` et `RSXFRAME551
  texture_ms` en baisse ; `OPT559 epoch_advances` en baisse.
- Pas de textures fausses ni d'à-coups en revenant dans une zone.
- Si une régression apparaît : désactiver *Texture residency cap* ou *Scoped
  texture revalidation* rend le comportement 571.
