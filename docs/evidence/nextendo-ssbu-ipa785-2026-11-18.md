# Connexion de Smash Ultimate à Nextendo sur l’IPA 785

La session du 18 novembre a chargé `01006a800016e000` en version `13.0.5`, acceptée dans le catalogue signé. Le pont a accepté la configuration Nextendo de cette session et le cœur a servi ses données BCAT.

À 07:45:06, 07:45:15 et 07:45:20, heure de Paris, le cœur a refusé le certificat présenté pour `g23380901-lp1.s.n.srv.nintendo.net`. Son sujet et son émetteur étaient tous deux `CN=nintendo-private-server`. Les trois échecs arrivent avant l’authentification NEX. L’enregistrement de 08:43 montre deux ouvertures de « Connexion à Internet… », suivies du retour au menu principal.

Ce nom est celui que Nextendo publie pour Smash. Son guide demande la validation du nom d’hôte et d’une chaîne vers une racine Nextendo publiée. Le certificat présenté ne valide pas dans la session observée. Les anciens journaux ne permettent pas d’identifier la provenance de l’adresse choisie pour cette tentative. [Guide d’intégration Nextendo](https://wiki.nextendo.network/integration#ig-tls)

RewindBox choisit désormais les adresses issues du DNS officiel en priorité. Une adresse intégrée à la compilation sert de repli si le nom n’a jamais été résolu. Le journal de lancement indique l’origine des deux adresses sans publier leurs valeurs. Un essai sur iPhone reste nécessaire pour vérifier le certificat présenté après ce changement et l’accès effectif à la recherche d’adversaires.
