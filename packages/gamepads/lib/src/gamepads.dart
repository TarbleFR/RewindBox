library;

import 'package:gamepads_platform_interface/api/gamepad_controller.dart';
import 'package:gamepads_platform_interface/api/gamepad_event.dart';
import 'package:gamepads_platform_interface/gamepads_platform_interface.dart';

class Gamepads {
  Gamepads._();

  static final _platform = GamepadsPlatformInterface.instance;

  static Future<List<GamepadController>> list() => _platform.listGamepads();

  static Stream<GamepadEvent> get events => _platform.gamepadEventsStream;

  /// Takes the controller input back once a game session has ended. See
  /// [GamepadsPlatformInterface.reclaimGamepads].
  static Future<void> reclaim() => _platform.reclaimGamepads();

  static Stream<GamepadEvent> eventsByGamepad(String gamepadId) {
    return events.where((event) => event.gamepadId == gamepadId);
  }
}
