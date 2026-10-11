# Bibliothèque de lecture — Build 437 (10–11 octobre 2026)

Demande du mainteneur du 10 octobre 2026 (branche `Claude`, livrée en
Build 437 par-dessus la 436) : compatibilité avec les sources Aidoku
ajoutées par l’utilisateur, bibliothèque locale de livres et de mangas,
chargement rapide des catalogues, et lecture adaptée à l’iPhone.

Base : Build 436, `90a0d5cc`. Rien n’a été modifié dans RPCS3, les moteurs
d’émulation, `lib/main.dart` ou les dix fichiers verrouillés sur la 419. Le
pont libretro reçoit une seule méthode (orientation des lecteurs, §6).

## 1. Point de départ (Build 436, constaté dans les sources)

- `neostation.library.v1` reste le format des manifestes NeoStation ; il est
  conservé. Les dépôts Aidoku étaient importés **en bloc** (toutes les
  sources activées, sans aperçu), un `source.json` seul ou un `.aix` étaient
  refusés.
- 7 adaptateurs natifs Dart existaient ; les 3 autres sources étaient
  refusées.
- Le filtre « contenu adulte », actif par défaut, cherchait des mots dans
  `jsonEncode(provider)` : la clé `"nsfw"` correspondait toujours, donc
  **100 % des titres Aidoku étaient masqués** (0 titre visible sur 70 mesuré).
- L’accueil attendait toutes les sources, par lots de 3, avant d’afficher le
  premier titre ; aucun cache ; un client HTTP neuf par requête ; couvertures
  sans cache disque ni redimensionnement ; analyse HTML sur le fil de
  l’interface ; mode continu du lecteur chargeant toutes les pages d’un coup.
- La « Bibliothèque locale » n’était qu’un écran d’attente.

## 2. Ce qui a été réalisé

| Domaine | Fichiers principaux |
|---|---|
| Réseau partagé : client keep-alive, limites par hôte et globale, déduplication, annulation réelle des sockets, cache disque LRU (ETag / Last-Modified, fraîcheur, repli périmé hors ligne), erreurs typées (défi anti-bot, serveur indisponible, hors ligne, délai) | `lib/services/library_http.dart` |
| Cache d’images (couvertures, pages) avec épinglage des favoris, décodage à la taille affichée | `library_image_cache.dart` |
| Progression, favoris, marques de chapitres, réglages des lecteurs (JSON atomique, tolérant à la corruption) | `library_reading_store.dart` |
| Moteurs Aidoku natifs (Madara + variante Mangas Origines, MangaThemesia, Lelscan), registre d’état des 10 sources, test de santé par étapes, analyse hors du fil principal | `library_aidoku_engines.dart`, `library_aidoku_parsing.dart`, `library_aidoku_native_service.dart`, `library_source_support.dart`, `library_manga_models.dart` |
| Import de catalogue : aperçu sans installation, activation des seules sources cochées, `source.json` seul, `.aix` (métadonnées uniquement), liens `aidoku://` et `aidoku.app`, liens GitHub `blob`, dossiers, redirections | `library_source_catalog_service.dart`, `library_addon_service.dart` |
| Accueil : flux de catalogue progressif depuis le cache, recherche progressive annulable, favoris et « reprendre » | `library_catalog_feed.dart`, `library_screen.dart`, `library_favorites_view.dart` |
| Sources, aperçu de catalogue, fiche manga, bibliothèque locale | `library_sources_view.dart`, `library_catalog_preview_screen.dart`, `library_manga_details_screen.dart`, `library_local_view.dart` |
| Bibliothèque locale : formats, EPUB (CFI), CBZ paresseux, TXT, index incrémental | `library_local_library_service.dart`, `library_book_formats.dart`, `library_epub.dart`, `library_archive_pages.dart`, `library_text_document.dart` |
| Lecteurs iOS : pages (chapitres en ligne, CBZ), EPUB/TXT redimensionnable, PDF | `lib/screens/library_screen/reader/`, `library_pdf_reader_screen.dart`, `library_reader_launcher.dart` |
| Traductions (12 langues) | `lib/l10n/library_feature_locale.dart`, `library_sources_locale.dart`, `library_local_locale.dart`, `library_reader_locale.dart`, `library_date_format.dart` |

Aucune nouvelle dépendance : `archive`, `xml`, `html`, `http`, `pdfrx`,
`file_picker`, `wakelock_plus`, `url_launcher` étaient déjà verrouillés.
Le code `.aix` (WebAssembly) n’est jamais exécuté : iOS interdit le JIT, les
sources appellent l’hôte de façon synchrone et utilisent des sélecteurs
propres à Jsoup ; le dépôt français ne déclare aucune licence. Les
adaptateurs natifs sont écrits pour les sites publics.

## 3. État des dix sources (vérifié le 10–11 octobre 2026 depuis un PC Windows, pas sur iPhone)

Niveaux : **catalogue importé** → **source reconnue et adaptateur disponible**
→ **navigation fonctionnelle** (liste, fiche, chapitres) → **lecture d’un
chapitre vérifiée** (liste des pages + première image téléchargée).

| Source | Site | Adaptateur | Navigation | Lecture | Constat |
|---|---|---|---|---|---|
| Mangas Origines | mangas-origines.fr | oui (Madara + thème « origines ») | oui | oui | Le site a changé de thème : recherche, fiche et chapitres étaient cassés en 436 (0 chapitre). Recherche via `madara_child_catalogue`, chapitres lus dans la page du titre (1 requête). |
| LelscanFR | www.lelscanfr.com | oui | oui | oui | Liste des chapitres sur plusieurs pages (546 pour One Piece) ; le site met 5 à 24 s à les générer, la fiche s’affiche puis la liste se complète. |
| SushiScan | sushiscan.net | oui (MangaThemesia) | oui | oui | Fonctionne ; le site n’a rien publié depuis environ mai 2026. Referer exact `https://sushiscan.net/` obligatoire pour les images. |
| Sushi Scans | sushiscan.fr | oui (même moteur) | partielle | non | L’origine répond 504 après ~5 s sauf pages en cache frontal (listes 1–2, quelques fiches). Différente de SushiScan (.net). |
| Manga Scantrad | manga-scantrad.io | conservé | non | non | Défi Cloudflare (403 `cf-mitigated: challenge`) sur toutes les URL ; CDN d’images en 504. Aucun contournement. |
| Astral Manga | astral-manga.fr | non | — | — | Défi Cloudflare ; le site est devenu une application Next.js (API JSON, images S3 signées) : l’ancien modèle Madara ne correspond plus. |
| PhenixScans | phenix-scans.com | non | — | — | Domaine parqué (page « Redirecting… ») ; le groupe d’origine a disparu, le clone `.co` est hors ligne. |
| Manga Scan | mangascan-fr.com | non | — | — | Domaine parqué ; successeurs `.co` / `.net` disparus. Le README l’indique déjà hors service. |
| ReaperScansFR | reaperscans.fr / reaper-scans.fr | non | — | — | DNS rompu pour l’URL du `source.json` ; le domaine du README ne sert qu’un fichier de 4 octets. Le README l’indique déjà non fonctionnel. |
| LegacyScans | legacy-scans.com | non | — | — | Cloudflare 522 (origine injoignable) partout, CDN en 525. Le README l’indique déjà non fonctionnel. |

Le README du dépôt marque 7 sources comme fonctionnelles : au moment de la
vérification, 4 d’entre elles ne l’étaient plus (Astral, Scantrad, Phenix,
Sushi Scans). Leur rétablissement dépend des sites. Dans l’application, chaque
source affiche cet état, et le bouton **Tester** refait la vérification sur
l’iPhone (étapes liste, fiche, chapitres, pages, image) et enregistre le
résultat daté ; un appareil hors ligne est distingué d’une source hors ligne.

## 4. Formats locaux

| Format | Lisible | Remarques |
|---|---|---|
| EPUB | oui | Texte redimensionnable, sommaire, police, interligne, marges, justification, thèmes clair / sépia / sombre / noir ; position enregistrée en CFI EPUB (stable malgré police et rotation). EPUB protégés (Adobe/LCP : `rights.xml`, `encryption.xml` hors polices) refusés. |
| PDF | oui | pdfrx/PDFium : pages, zoom, sommaire, curseur de page ; PDF protégés par mot de passe refusés à l’import. |
| CBZ | oui | Pages lues une par une depuis un isolate (jamais toute l’archive en mémoire) ; ComicInfo (titre, sens de lecture). Un `.cbr` qui est en réalité un ZIP est accepté. |
| TXT | oui | UTF-8, UTF-16 (BOM), Windows-1252. GBK/Big5/Shift-JIS ne sont pas détectés. |
| CBR (RAR), CB7 (7z), MOBI/AZW | non | Refusés avec une explication : il faudrait une dépendance native nouvelle (RAR) ou une extraction complète (7z solide). |

Les fichiers sont choisis dans Fichiers (Sur mon iPhone, iCloud Drive, autres
fournisseurs) ; iOS les télécharge avant de les remettre. NeoStation garde sa
copie dans `NeoStation iOS › Library › Books` (visible dans Fichiers) ;
supprimer un livre ne supprime que cette copie. Doublons détectés par
empreinte (taille + SHA-256 du début et de la fin), y compris deux fichiers de
même nom dans une même sélection. L’index est incrémental : au relancement,
seuls les fichiers nouveaux ou modifiés sont réexaminés.

## 5. Performances (mesures avant/après)

Conditions : PC Windows 11, Flutter 3.47.2 en `flutter test` (VM Dart JIT),
réseau habituel du PC, 3 passes, médianes. Build 436 mesurée à nouveau juste
avant la 437 pour des conditions comparables. **Aucune mesure sur iPhone ni
en cellulaire.** Détail : `results-*.json` et `compare.md` de la session.

| Scénario | Build 436 | Build 437 |
|---|---|---|
| Ouverture à froid : premiers titres | 6 000 ms, et 0 titre visible avec le filtre par défaut | 233 ms ; 99 titres visibles sur 100 |
| Ouverture à froid : toutes sources terminées | 6 000 ms | 773 ms (réseau 763 ms, traitement 7–18 ms par source) |
| Requêtes vers des sources bloquées à chaque ouverture | 3 | 0 |
| Retour sur l’onglet | 6 006 ms, 7 requêtes, 977 Ko | 0,2 ms, 0 requête |
| Relance (cache frais) | identique au froid | 12 ms, 0 requête |
| Recherche « solo » : premiers résultats | 250 ms (après attente de toutes les sources : 5,2 s) | 212 ms, résultats source par source |
| Saisie de « solo » (requêtes / octets perdus) | 28 / 3,17 Mo | 12 / 1,55 Mo (6 requêtes annulées) |
| Ouverture d’un titre puis d’un chapitre (LelscanFR) | première page à 2 352 ms, 1 requête en double | 1 240 ms, aucune requête en double |
| Idem (SushiScan) | 833 ms | 497 ms |
| Attente à chaque page | 34–49 ms | 1–3 ms (préchargement) |
| Analyse HTML la plus lourde, blocage du fil d’interface | 16–24 ms | ≤ 1,2 ms (isolate) |
| Liste visible de l’accueil (420 titres) | 30 ms par calcul, 3 calculs par déplacement manette | 0,12 ms, mémorisée (0 recalcul en 24 déplacements) |
| Mémoire décodée, 15 couvertures | 57,4 Mo | 19,2 Mo (paysage) / 5,3 Mo (portrait) |
| Mémoire décodée, chapitre SushiScan de 20 pages | 486 Mo (mode continu) | 31 Mo (3 pages gardées, portrait) |
| Bibliothèque locale, relance à 1 000 livres | — | index affiché en 3–7 ms, 0 livre réexaminé |
| CBZ de 100 Mo : mémoire de pointe | 236–252 Mo (lecture naïve) | +34–38 Mo |

Points honnêtes : les octets d’une ouverture à froid augmentent (+26 %) parce
que 4 sources répondent désormais au lieu de 3 (100 titres au lieu de 70) ;
sushiscan.fr reste lent (504 après ~5 s) et retarde la fin de la recherche
sans bloquer les autres sources ; le traitement d’ouverture d’un titre
LelscanFR passe de 8 à 22 ms (analyse en isolate, écriture du cache) pendant
que le temps réseau est divisé par deux.

## 6. Lecture sur iPhone

- Les lecteurs peuvent pivoter en portrait alors que l’app reste en paysage :
  méthode `setReaderOrientation` ajoutée au pont libretro (masque
  d’orientation existant, refusée pendant une session libretro) ; ordre
  d’entrée et de sortie vérifié par un test de contrat. `Info.plist` et
  `lib/main.dart` ne changent pas.
- Pages : mode page par page (gauche → droite ou droite → gauche) ou défilement
  vertical (webtoon), zoom par pincement et double-tap, zones de tap,
  curseur de page, chapitre précédent/suivant, écran maintenu allumé,
  sauvegarde automatique.
- EPUB/TXT : voir §4 ; PDF : pages, zoom, sommaire.
- Manette : flèches pour tourner les pages, LB/RB pour les chapitres, A pour
  les commandes, B pour fermer ; les nouveaux écrans sont navigables à la
  manette.

## 7. Tests et vérifications

- Tests Dart de la bibliothèque (`test/library_*_test.dart`, désormais
  exécutés obligatoirement par la livraison) : 664 réussis, 2 ignorés (tests
  en direct), 1 échec propre à Windows et préexistant (scanner de ROM,
  séparateur de chemin). Ils couvrent services, formats, import de
  catalogue, moteurs sur fixtures minimisées, écrans, lecteurs, parcours de
  bout en bout hors ligne et contrôle des 12 langues (clés, paramètres,
  chinois traditionnel, termes de menu, dates localisées).
- Tests Python : couverture des 12 langues (catalogues de la bibliothèque
  ajoutés), périmètre verrouillé 419, contrat libretro, contrat d’orientation
  des lecteurs, notices juridiques.
- Vérification en direct (test ignoré par défaut, `NS_LIBRARY_LIVE=1`) :
  catalogue importé → 3 sources activées → recherche → fiche → chapitres →
  pages → première image, puis relance hors ligne servie depuis le cache.
- Revue contradictoire selon cinq angles (exactitude, sûreté des données,
  performances, traductions, ergonomie iOS et manette) : 28 constats, aucun
  critique ni élevé, tous corrigés avec un test qui échoue sans le correctif.
- Sous Windows, 9 tests du scanner de ROM échouent à l’identique sur la 436
  (liens symboliques, chemins) ; ils sont validés sous Linux en CI.

## 8. Limites et vérifications restant nécessaires

- **Rien n’a été testé sur l’iPhone** : sélecteur de fichiers (iCloud,
  fournisseurs tiers), rotation portrait des lecteurs, rendu PDF réel,
  mémoire, VoiceOver, réseau cellulaire.
- Le portrait des jeux libretro doit être revérifié sur l’iPhone, car le
  fichier du pont libretro a changé (une méthode ajoutée).
- Sources bloquées par Cloudflare : aucune vérification interactive n’est
  proposée (il faudrait une vue web ; décision produit non prise).
- RAR/CBR réels, CB7, MOBI/AZW et livres protégés par DRM ne sont pas lisibles.
- Les adaptateurs dépendent du balisage des sites et casseront s’ils changent ;
  le bouton Tester le signale.
- Sushi Scans (sushiscan.fr) est encore interrogée par la recherche : elle
  reste « en cours » environ 5 s (504 du site) pendant que les autres
  sources affichent déjà leurs résultats.
- Un site peut recevoir jusqu’à 6 connexions simultanées (3 pour les pages
  HTML/API, 3 pour les images) ; la réaction des sites (limitation de débit)
  n’a pas été mesurée en cellulaire.
- TXT en GBK, Big5 ou Shift-JIS non détectés ; les compteurs d’évictions de
  progression ne sont affichés nulle part (aucune éviction des livres locaux
  ni des titres marqués).

## 9. Tutoriel

**Ajouter un catalogue de sources**
1. Bibliothèque › **Sources** › **Ajouter un catalogue (URL)**.
2. Coller l’URL, par exemple
   `https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/gh-pages/index.min.json`
   (un lien `aidoku://`, `aidoku.app`, GitHub ou un `source.json` fonctionne aussi).
3. L’aperçu liste les sources sans rien activer : cocher celles voulues
   (celles avec adaptateur sont indiquées), puis **Activer**.
4. Les titres apparaissent sur l’accueil de la Bibliothèque ; **Tester**
   vérifie une source étape par étape.

**Importer ses fichiers**
1. Bibliothèque › **Bibliothèque locale** › **Importer des fichiers**.
2. Choisir un ou plusieurs EPUB, PDF, CBZ ou TXT dans Fichiers (Sur mon
   iPhone, iCloud Drive…).
3. Le bilan indique pour chaque fichier : importé, doublon, protégé, format
   non pris en charge…
4. Toucher un livre pour le lire ; la position est reprise automatiquement.
   Les fichiers peuvent aussi être déposés dans Fichiers ›
   NeoStation iOS › Library › Books.
5. **Favoris et lectures** regroupe les lectures en cours (livres locaux et
   chapitres en ligne) et les titres mis en favori ; ils restent même si la
   source est désactivée.
