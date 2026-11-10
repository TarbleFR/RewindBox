"""Private Liquid Glass UI build (BUILD below): the interface on the host of the validated 546 delivery (542 host, MeloNX close teardown 544, RPCS3 546 Core and its diagnostics files)."""
import argparse,fnmatch,hashlib,json,os,re
from pathlib import Path
import rpcs3cell546_delivery as rpc
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
HOST_TREE=close.BASE
MELONX_SOURCE,MELONX_RUN=close.MELONX_SOURCE,close.MELONX_RUN
HOST_SOURCE,HOST_RUN=close.HOST_SOURCE,close.HOST_RUN
CORE_SOURCE,CORE_RUN,HOST=rpc.CORE_SOURCE,rpc.CORE_RUN,rpc.HOST
validate_rpc_core_identity=rpc.validate_rpc_core_identity
validate_rpc_core_pin=rpc.validate_rpc_core_pin
validate_psp_core_identity=rpc.validate_psp_core_identity
logger_proofs=rpc.logger_proofs
command=previous.command
BUILD='548'
LOCAL='docs/evidence/liquid-glass-ui-local.json'
# Frontend paths the Liquid Glass work may change.
UI_SCOPE=['lib/themes/*','lib/widgets/*','lib/screens/*','lib/l10n/interface_style_locale.dart',
 'lib/providers/theme_provider.dart','lib/services/glass_performance_governor.dart','lib/responsive.dart',
 'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatBrowser.m','packages/neo_texture_catalog/ios/Classes/NeoTextureHDPage.m']
# Startup, storage, models, engines, dependencies and every other plugin keep
# the bytes of the validated 542 host (or of the proofs named in HOST_FIXED).
PROTECTED=['lib/main.dart','lib/data','lib/repositories','lib/models','lib/utils','lib/sync','native','assets','ios',
 'pubspec.yaml','pubspec.lock','lib/widgets/game_launch_dialog.dart']
# The interface ships on the tree of the validated 546 delivery (source
# 6c6c6241, run 40231210331). Later RPCS3 and MeloNX work keeps landing on
# Claude; the runner puts every path the interface does not own back to that
# exact tree before anything reads or builds it (working tree only, Git
# history unchanged), and the source contract refuses to run on anything else.
FIXED_STATE='6c6c624179540b860de16eab9c08323efaf12683'
# Host files fixed by the reused proofs: the MeloNX close fix (544) and the
# RPCS3 546 diagnostics files, byte-checked below exactly as the 546 delivery does.
HOST_FIXED=close.CHANGED|rpc.HOST546
TESTS=['test/interface_style_settings_test.dart','test/liquid_glass_theme_test.dart','test/glass_performance_governor_test.dart',
 'test/interface_style_locale_test.dart','test/main_menu_tab_strip_styles_test.dart','test/liquid_glass_settings_spacing_test.dart',
 'test/interface_style_screen_test.dart']

# The interface owns exactly the sources its local receipt hashes, plus its
# report and recipe files; a sibling change to any other path, even under
# lib/widgets, is not part of this build.
RECIPE=['docs/liquid-glass-ui.md',LOCAL,'.github/workflows/liquid-glass-ui-checks.yml','.github/workflows/liquid-glass-ui-delivery.yml',
 '.github/diagnostics/liquidglass_ui_delivery.py','build-utils/validate_liquid_glass_ipa.py','build-utils/delivery-'+BUILD+'-recipient.pem']

def in_scope(path):
 return path in HOST_FIXED or any(fnmatch.fnmatchcase(path,pattern) for pattern in UI_SCOPE)

def owned():
 inputs=set(json.loads((ROOT/LOCAL).read_text())['inputs'])
 assert all(any(fnmatch.fnmatchcase(p,pattern) for pattern in UI_SCOPE+['test/*']) for p in inputs),'receipt names a source outside the interface'
 return inputs|set(RECIPE)

def host_changed():
 """Working-tree paths that differ from the validated 542 host (after the restore below)."""
 return set(command('git','diff','--name-only',HOST_TREE,'--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())

def ui_changed():
 return host_changed()-HOST_FIXED

def drift():
 """Paths the interface does not own that later commits changed (to restore) or added (to remove)."""
 at_state=set(command('git','ls-tree','-r','--name-only',FIXED_STATE).splitlines())
 mine=owned()
 changed=[p for p in command('git','diff','--name-only',FIXED_STATE,'HEAD').splitlines() if p not in mine]
 return sorted(p for p in changed if p in at_state),sorted(p for p in changed if p not in at_state)

def restore_fixed_state():
 """Working tree only: everything but the interface becomes byte for byte the 546 delivery tree."""
 restored,removed=drift()
 for p in restored:command('git','checkout',FIXED_STATE,'--',p)
 for p in removed:
  if (ROOT/p).exists():(ROOT/p).unlink()
 assert_fixed_state()
 print(json.dumps(dict(fixedState=FIXED_STATE,restored=restored,removed=removed),indent=2))

def assert_fixed_state():
 restored,removed=drift()
 for p in restored:assert (ROOT/p).read_bytes()==close.at(FIXED_STATE,p),f'{p}: run --restore-fixed-state first'
 for p in removed:assert not (ROOT/p).exists(),f'{p}: run --restore-fixed-state first'
 return restored,removed

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 restored,removed=assert_fixed_state()
 changed=host_changed()
 outside=sorted(p for p in changed if not in_scope(p))
 assert not outside,outside
 protected=[p for p in command('git','diff','--name-only',HOST_TREE,'--',*PROTECTED).splitlines() if p not in HOST_FIXED]
 assert not protected,protected
 for p in close.CHANGED:assert (ROOT/p).read_bytes()==close.at(HOST_SOURCE,p),p
 for p in previous.IMPORT_INPUTS-close.CHANGED:assert (ROOT/p).read_bytes()==close.at(previous.SOURCE,p),p
 # The 546 diagnostics files ship exactly as built and tested with the 546
 # Core; the logger carries the timeline bound raised by the 546 delivery,
 # whose logger tests this delivery re-executes on the macOS job.
 for p in rpc.HOST546-{rpc.LOGGER}:assert (ROOT/p).read_bytes()==close.at(CORE_SOURCE,p),p
 logger=(ROOT/rpc.LOGGER).read_bytes()
 assert logger.replace(rpc.LOGGER_CHANGE[1],rpc.LOGGER_CHANGE[0])==close.at(CORE_SOURCE,rpc.LOGGER),rpc.LOGGER
 rpc.rpc.native.pin_module().validate_source_contract()
 for p,h in rpc.rpc.native.inputs().items():
  assert hashlib.sha256(close.at(CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==close.at(MELONX_SOURCE,p),p
 for p in close.ENGINE_INPUTS:assert (ROOT/p).read_bytes()==close.at(MELONX_SOURCE,p),p
 local=validate_local_evidence()
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=int(BUILD),hostTree=HOST_TREE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,hostFixed=sorted(HOST_FIXED),
  fixedState=FIXED_STATE,restored=restored,removed=removed,
  liquidGlassChanged=sorted(ui_changed()),liquidGlassSource=local['source'],liquidGlassTests=local['passedTests'],
  physicalDeviceTested=False,closeTeardownDeviceVerified=False,jitCompressionDeviceMeasured=False,interfaceDeviceReviewed=False)

def validate_local_evidence():
 """The local Flutter analysis and test receipt names the exact UI sources it covered."""
 local=json.loads((ROOT/LOCAL).read_text())
 assert local['result']=='passed' and local['physicalDeviceTested'] is False
 assert local['flutter']=='3.47.2' and local['passedTests']>=120
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 assert set(TESTS)<=set(local['tests'])
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 assert set(local['inputs'])>=ui_changed()|set(TESTS),sorted((ui_changed()|set(TESTS))-set(local['inputs']))
 return local

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--restore-fixed-state',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation-liquid-glass.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 if a.restore_fixed_state:restore_fixed_state();return
 report=source_contract()
 if a.retain_checks:
  rpc.retain_checks()
  out=ROOT/'build/delivery/liquid-glass-ui-tests.json'
  out.write_text(json.dumps(validate_local_evidence(),indent=2)+'\n')
 if a.logger_proofs:logger_proofs();print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,[
   'Execute compiled GPU texture teardown ownership and deferred-release concurrency',
   'Exercise speculative pipeline recovery and preserve fatal GPU errors',
   'Retain effective graphics journal regression proof',
   'Exercise the selected Apple audio backend and update target selection',
   'Execute production audio accounting and Vulkan failure regressions',
   'Compile NativeAOT library and verify exported ABI',
   'Exercise this exact rebuilt engine in an ARM64 iOS app'])
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,[
   'Compile the iPhone host and execute its native ABI scenarios',
   'Exercise audio ownership, route changes and presentation handoff',
   'Exercise registered plugin presentation and retry in actual UIKit'])
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
