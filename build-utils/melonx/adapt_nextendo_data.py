"""Nextendo Network's per-title data for the embedded Switch engine's online sessions (after adapt_nextendo_online).

Nextendo's integration guide for emulators and client apps (wiki.nextendo.network/integration, read 17 November 2026):
- "BCAT data": some titles need their delivery data to show menus or rotations (Splatoon 2 and 3, Pokemon Scarlet and
  Violet, Legends: Z-A, Sword and Shield, Nintendo Switch Sports, Super Smash Bros. Ultimate: "otherwise the menu banner
  asks to connect to the Internet"); download it from nextendo.network/api/bcat/<titleId> and serve it from a folder;
- Animal Crossing: New Horizons must receive the account's BAAS user id (the `nsa` field of /api/me) as its network
  service account id instead of the PID;
- the exact game version is read from Nextendo's signed game catalog.

The host (Dart, then Swift) downloads and unpacks a title's BCAT zip to <data root>/nextendo/bcat/<title id>/, asks /api/me
for Animal Crossing, reads the catalog, and adds three optional keys to the online request of the launch: bcatDirectory,
nsa and acceptedVersions (native/melonx/EmbeddedOnline.cs parses them; a malformed one is left out, never the session).

Engine edits, each inert without an online session that carries the part:
  native/melonx/EmbeddedDeliveryCache.cs (copied into Ryujinx.Horizon by prepare_embedded): the served folder, listed and
      digested once at the session's start, and the three delivery cache IPC services over it, with LibHac's results.
  Ryujinx.Horizon/Bcat/Ipc/ServiceCreator.cs: CreateDeliveryCacheStorageService (by process) serves the folder when the
      process's application (arp:r) is the folder's title; CreateDeliveryCacheStorageServiceWithApplicationId does for
      that title on the ports LibHac lets mount another application's storage (not bcat:u, which keeps its
      PermissionDenied). Every other request takes LibHac's path unchanged.
  ManagerServer.cs: when the game first asks for its id_token online, one journal line (title, installed version,
      whether the catalog accepts it, BCAT data served, NSA or PID); the version passed to the token is unchanged.
  EmbeddedOnline.AccountId (native): the NSA when the request gives one, the PID otherwise.

Sync requests: IBcatService.RequestSyncDeliveryCache (10100) already returns a progress service whose GetImpl answers
Done with result 0 and whose event is created signalled (upstream Ryujinx.Horizon), so a game's sync completes at once
and then reads the served storage. Not handled here: Nextendo's signed NPLN patches (they need the main executable's
build id), the /api/nex-session heartbeat (host side). Not run on an iPhone.

Fail closed on drift: ServiceCreator.cs is pinned to the pristine bytes, ManagerServer.cs to the bytes
adapt_nextendo_online leaves; no later adapter edits either.
"""
import hashlib
from pathlib import Path

SERVICE_CREATOR = 'src/Ryujinx.Horizon/Bcat/Ipc/ServiceCreator.cs'
MANAGER = 'src/Ryujinx.HLE/HOS/Services/Account/Acc/AccountService/ManagerServer.cs'

BASELINE = {
    SERVICE_CREATOR: '672efc94ae16d396a4919045550c02e8060b9512e929cb409f68fa35c445a949',
    MANAGER: 'b19a6edad689dbab593367cc71c22b349b5245f0ae9c11356ee653c18ceefd3b',
}

PROCESS_OLD = '''        public Result CreateDeliveryCacheStorageService(out IDeliveryCacheStorageService service, [ClientProcessId] ulong pid)
        {
'''
PROCESS_NEW = '''        public Result CreateDeliveryCacheStorageService(out IDeliveryCacheStorageService service, [ClientProcessId] ulong pid)
        {
            // RewindBox (adapt_nextendo_data): the online session's BCAT data, served from the host's folder to the process
            // of the folder's title; any other request goes to LibHac as before.
            if (EmbeddedDeliveryCache.TryCreateForProcess(pid, out service))
            {
                return Result.Success;
            }

'''
APPLICATION_OLD = '''        public Result CreateDeliveryCacheStorageServiceWithApplicationId(out IDeliveryCacheStorageService service, ApplicationId applicationId)
        {
'''
APPLICATION_NEW = '''        public Result CreateDeliveryCacheStorageServiceWithApplicationId(out IDeliveryCacheStorageService service, ApplicationId applicationId)
        {
            // RewindBox (adapt_nextendo_data): the served title's storage, on the ports LibHac lets mount another
            // application's (bcat:u keeps LibHac's PermissionDenied).
            if (_permissionLevel != BcatServicePermissionLevel.User && EmbeddedDeliveryCache.TryCreateForApplication(applicationId.Id, out service))
            {
                return Result.Success;
            }

'''
MANAGER_OLD = '''                _cachedTokenData = Encoding.ASCII.GetBytes(GenerateIdToken(Ryujinx.HLE.EmbeddedOnline.Enabled ? context.Device.Processes.ActiveApplication.DisplayVersion : null));
'''
MANAGER_NEW = '''                // RewindBox (adapt_nextendo_data): the session's journal line (title, installed version against the catalog,
                // BCAT data, account id) when the game first asks for its token online; the version is passed on unchanged.
                _cachedTokenData = Encoding.ASCII.GetBytes(GenerateIdToken(Ryujinx.HLE.EmbeddedOnline.Enabled ? Ryujinx.HLE.EmbeddedOnline.NoteVersion(context.Device.Processes.ActiveApplication.ProgramIdText, context.Device.Processes.ActiveApplication.DisplayVersion) : null));
'''

PAIRS = (
    (SERVICE_CREATOR, PROCESS_OLD, PROCESS_NEW),
    (SERVICE_CREATOR, APPLICATION_OLD, APPLICATION_NEW),
    (MANAGER, MANAGER_OLD, MANAGER_NEW),
)


def once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, (str(path), old[:90], text.count(old))
    path.write_text(text.replace(old, new), encoding='utf-8')


def apply(source):
    """Edits the prepared tree; EmbeddedDeliveryCache.cs is copied there with the native files (prepare_embedded)."""
    source = Path(source)
    for name, expected in BASELINE.items():
        actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
        assert actual == expected, 'Preparation drift, refusing to adapt: ' + name
    for name, old, new in PAIRS:
        once(source / name, old, new)
    return [source / name for name in BASELINE]


if __name__ == '__main__':
    import sys
    for path in apply(sys.argv[1]):
        print(path)
