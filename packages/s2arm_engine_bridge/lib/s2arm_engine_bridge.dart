/// Host side of the embedded Switch 2 engine. The app talks to it through
/// `lib/services/s2arm_internal_service.dart`; this library only names the
/// channel so that both sides use one spelling.
library;

const s2armInternalChannelName = 'neostation/s2arm_internal';
