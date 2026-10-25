# Nettoyage ponctuel de l’historique GitHub Actions — 21 octobre 2026

## Demande et périmètre

Le mainteneur demande de commencer le ménage dans GitHub Actions et de garder
les 300 exécutions les plus récentes. Le dépôt audité est
`TarbleFR/neostation-ios`. Le point de départ de `Claude` est
`1375d57eee0af2de47740843808761456a4dc3a2` ; `main` est
`bcca4e4a4dc89a96b1dde05d66436af54efd327e`.

L’inventaire initial comporte **2 224 exécutions distinctes**, toutes achevées,
du 7 au 21 octobre 2026. La 300e est `39270782207`, créée le 19 octobre à
14:38:29 UTC. Le classement repose sur `created_at`, puis sur l’identifiant
décroissant en cas d’égalité ; il est identique à l’ordre retourné par GitHub
pour cet inventaire.

La cible est de conserver les **300 exécutions les plus récentes au moment du
nettoyage**, auxquelles s’ajoutent les anciennes exécutions encore nécessaires
aux téléchargements et aux validations. L’exécution de maintenance entre
elle-même dans les 300 plus récentes. Les nouvelles exécutions absentes de
l’inventaire figé restent hors du périmètre de suppression.

## Pourquoi certains anciens runs doivent rester

Des workflows actuels téléchargent des artefacts de runs plus anciens que la
coupure. D’autres vérifications interrogent directement leur état ou leurs
jobs. Un reçu conservé dans Git ne remplace pas ces appels réseau. Supprimer
ces runs casserait la réutilisation de cœurs ou les gardes de livraison.

Le registre des protections est construit à partir des consommateurs
exécutables sur `Claude` et sur `main`, avec les manifestes et recettes figées
qu’ils chargent. Il couvre notamment ARMSX2, les paquets Libretro/Nestopia et
les preuves encore requises par les validations. Il distingue les références
déjà absentes et les anciennes mentions purement historiques.

Le rapprochement initial identifie **118 IDs de dépendances** : 112 présents,
dont 75 parmi les 300 récents et **37 plus anciens**, plus six références
déjà absentes. Sur le snapshot seul, cela conserve 337 runs et en rend
1 887 supprimables. Avec le nouveau run de maintenance, qui occupe une place
parmi les 300 récents, la projection devient **1 888 suppressions et 337
runs conservés**, en l’absence d’autre activité concurrente. Le run sortant
de la coupure des 300 n’est pas une dépendance protégée.

Le plan `build-utils/maintenance/actions-cleanup-2026-10-21.json` contient
l’inventaire, les identités des runs et le registre détaillé des protections.
Le résultat exact doit se lire dans le reçu du workflow : les chiffres
prévisionnels ne sont pas une preuve de suppression.

## Exécution et garde-fous

Le workflow `.github/workflows/actions-history-cleanup.yml` est ponctuel. Il
ne possède pas de déclencheur planifié. Son lancement est borné à un push sur
`Claude` depuis le SHA de départ indiqué ci-dessus, à la modification du plan
daté et au marqueur de commit `[actions-cleanup-2026-10-21]`. Les chemins de
maintenance ne correspondent à aucun déclencheur push des 73 workflows
existants contrôlés au SHA de départ.

Le jeton éphémère du workflow possède `actions: write` pour supprimer les runs
et `contents: read` pour vérifier les références. Le script n’expose qu’une
opération destructive : `DELETE /repos/TarbleFR/neostation-ios/actions/runs/ID`.
Le code n’écrit pas de release, de tag, d’asset ou de référence Git et ne
lance aucune compilation d’application ou de cœur.

Avant suppression, le script vérifie le dépôt, la branche, le commit, la
date limite du plan et son SHA-256. Il réénumère les runs sans filtre de
recherche, vérifie le total et l’absence de doublons, puis établit les
candidats. Les 300 plus récents, les dépendances déclarées, les runs actifs,
les runs relancés et les IDs absents de l’inventaire restent protégés.
Les identités et les références Git sont contrôlées de nouveau pendant
l’opération ; un changement de branche interrompt le nettoyage.

Les suppressions sont séquentielles, espacées d’au moins une seconde.
Le script respecte `Retry-After` et la remise à zéro du quota. Il n’utilise
ni autre jeton, ni changement de compte pour contourner une limite. Une
erreur non récupérable conserve le reçu partiel et arrête l’exécution.

## Reçu et vérification

Le répertoire `cleanup-output/` contient le plan calculé, les événements de
suppression et le bilan. Il est joint au run sous le nom
`Actions-history-cleanup-<run_id>`. Le journal est mis à jour après chaque
suppression ; le bilan distingue les réponses de suppression, les IDs déjà
absents et les protections supplémentaires dues à un changement concurrent.

Les tests `test/actions_cleanup_test.py` vérifient les conditions qui peuvent
entraîner une suppression injustifiée : pagination instable, conservation
des runs récents/protégés/actifs, changements d’identité, borne du nombre de
suppression et reprise idempotente. Ils s’exécutent avant le nettoyage.
Les **21 cas comportementaux** passent localement avant activation, avec une
API factice uniquement. La projection sur les vrais 2 224 enregistrements,
augmentée d’un run de maintenance factice, confirme séparément 1 888 cibles
et 337 conservations. Les 118 IDs de dépendances sont tous exclus des cibles.
Le SHA-256 du plan relu est
`802f1ebd352ca6322334bac409c1cc0d54d681b4b15595c7fc34baeeaa137ea5`.

La release existante `0.0.8` (ID `416487079`) et l’identité de ses sept assets
figurent dans le plan comme état de référence. Aucun nouveau numéro de build
ou de release n’est attribué par cette maintenance.

## Références techniques officielles

- [API GitHub — énumération et suppression des workflow runs](https://docs.github.com/en/rest/actions/workflow-runs).
- [Limites de l’API et du GITHUB_TOKEN](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
- [Pratiques recommandées : requêtes séquentielles et respect des limites](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

Pour atteindre exactement 300 runs tout en conservant toutes les anciennes
dépendances, il faudrait d’abord déplacer leurs artefacts et adapter leurs
consommateurs avec une preuve d’identité. Ce nettoyage conserve ces
dépendances tant que cette migration n’a pas été effectuée.
