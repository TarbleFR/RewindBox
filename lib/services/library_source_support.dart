import 'library_manga_models.dart';

/// Site template a source is built on (upstream Aidoku engine).
enum LibrarySourceEngine {
  /// WordPress Madara theme (wp-manga).
  madara,

  /// Madara with the Mangas Origines "child-origines" theme (ori-* markup).
  madaraOrigines,

  /// WordPress MangaThemesia / MangaStream theme (ts_reader).
  mangaThemesia,

  /// LelscanFR Laravel/Tailwind site.
  lelscan,

  /// Next.js application with a JSON API (Astral Manga since 2026-02).
  nextJsApp,

  /// Custom JSON REST API (PhenixScans).
  restApi,

  /// My Manga Reader CMS (Manga Scan).
  mmrcms,

  /// Keyoapp WordPress template (Reaper Scans FR).
  keyoapp,

  /// Custom Nuxt site + JSON API (LegacyScans).
  customApi,

  unknown,
}

/// State of a source as last verified, before any runtime health check.
enum LibrarySourceKnownState {
  /// Listing, details, chapters, pages and images answered.
  working,

  /// The site moved to a different platform the adapter does not read.
  siteChanged,

  /// Every request gets an anti-bot browser verification.
  challenge,

  /// The origin is down behind its proxy (HTTP 5xx / Cloudflare 52x).
  serverUnavailable,

  /// The domain no longer resolves or only serves a placeholder.
  offline,

  /// The domain is parked (ad/parking page).
  parked,

  /// No native adapter exists for this source.
  adapterMissing,

  unknown,
}

/// Why `LibraryAidokuNativeService.supports` returns false.
enum LibrarySourceUnsupportedReason {
  /// The site became another application (Next.js) behind a challenge.
  siteMigratedBehindChallenge,

  /// The domain is parked.
  domainParked,

  /// The domain does not resolve or only serves a placeholder.
  siteOffline,

  /// The proxy cannot reach the origin (Cloudflare 522/525).
  originUnreachable,

  /// The source is not one of the sources NeoStation has an adapter for.
  adapterMissing,

  /// The addon is not an Aidoku repository source.
  notAidokuSource,
}

/// Static, evidence-based support information for one Aidoku source.
class LibrarySourceSupport {
  const LibrarySourceSupport({
    required this.sourceId,
    required this.name,
    required this.engine,
    required this.hasAdapter,
    required this.knownState,
    required this.websiteUrl,
    this.unsupportedReason,
    this.verifiedOn,
    this.navigationVerified = false,
    this.readingVerified = false,
    this.evidence = '',
    this.listings = const <LibraryMangaListing>[],
  });

  final String sourceId;
  final String name;
  final LibrarySourceEngine engine;

  /// A native adapter exists and `supports()` is true. A source may have an
  /// adapter while [knownState] is not [LibrarySourceKnownState.working]
  /// (it stays callable so a health check can detect recovery).
  final bool hasAdapter;
  final LibrarySourceKnownState knownState;
  final LibrarySourceUnsupportedReason? unsupportedReason;
  final String websiteUrl;

  /// Day of the last verification (from a Windows PC, not an iPhone).
  final DateTime? verifiedOn;

  /// Listing + details + chapter list were obtained on [verifiedOn].
  final bool navigationVerified;

  /// A chapter page list and its first image were obtained on [verifiedOn].
  final bool readingVerified;

  /// Short English technical note (raw diagnostic, not user text).
  final String evidence;

  /// Listings the adapter exposes, default first.
  final List<LibraryMangaListing> listings;
}

/// Verified status of the ten French Aidoku sources (2026-10-10).
abstract final class LibrarySourceSupportRegistry {
  static final DateTime verifiedOn = DateTime.utc(2026, 10, 10);

  static final Map<String, LibrarySourceSupport> sources =
      Map<String, LibrarySourceSupport>.unmodifiable(
        <String, LibrarySourceSupport>{
          'fr.mangasorigines': LibrarySourceSupport(
            sourceId: 'fr.mangasorigines',
            name: 'Mangas Origines',
            engine: LibrarySourceEngine.madaraOrigines,
            hasAdapter: true,
            knownState: LibrarySourceKnownState.working,
            websiteUrl: 'https://mangas-origines.fr/',
            verifiedOn: verifiedOn,
            navigationVerified: true,
            readingVerified: true,
            evidence:
                'HTTP 200 without challenge for any non-empty, non-curl UA. '
                'madara_load_more listings (16/page), madara_child_catalogue '
                'search JSON, ori-sr details with ori-chl chapter rows in the '
                'same page, div.page-break images; image 200 image/jpeg.',
            listings: const <LibraryMangaListing>[
              LibraryMangaListing.latest,
              LibraryMangaListing.popular,
              LibraryMangaListing.trending,
            ],
          ),
          'fr.lelscanfr': LibrarySourceSupport(
            sourceId: 'fr.lelscanfr',
            name: 'LelscanFR',
            engine: LibrarySourceEngine.lelscan,
            hasAdapter: true,
            knownState: LibrarySourceKnownState.working,
            websiteUrl: 'https://www.lelscanfr.com/',
            verifiedOn: verifiedOn,
            navigationVerified: true,
            readingVerified: true,
            evidence:
                'Apex 301 to www; HTTP 200 behind Cloudflare without '
                'challenge. Catalogue 24/page, chapter list paginated by 100 '
                '(One Piece 546 over 6 pages), details TTFB up to 14 s, '
                'reader 13 images, image 200 image/webp without Referer.',
            listings: const <LibraryMangaListing>[
              LibraryMangaListing.latest,
              LibraryMangaListing.popular,
              LibraryMangaListing.newest,
            ],
          ),
          'fr.sushiscan': LibrarySourceSupport(
            sourceId: 'fr.sushiscan',
            name: 'SushiScan',
            engine: LibrarySourceEngine.mangaThemesia,
            hasAdapter: true,
            knownState: LibrarySourceKnownState.working,
            websiteUrl: 'https://sushiscan.net/',
            verifiedOn: verifiedOn,
            navigationVerified: true,
            readingVerified: true,
            evidence:
                'HTTP 200 without challenge (empty/curl UA get 403). Listing '
                '30/page over 145 pages, search 10/page (404 past the end), '
                'ts_reader page lists; images need Referer '
                'https://sushiscan.net/ exactly (403 otherwise). No new '
                'release since about 2026-05.',
            listings: const <LibraryMangaListing>[
              LibraryMangaListing.latest,
              LibraryMangaListing.popular,
              LibraryMangaListing.newest,
            ],
          ),
          'fr.sushiscans': LibrarySourceSupport(
            sourceId: 'fr.sushiscans',
            name: 'Sushi Scans',
            engine: LibrarySourceEngine.mangaThemesia,
            hasAdapter: true,
            knownState: LibrarySourceKnownState.serverUnavailable,
            websiteUrl: 'https://sushiscan.fr/',
            verifiedOn: verifiedOn,
            evidence:
                'openresty answers HTTP 504 after about 5.2 s for every '
                'uncached request (chapters, search, page images on '
                's22.anime-sama.me); only cached listing pages 1-2 and some '
                'details pages answer 200. Origin outage, not anti-bot.',
            listings: const <LibraryMangaListing>[
              LibraryMangaListing.latest,
              LibraryMangaListing.popular,
              LibraryMangaListing.newest,
            ],
          ),
          'fr.mangascantrad': LibrarySourceSupport(
            sourceId: 'fr.mangascantrad',
            name: 'Manga Scantrad',
            engine: LibrarySourceEngine.madara,
            hasAdapter: true,
            knownState: LibrarySourceKnownState.challenge,
            websiteUrl: 'https://manga-scantrad.io/',
            verifiedOn: verifiedOn,
            evidence:
                'Every path returns HTTP 403 cf-mitigated: challenge for '
                'every UA tried; image CDN stockage.manga-scantrad.net '
                'returns 504 after 30 s. Generic Madara adapter kept so a '
                'health check can detect recovery.',
            listings: const <LibraryMangaListing>[
              LibraryMangaListing.latest,
              LibraryMangaListing.popular,
              LibraryMangaListing.trending,
            ],
          ),
          'fr.astralmanga': LibrarySourceSupport(
            sourceId: 'fr.astralmanga',
            name: 'Astral Manga',
            engine: LibrarySourceEngine.nextJsApp,
            hasAdapter: false,
            knownState: LibrarySourceKnownState.siteChanged,
            unsupportedReason:
                LibrarySourceUnsupportedReason.siteMigratedBehindChallenge,
            websiteUrl: 'https://astral-manga.fr/',
            verifiedOn: verifiedOn,
            evidence:
                'Site replaced by a Next.js app with UUID ids and presigned '
                'S3 images (2026-02); all 24 probes returned HTTP 403 '
                'cf-mitigated: challenge. The Madara adapter cannot work.',
          ),
          'fr.phenixscans': LibrarySourceSupport(
            sourceId: 'fr.phenixscans',
            name: 'PhenixScans',
            engine: LibrarySourceEngine.restApi,
            hasAdapter: false,
            knownState: LibrarySourceKnownState.parked,
            unsupportedReason: LibrarySourceUnsupportedReason.domainParked,
            websiteUrl: 'https://phenix-scans.com/',
            verifiedOn: verifiedOn,
            evidence:
                'Nameservers parklogic.com; every API path returns a 5.6 KB '
                'parking HTML page; non-browser UAs get the connection '
                'closed. Original group gone since 2025-09.',
          ),
          'fr.mangascan': LibrarySourceSupport(
            sourceId: 'fr.mangascan',
            name: 'Manga Scan',
            engine: LibrarySourceEngine.mmrcms,
            hasAdapter: false,
            knownState: LibrarySourceKnownState.parked,
            unsupportedReason: LibrarySourceUnsupportedReason.domainParked,
            websiteUrl: 'http://mangascan-fr.com/',
            verifiedOn: verifiedOn,
            evidence:
                'mangascan-fr.com is parked (parklogic nameservers, '
                '"Redirecting..." page, robots Disallow: /); successor '
                'domains .co and .net are NXDOMAIN.',
          ),
          'fr.reaperscans': LibrarySourceSupport(
            sourceId: 'fr.reaperscans',
            name: 'Reaper Scans FR',
            engine: LibrarySourceEngine.keyoapp,
            hasAdapter: false,
            knownState: LibrarySourceKnownState.offline,
            unsupportedReason: LibrarySourceUnsupportedReason.siteOffline,
            websiteUrl: 'https://reaperscans.fr/',
            verifiedOn: verifiedOn,
            evidence:
                'reaperscans.fr: DNS SERVFAIL (lame Cloudflare delegation); '
                'reaper-scans.fr serves a 4-byte placeholder and 404 on '
                'every Madara and Keyoapp path.',
          ),
          'fr.legacyscans': LibrarySourceSupport(
            sourceId: 'fr.legacyscans',
            name: 'LegacyScans',
            engine: LibrarySourceEngine.customApi,
            hasAdapter: false,
            knownState: LibrarySourceKnownState.offline,
            unsupportedReason: LibrarySourceUnsupportedReason.originUnreachable,
            websiteUrl: 'https://legacy-scans.com/',
            verifiedOn: verifiedOn,
            evidence:
                'All 23 requests to legacy-scans.com, www and api returned '
                'Cloudflare HTTP 522 after about 19.5 s; CDN images 525. '
                'Domain still registered; upstream code also obsolete.',
          ),
        },
      );

  /// Support information for [sourceId]; an "adapter missing" entry for
  /// sources outside the verified list.
  static LibrarySourceSupport forSourceId(String sourceId) {
    return sources[sourceId] ??
        LibrarySourceSupport(
          sourceId: sourceId,
          name: sourceId,
          engine: LibrarySourceEngine.unknown,
          hasAdapter: false,
          knownState: LibrarySourceKnownState.adapterMissing,
          unsupportedReason: LibrarySourceUnsupportedReason.adapterMissing,
          websiteUrl: '',
        );
  }
}
