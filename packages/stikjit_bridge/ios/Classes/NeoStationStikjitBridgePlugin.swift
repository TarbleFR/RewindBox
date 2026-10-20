import Flutter
import Foundation

/// Shared LocalDevVPN route probe. Embedded engines own their JIT transactions.
/// The retired external MeloNX launch method is no longer registered.
public final class NeoStationStikjitBridgePlugin: NSObject, FlutterPlugin {
  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "neostation/stikjit", binaryMessenger: registrar.messenger())
    registrar.addMethodCallDelegate(NeoStationStikjitBridgePlugin(), channel: channel)
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard call.method == "probeLocalDevVpnRoute" else {
      result(FlutterMethodNotImplemented)
      return
    }
    LocalDevVpnRouteProbe.probe { response in result(response) }
  }
}
