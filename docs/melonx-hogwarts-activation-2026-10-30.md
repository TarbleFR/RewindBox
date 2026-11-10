# Activation Hogwarts après le nouveau journal

Demande explicite du mainteneur : activer les chemins pertinents et ajuster le
candidat après IPA598. Base livrée : source1c30df6, run41010479756. Claude seule.

Le journal contient17 sessions. Les deux dernières, du30octobre à07:09:32 et
07:11:22 heure de Paris, ont4,15 et4,2 FPS médians sur les échantillons actifs
non nuls. Empreinte2433–3623 et3151–4094 Mio, marge annoncée3032–4222 et
2561–3504 Mio. JIT1024Mio réussi, fermeture et restitution des donneurs réussies,
thermique nominale. Les choix async/VSync et les scènes diffèrent. Le journal
n’atteste ni numéro exact d’IPA ni source du core : aucune régression ou hausse
de FPS n’est attribuable à une version. Les threads CPU nommés GPU ne mesurent
pas l’utilisation du GPU physique. Observations assainies dans
[evidence](evidence/melonx-hogwarts-activation-20261030/log-analysis.json).

## Code produit

Le worker natif applique désormais les options existantes après le preflight
réussi du contenu et avant configuration/JIT/création du renderer. Le titre
exact0100F7E00C70E000 reçoit par défaut occlusionQuerySync=true et
relaxQueryFlushing=true, conformément à la nouvelle demande. Les valeurs false
explicites sont respectées. Le regroupement requiert la synchronisation. Une
identité absente ou différente retire les deux champs même si une préférence
périmée les demande. Le core revérifie indépendamment le contenu réellement
lancé. Un booléen mal formé désactive l’option. Aucun état de session statique.
Les autres paramètres et jeux sont conservés.

L’éditeur graphique Hogwarts expose deux interrupteurs, applicables au prochain
lancement. Désactiver la synchronisation coupe aussi le regroupement ; la
réactiver ne réactive pas implicitement un regroupement explicitement désactivé.
Les choix utilisent les préférences durables existantes dans Documents. Une
lecture de métadonnées dans l’éditeur corrige une identité de bibliothèque
absente/périmée, sans lecture supplémentaire au lancement. Onze langues de
l’interface existante sont couvertes.

Deux événements bornés par lancement donnent les options effectives et la
provenance du paquet : version/build, préfixes du commit et du SHA du core lus
dans son identité embarquée. Les préfixes passent le filtre des secrets existant.
C’est une preuve déclarée du paquet, pas un hash indépendant du binaire chargé
ni un benchmark. Aucun log périodique supplémentaire, purge de cache shader,
réduction graphique implicite ou hausse de budget RAM n’est ajouté.

## Limites des autres lots

Le core exact e7143e56 conserve tous les correctifs déjà compilés. Les108 entrées
de préparation et le périmètre du smoke natif restent inchangés : aucune
recompilation du moteur ni répétition des suites anciennes pour cette activation.
Le journal ne montre aucun refus d’arène JIT. Le repli progressif reste bloqué
par l’absence de contrat transactionnel de rollback natif ; conserver une seule
tentative et les budgets1Gio/512Mio. Aucun RomFS ou chargement effectif des CVars
Unreal Switch n’est fourni : aucun mod LayeredFS spéculatif n’est installé.
Ni correction des textures noires sur appareil ni gain FPS physique n’est prouvé.
Ces limites ne sont pas déclarées achevées par l’activation des deux options GPU.

## Validation

Le test Swift cible le vrai fichier de politique Foundation sur Apple : titres
exacts/absents/différents, couples de booléens, valeurs mal formées, paramètres
préservés, sessions alternées et provenance résistante au filtre des secrets.
Les tests Flutter exercent les vrais interrupteurs et les préférences durables.
L’hôte iPhone complet est compilé dans l’application. Les résultats Apple et
l’identité de l’IPA finale seront consignés après réussite, sans prétendre qu’un
contrôle source Linux exécute ces scénarios natifs.
