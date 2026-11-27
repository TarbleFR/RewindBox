/// Service support and RewindBox device validation are independent facts.
enum WiimmfiCompatibility { full, partial, unsupported, unverified }

class WiimmfiGameCandidate {
  const WiimmfiGameCandidate(
    this.name, {
    this.compatibility = WiimmfiCompatibility.unverified,
    this.validatedOnDevice = false,
  });
  final String name;
  final WiimmfiCompatibility compatibility;
  final bool validatedOnDevice;
}

abstract final class WiimmfiCatalog {
  static const source = 'https://wiimmfi.de/stat';
  // Official site returned HTTP 403 on 2026-11-27. These are the maintainer's
  // candidates, not an imported or certified official compatibility list.
  static const candidates = [
    WiimmfiGameCandidate('Mario Kart Wii'),
    WiimmfiGameCandidate('Super Smash Bros. Brawl'),
    WiimmfiGameCandidate('Mario Strikers Charged Football'),
    WiimmfiGameCandidate('Mario Sports Mix'),
    WiimmfiGameCandidate('Animal Crossing: Let’s Go to the City'),
    WiimmfiGameCandidate('Sonic & SEGA All-Stars Racing'),
    WiimmfiGameCandidate('Tatsunoko vs. Capcom'),
    WiimmfiGameCandidate('Fortune Street'),
    WiimmfiGameCandidate('Inazuma Eleven GO Strikers 2013'),
  ];
}
