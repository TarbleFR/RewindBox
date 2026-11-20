# Connexion de Smash Ultimate à Nextendo sur l’IPA 785

La session du 18 novembre a chargé `01006a800016e000` en version `13.0.5`, acceptée dans le catalogue signé. Le pont a accepté la configuration Nextendo de cette session et le cœur a servi ses données BCAT.

À 07:45:06, 07:45:15 et 07:45:20, heure de Paris, le cœur a refusé le certificat présenté pour `g23380901-lp1.s.n.srv.nintendo.net`. Son sujet et son émetteur étaient tous deux `CN=nintendo-private-server`. Les trois échecs arrivent avant l’authentification NEX. L’enregistrement de 08:43 montre deux ouvertures de « Connexion à Internet… », suivies du retour au menu principal.

Ce nom est celui que Nextendo publie pour Smash. Son guide demande la validation du nom d’hôte et d’une chaîne vers une racine Nextendo publiée. Le certificat présenté ne valide pas dans la session observée. Les anciens journaux ne permettent pas d’identifier la provenance de l’adresse choisie pour cette tentative. [Guide d’intégration Nextendo](https://wiki.nextendo.network/integration#ig-tls)

RewindBox choisit désormais les adresses issues du DNS officiel en priorité. Une adresse intégrée à la compilation sert de repli si le nom n’a jamais été résolu. Le journal de lancement indique l’origine des deux adresses sans publier leurs valeurs. Un essai sur iPhone reste nécessaire pour vérifier le certificat présenté après ce changement et l’accès effectif à la recherche d’adversaires.

## Nouvel essai du 20 novembre 2026 — IPA 796

- Sources examinées : `Claude` à `007929e0471e493069c944fe9dae80e730c3ba37`. Le journal de l’appareil identifie l’IPA 796 et le Core `cf6396a2ca61` ; ce Core contient déjà la sélection parmi plusieurs réponses DNS décrite dans [le suivi de l’IPA 786](melonx-ssbu-hogwarts-ipa786-2026-11-18.md).
- À 01:59:02, heure de Paris : adresses jeu/NAT issues du DNS, catalogue `listed 13.0.5`, BCAT `current`, configuration en ligne acceptée. `listed` décrit la version attendue du catalogue, pas une nouvelle mesure de la mise à jour effectivement chargée.
- À 01:59:19.680 : `smashTls / refused / hostname`. `ValidateServerCertificate` produit cette ligne seulement pour `g23380901-lp1.s.n.srv.nintendo.net` ; le certificat reçu ne couvre pas ce nom. Le journal joint ne contient pas le certificat de cette tentative : son sujet, sa chaîne et son empreinte ne peuvent pas être déduits des anciens essais.
- La vidéo montre « Connexion à Internet… », puis le retour au menu. Les notifications BCAT viennent du cache préparé séparément ; elles ne prouvent ni TLS du jeu ni authentification NEX ni matchmaking.
- Après la mise en arrière-plan, le journal montre un redémarrage de RewindBox. Le refus était uniquement conservé dans `NextendoOnlinePlay.lastSmashTls`, donc perdu. De plus, « Vérifier l’accès en ligne » ne consultait pas ce refus après la réponse positive de l’API du compte.

## Correction et limite

- Le résultat TLS réel de SSBU (`accepted` ou `refused` uniquement) est maintenant conservé dans les préférences et restauré à l’ouverture du panneau. Les écritures sont ordonnées ; un résultat reçu en direct prime sur la restauration. Une erreur de stockage ne casse pas le lancement. Aucune donnée de compte, adresse ou certificat n’est enregistrée.
- Le bouton de vérification affiche le dernier refus connu au lieu de déclarer la connexion prête sur le seul accord du compte. Seule une nouvelle validation TLS du jeu remplace ce refus ; l’activation du jeu en ligne reste disponible pour réessayer.
- Le [guide Nextendo](https://wiki.nextendo.network/integration#ig-tls), relu le 20 novembre, confirme le nom Smash, SNI, HTTP/1.1 et la validation nom + racines publiées. Les cinq PEM intégrés ont été recalculés en SHA-256 : leurs empreintes correspondent toutes à celles du guide actuel. Il demande de contacter l’équipe lorsqu’un certificat ne correspond pas au guide. Aucun contournement TLS ni changement arbitraire de DNS n’est introduit.
- Le sondage depuis l’environnement de travail reçoit le certificat de son proxy TLS, pas celui du serveur de jeu : inutilisable pour conclure sur le déploiement actuel. L’accès direct au PC était indisponible (HTTP 429). Le refus observé sur iPhone reste la preuve de l’échec ; la configuration du serveur ou du trajet réseau doit être vérifiée avec l’opérateur.
- Vérification locale : `git diff --check`. Le [run Nextendo 44651254244](https://github.com/TarbleFR/RewindBox/actions/runs/44651254244), sur le correctif `2bef01cfa5f76672ddbadfb0721f1fd47948a810`, réussit : analyse Dart sans erreur bloquante et 28 tests existants passés. Aucun nouveau test ajouté, aucun Core modifié. La persistance du résultat n’a pas été observée sur iPhone ; pas de nouvelle IPA ni de partie en ligne validée.
