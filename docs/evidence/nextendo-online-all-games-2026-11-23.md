# Nextendo : un seul interrupteur et tous les jeux NEX — 23 novembre 2026

Demande : simplifier l’activation (un bouton de compte, un bouton pour les services en ligne, le reste automatique) et
étendre à tous les jeux compatibles ce qui fait marcher Super Smash Bros. Ultimate.

## Ce qui faisait marcher SSBU

D’après les [journaux des IPA 785 à 801](nextendo-ssbu-ipa785-2026-11-18.md), trois éléments étaient réservés au titre
`01006a800016e000` :

- le certificat privé générique `CN=nintendo-private-server` (auto-signé, sans SAN) présenté par les serveurs de jeu
  NEX de Nextendo, accepté avec consentement explicite ;
- le serveur sécurisé que le jeu nomme ensuite par son adresse IP (port 60005 pour SSBU), accepté après la connexion au
  serveur NEX de la même session ;
- le choix, parmi les réponses DNS de `nex.nextendo.network`, d’une adresse qui accepte une poignée de main TLS.

Le [guide d’intégration](https://wiki.nextendo.network/integration) décrit le même transport pour tous les titres NEX :
PRUDP dans un WebSocket sur TLS, SNI = le nom `g<id>-lp1.s.n.srv.nintendo.net` du jeu. Le client officiel de Nextendo
accepte les certificats de jeu sans vérification (constat du 20 novembre).

## Changements

- **Moteur (`native/melonx/EmbeddedOnline.cs`)** : le consentement s’applique à tout titre. Le certificat privé est
  accepté seulement sur un nom NEX (`g` + 8 chiffres hexadécimaux + `-lp1.` … `.srv.nintendo.net`) et seulement sur une
  adresse de Nextendo : serveur de jeu, adresse NAT (l’hôte NEX de Mario Kart 8 Deluxe y est redirigé) ou réponse DNS
  choisie. Le serveur sécurisé nommé par son adresse est accepté sur tout port de ces adresses, une fois un hôte NEX
  atteint dans la session ; un refus ultérieur ne retire pas cet acquis. Le choix d’adresse démarre à la première
  recherche d’un hôte NEX par le jeu, avec ce nom comme SNI (deux secondes au plus). Une chaîne vers les racines publiées
  reste acceptée comme vérifiée ; tout le reste garde la validation stricte. Journal générique `nexTls` (titre, port,
  sans adresse ni certificat). Les anciens champs `smashPrivateTls` / `smashDnsAddresses` restent compris pour SSBU.
- **Pont iOS** : transmet `nexCompatibility`, `gameDnsAddresses` et l’identifiant de titre lu par la pré-vérification du
  moteur (pas celui annoncé par Dart). Il ajoute les anciens champs SSBU pour un Core plus ancien.
- **Lancement (Dart)** : tout jeu reçoit le même traitement : jeton, adresses DNS, versions du catalogue, données BCAT
  et, pour Animal Crossing, l’identifiant de compte. Le consentement est celui de l’interrupteur.
- **Écran Nextendo** : un bouton de compte (se connecter / se déconnecter) et un interrupteur « Services en ligne ».
  L’activation connecte au compte si besoin, puis pose une seule question qui explique le certificat. Serveurs,
  moteur, compte et dernière connexion d’un jeu sont vérifiés en arrière-plan et résumés en une ligne. Les réglages
  supprimés sont la compatibilité SSBU, les champs d’adresses, les trois lignes d’état et le bouton de vérification.
  Les textes sont traduits dans les 12 langues. Un consentement SSBU donné auparavant, avec le jeu en ligne actif, vaut
  activation.

## Vérifications

- Arbre complet du Core préparé localement, avec `prepare_embedded.py` sur l’amont épinglé : `Ryujinx.HLE` et
  `Ryujinx.Library` compilent sans erreur (.NET 10.0.100).
- Banc local non commité, 20/20, avec de vraies poignées TLS : certificat privé accepté pour un hôte NEX hors SSBU avec
  consentement, refusé sans consentement, refusé pour un autre certificat, pour un hôte non NEX ou pour une adresse hors
  Nextendo. Serveur nommé par adresse sur un port quelconque après connexion, refusé avant. Ancien consentement SSBU
  limité à SSBU. Choix de la réponse DNS qui répond sur 443. Règle NAT de MK8D conservée.
- Banc existant du lot en ligne (`test/melonx_nifm_network_watch/Online.cs`) : 154/154. Test existant
  `melonx_nextendo_data_test.py` : 37 + 102 vérifications réussies. Contrat du Core : 564 vérifications réussies.
- Dart : analyse sans erreur ni avertissement. Les 41 tests existants (Nextendo, en-tête) passent. Test d’écran
  temporaire non commité : 5/5.
- Non fait ici : compilation iOS du Core et de l’app (CI), essai sur iPhone. Rien ne prouve encore qu’un autre jeu NEX
  que SSBU se connecte ou trouve une partie.

## Limites restantes

- Titres NPLN (16 au catalogue : Splatoon 3, Super Mario Bros. Wonder, Pokémon Écarlate / Violet, Légendes Z-A,
  Nintendo Classics…) : il faut les patchs en ligne signés de Nextendo. Le document de patch dépend de l’identifiant de
  compilation de l’exécutable du jeu (`/service-catalog/v1/npln-patches/<titre>/<build>`), et chaque écriture IPS32
  porte une garde à vérifier sur les octets d’origine. RewindBox ne les applique pas encore : il faut un lot moteur
  distinct.
- Titres tiers (Demonware, Ubisoft, EA…) : ils passent par les racines publiées, donc par le chemin vérifié inchangé.
- Version exacte : le serveur refuse une autre version que celle du catalogue. La page du jeu l’indique déjà.
