"""Execute the production audio handoff/observer methods with a session double."""
from pathlib import Path
import hashlib, json, os, subprocess, tempfile
ROOT = Path(__file__).resolve().parents[1]
FRONT = 'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift'
GAME = 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift'
def method(source, name):
    start = source.index('    private func ' + name + '(')
    brace = source.index('{', start); end = brace + 1; depth = 1
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[start:end]
front = (ROOT/FRONT).read_text(); game = (ROOT/GAME).read_text()
stub = r'''import Foundation
let AVAudioSessionInterruptionTypeKey = "type"
let AVAudioSessionInterruptionOptionKey = "options"
struct UIApplication { static let didBecomeActiveNotification = Notification.Name("foreground") }
enum MeloNXLaunchJournal { static func record(_ stage:String,_ status:String,detail:String="") {} }
final class AVAudioSession: NSObject {
    enum Category:String { case ambient, playback }
    enum Mode:String { case `default` }
    struct CategoryOptions:OptionSet { let rawValue:Int; static let mixWithOthers=Self(rawValue:1) }
    struct InterruptionOptions:OptionSet { let rawValue:UInt; static let shouldResume=Self(rawValue:1) }
    enum InterruptionType:UInt { case ended=0, began=1 }
    struct Port { let rawValue="Speaker" }
    struct Output { let portType=Port() }
    struct Route { let outputs=[Output()] }
    static let routeChangeNotification=Notification.Name("route")
    static let interruptionNotification=Notification.Name("interruption")
    static let instance=AVAudioSession()
    static func sharedInstance()->AVAudioSession { instance }
    var category=Category.ambient,mode=Mode.default,categoryOptions:CategoryOptions=[.mixWithOthers]
    var preferredSampleRate=44100.0,preferredIOBufferDuration=0.023
    var sampleRate=48000.0,ioBufferDuration=256.0/48000.0,currentRoute=Route()
    var active=false,categoryWrites=0,activations=0,rejectPreferences=false
    func setCategory(_ c:Category,mode m:Mode,options:CategoryOptions) throws {
        category=c;mode=m;categoryOptions=options;categoryWrites += 1
        NotificationCenter.default.post(name:Self.routeChangeNotification,object:self)
    }
    func setActive(_ value:Bool) throws { active=value;activations += 1 }
    func setPreferredSampleRate(_ value:Double) throws {
        if rejectPreferences { throw NSError(domain:"preference",code:1) };preferredSampleRate=value
    }
    func setPreferredIOBufferDuration(_ value:TimeInterval) throws { preferredIOBufferDuration=value }
}
'''
front_methods='\n'.join(method(front,n) for n in ['installAudioSessionObservers','applySilentModeAudioSession'])
game_methods='\n'.join(method(game,n) for n in ['acquireAudio','activateAudio','installAudioObservers','restoreAudio'])
program = stub + '''
final class Frontend {
    private var audioSessionObservers:[NSObjectProtocol]=[]
    private var audioSessionKnownActive=false
    private var melonxOwnsAudioSession=false
    init(){installAudioSessionObservers()}
    func apply() throws { _ = try applySilentModeAudioSession(forceActivation:true) }
''' + front_methods + '''
}
final class GameAudio {
    private var previousAudio:(AVAudioSession.Category,AVAudioSession.Mode,AVAudioSession.CategoryOptions,Double,TimeInterval)?
    private var audioObservers:[NSObjectProtocol]=[]
    private static let audioOwnership=Notification.Name("RewindBox.MeloNX.AudioOwnership")
    init(){installAudioObservers()}
    func acquire() throws { try acquireAudio() }
    func beforeRun() throws { try activateAudio(reason:"beforeRun") }
    func release(){restoreAudio()}
''' + game_methods + '''
}
var checks=0
func check(_ value:Bool,_ text:String){precondition(value,text);checks += 1}
let frontend=Frontend(),audio=AVAudioSession.sharedInstance()
try frontend.apply()
check(audio.category == .ambient && audio.active,"menu policy changed")
let game=GameAudio()
try game.acquire()
check(audio.category == .playback,"route observer stole game ownership")
check(audio.preferredSampleRate == 48000 && abs(audio.preferredIOBufferDuration - 256.0/48000.0)<0.00001,"preferences not requested")
let writes=audio.categoryWrites
try frontend.apply()
NotificationCenter.default.post(name:AVAudioSession.routeChangeNotification,object:audio)
check(audio.categoryWrites == writes && audio.category == .playback,"frontend reconfigured active game")
try audio.setActive(false) // shared frontend device closed during presentation
try game.beforeRun()
check(audio.active,"handoff left session inactive")
try audio.setCategory(.ambient,mode:.default,options:[.mixWithOthers])
check(audio.category == .playback,"another audio client permanently changed game policy")
try audio.setActive(false)
NotificationCenter.default.post(name:AVAudioSession.interruptionNotification,object:audio,
 userInfo:[AVAudioSessionInterruptionTypeKey:NSNumber(value:0),AVAudioSessionInterruptionOptionKey:NSNumber(value:1)])
check(audio.active && audio.category == .playback,"interruption return restored menu policy")
game.release()
try frontend.apply()
check(audio.category == .ambient && audio.categoryOptions == [.mixWithOthers],"menu policy not restored")
check(audio.preferredSampleRate == 44100 && audio.preferredIOBufferDuration == 0.023,"previous preferences not restored")
let endedWrites=audio.categoryWrites
NotificationCenter.default.post(name:UIApplication.didBecomeActiveNotification,object:nil)
check(audio.categoryWrites == endedWrites,"closed game retook audio ownership")
audio.rejectPreferences=true
try game.acquire()
check(audio.active && audio.category == .playback,"advisory preference error blocked game")
audio.rejectPreferences=false;game.release()
print("PASS \\(checks) production audio ownership assertions; AVAudioSession double, no iPhone audio claim")
'''
with tempfile.TemporaryDirectory(prefix='melonx-audio-ownership-') as d:
    work=Path(d); path=work/'main.swift';path.write_text(program)
    subprocess.run(['swiftc',str(path),'-o',str(work/'probe')],check=True,timeout=120)
    result=subprocess.check_output([str(work/'probe')],text=True,stderr=subprocess.STDOUT,timeout=30)
    print(result)
# Compile the complete frontend plugin too: the MeloNX host check only covers
# its own module. The observer guard must type-check against the iPhone SDK.
sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
flutter=Path(os.environ['FLUTTER_ROOT'])/'bin/cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64'
sources=sorted((ROOT/'packages/external_folder_access/ios/Classes').glob('*.swift'))
subprocess.run(['xcrun','swiftc','-typecheck','-swift-version','5','-sdk',sdk,
    '-target','arm64-apple-ios18.0','-F',str(flutter),'-module-name','external_folder_access',*map(str,sources)],check=True,timeout=120)

out=ROOT/'dist/melonx-host/audio-ownership.json';out.parent.mkdir(parents=True,exist_ok=True)
inputs=[FRONT,GAME,'test/melonx_audio_ownership_test.py']
out.write_text(json.dumps(dict(result='passed',summary=result,physicalDeviceTested=False,
    sessionDouble=True, iphoneSDKTypecheck=True,inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}),indent=2)+'\n')

