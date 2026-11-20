# Observation de 0089 — proposition bornée, sans scan supplémentaire

## Ce qui manque et ce qu’on peut réellement mesurer

`rb_pa_post` incrémente les spans et octets quand il les met en file. Le worker appelle ensuite `rb_wn`, qui fait déjà `mincore` et `MADV_WILLNEED` sur les pages absentes ; le résultat de `madvise` est ignoré. Il n’existe actuellement aucun lien conservé entre cette demande et un lecteur de texture ultérieur.

Le minimum utile est de compter **hints acceptés → demande observée → lecture confirmée quand le chemin le permet**, avec les pages résidentes/manquantes à l’observation. Cela n’établit pas que le hint a causé la lecture physique ou évité un défaut de page. Les comptes de pages résidentes après hint ne sont pas une mesure de son efficacité causale.

## Crochets et conservation du comportement

Conserver l’argument `demand` de `rb_wn_` pour son rôle actuel dans le batching 0105. Ajouter un **type d’origine d’observation séparé**, ou un wrapper équivalent : `pool_speculation`, `registration_speculation`, `demand_full`, `demand_written_bits`, `demand_level`. Aujourd’hui `demand == 0` peut désigner soit la spéculation, soit la vérification des pages écrites ; ce booléen ne peut pas servir de classement.

Dans la boucle existante, réutiliser les vecteurs `v` et `selected`. Former un masque d’au plus 64 pages à partir de cette boucle, sans nouveau `mincore`, `vm_page_query`, parcours de dirty bits, hash ou lecture du contenu. Pour une sonde batch de 256 pages, émettre jusqu’à quatre observations de 64 pages.

Lors d’un conseil pool : garder la valeur de retour de `madvise`. Un succès produit un événement avec le masque des pages **absentes avant le conseil** ; un échec incrémente les appels/pages échoués, sans marquer les pages comme préchargées. Enregistrer les heures de début et fin de l’appel, afin de distinguer une demande survenue avant la fin de l’appel d’une demande postérieure. Ne pas attendre l’E/S et ne pas toucher la page pour savoir si elle est arrivée.

Lors d’une demande naturelle : publier le masque sélectionné et le masque de résidence issus du `mincore` qui existe déjà. Ce point constate une **intention de lecture**, pas encore tous les octets réellement lus. Pour qualifier des pages de « lues », confirmer après le retour du lecteur naturel : par exemple au terme de la boucle de `span_hash` sur les pages sélectionnées d’une texture. Réutiliser le parcours/bits déjà réalisés. Un unique événement de confirmation de l’opération est préférable à une nouvelle sonde par page.

Les chemins avec lectures partielles dont la couverture de pages ne peut pas être prouvée à partir des informations existantes restent `demand_only` ou `unknown_read_coverage`. Ne pas déclarer tous les octets d’une texture utilisés parce que son upload a commencé. Un échec, un abort ou un remplacement de texture avant la lecture ne confirme rien.

### Schéma d’événements proposé

```c
/* Schéma, pas implémentation synchronisée prête à intégrer. */
typedef struct {
    uint64_t operation_id;
    uint64_t begin_ns, end_ns;
    uint64_t first_page_in_guest_window; /* index relatif, pas une adresse */
    uint64_t selected_mask;
    uint64_t resident_mask;             /* résultat du mincore existant */
    uint64_t hint_accepted_absent_mask;
    unsigned generation;
    unsigned frame;
    unsigned kind;                     /* HINT / DEMAND / READ_COMMIT / INVALIDATE */
    unsigned source;                   /* pool / registration / reader kind */
    int advice_errno;                  /* seulement sur échec */
} rb_page_observation;
```

Ne pas enregistrer de nom de texture, objet Objective-C, pointeur `tex_t`, contenu invité ou chemin de fichier. Le writer effectif des événements doit capturer les valeurs, jamais une référence au vecteur `v` de pile.

## Structure bornée et absence de contention bloquante

Pour 0171, recommander une petite file d’événements préallouée et une agrégation sur une file utility ; **pas de grande table dynamique touchée à chaque dessin**. Taille de départ proposée : 4 096 événements, mémoire annoncée à partir de `sizeof(event)`. Ce plafond est un choix de prudence, non une capacité validée. La file peut perdre des événements : compter séparément les pertes par origine et les publier.

Le hot path doit avoir une sortie immédiate si le diagnostic est désarmé. Une insertion ne doit jamais attendre un worker ou un mutex occupé. Deux possibilités raisonnables : files SPSC distinctes seulement si les propriétaires de chaque origine sont prouvés ; sinon un mécanisme borné de publication avec essai non bloquant et compteur de perte. Ne pas improviser une file MPSC avec `fetch_add(head)` si cela expose un slot non publié ou écrase un consommateur.

L’agrégateur, hors rendu, maintient une table bornée des pages conseillées par la file pool et un âge maximal **en temps monotone**. Un exemple de fenêtre de 30 secondes est un paramètre à déclarer, pas une vérité universelle. Les hints répétés d’une page encore suivie ne doivent pas multiplier les pages uniques. Une éviction de table, une expiration, une perte d’événement ou un arrêt ne signifie pas « jamais utilisée » ; ce sont des observations censurées.

Pour rester minimal, on peut livrer d’abord les compteurs de réussite/échec du conseil et la corrélation demande/résidence, explicitement nommée `demand_observed`. La qualification `read_confirmed` n’est ajoutée qu’aux lecteurs où la couverture est prouvée. La métrique ne doit pas être rebaptisée « pages réellement utilisées » avant cette confirmation.

## Dénominations et dénominateurs obligatoires

| Champ | Sens |
|---|---|
| `hint_absent_pages_attempted` | Pages absentes présentées aux conseils pool, répétitions possibles |
| `hint_absent_pages_accepted` | Même base, appels `madvise` réussis ; pas une fin d’E/S |
| `hint_calls_failed`, `hint_pages_failed` | Erreurs de conseil ; comportement de lecture inchangé |
| `tracked_unique_pages` | Pages uniques effectivement entrées dans la table d’observation |
| `later_demand_resident` | Page suivie sélectionnée à une demande ultérieure et alors résidente |
| `later_demand_absent` | Page suivie sélectionnée à une demande ultérieure et alors absente |
| `read_confirmed` | Lecture naturelle achevée, couverture de page prouvée |
| `demand_only` | Demande observée, confirmation de lecture indisponible |
| `repeat_hints` | Nouvelle demande d’anticipation pour une page déjà suivie |
| `expired_without_observed_read` | Aucune lecture observée avant échéance ; pas « inutile » |
| `invalidated`, `censored_on_end` | Fin de vie de la portée suivie, pas un échec de préchargement |
| `events_dropped`, `table_evicted`, `unknown_coverage` | Limites de la mesure ; ne jamais les cacher dans le dénominateur |

Publier séparément pool 0089, anticipation de registration et demandes directes. Une page demandée par `rb_wn_demand` et immédiatement conseillée pour cette même demande ne compte pas comme succès spéculatif de 0089. Une lecture CPU de la même page après réutilisation d’adresse ne prouve pas l’utilisation de la même ressource : conserver une identité de backing/pool disponible, ou invalider l’observation lors de la retraite du pool/mapping. Sans cet événement, nommer la mesure « même page virtuelle » et ne pas lui attribuer une texture.

## Session, arrêt et protocole

Armer l’observation seulement dans la phase diagnostique définie après le score. Capturer la génération existante dans chaque événement. À park/end/restart, désarmer immédiatement les producteurs et clôturer les observations en `censored_on_end`; jeter les générations périmées. La file de données de diagnostic ne participe pas au drain des files d’E/S et ne bloque ni les uploads, ni le park. Les mesures actives restent indépendantes des drains de 0097, qui continuent à protéger les lectures effectives du moteur.

Aucun changement de `RB_PA_BEHIND`, `RB_PA_AHEAD`, budgets, priorité de lecture, durée du filtre `g_pa_last`, scheduler, shader-cache ou logique d’upload n’est requis. `S2A_RB_POOL_USE_PROBE=0` conserve l’ancien comportement et ne crée aucune file ni table d’observation.

Le banc causal suivant, s’il devient justifié par les données, compare `S2A_RB_POOL_AHEAD` seul avec même source, parcours, état de cache, cadence, résolution et observation. Les relevés actuels ne permettent pas de prédire un gain. Un ratio de réutilisation faible sous faible couverture ou pertes élevées ne justifie aucune réduction de budget.
