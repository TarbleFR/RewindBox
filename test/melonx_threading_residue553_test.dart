import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/services/melonx_internal_service.dart';

// Builds 549-551 stored the standalone config's imported threading Off as a
// per-game backendThreading:false; 553 clears that residue once per game.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('a stored false next to the imported Off is cleared once per game', () async {
    const key = 'rewindbox.melonx.graphics.Switch/P4G.nsp';
    SharedPreferences.setMockInitialValues({key: '{"backendThreading":false,"showRamGraph":false}'});
    final prefs = await SharedPreferences.getInstance();
    final imported = {'backendThreading': 1, 'aspectRatio': 1};
    final saved = {'backendThreading': false, 'showRamGraph': false};
    expect(await MelonxInternalService.clearImportedThreading(prefs, key, imported, saved), {'showRamGraph': false});
    expect(jsonDecode(prefs.getString(key)!), {'showRamGraph': false});
    // Afterwards an explicit Off is the player's choice and stays.
    final chosen = {'backendThreading': false, 'showRamGraph': false};
    expect(await MelonxInternalService.clearImportedThreading(prefs, key, imported, chosen), chosen);
    // Without the imported Off, or with a stored On, nothing is touched.
    const other = 'rewindbox.melonx.graphics.Switch/P5R.nsp';
    expect(await MelonxInternalService.clearImportedThreading(prefs, other, {'backendThreading': 2}, {'backendThreading': false}),
        {'backendThreading': false});
    const third = 'rewindbox.melonx.graphics.Switch/Other.nsp';
    expect(await MelonxInternalService.clearImportedThreading(prefs, third, imported, {'backendThreading': true}),
        {'backendThreading': true});
  });
}
