'use strict';
// Options of origin.js. run.js and matrix.js accept the same names and pass them through.
module.exports = {
  'port': { type: 'number', default: 8765, help: 'TCP port of the origin (0 = any free port; the real one is in the "ready" line)' },
  'host': { type: 'string', default: '127.0.0.1', help: 'listen address' },
  'prefix': { type: 'string', default: '/s/lab/', help: 'URL prefix of the stream (the sender uses /s/<secret>/); everything else answers 403' },
  // encoder
  'seg': { type: 'number', default: 0.5, help: 'segment length in seconds (a whole number of frames): 1 = pre-743 sender, 0.5 = IPA 743' },
  'gop': { type: 'number', default: 0, help: 'key picture interval in seconds (0 = one per segment, as the sender); must divide --seg' },
  'long-segments': { type: 'string', default: '', help: 'comma-separated sequence numbers of segments made twice as long (two GOPs in one segment): irregular EXTINF' },
  'fps': { type: 'number', default: 60, help: 'frames per second of the test stream' },
  'size': { type: 'string', default: '640x360', help: 'picture size WxH (width >= 368: the frame counter needs 23 blocks of 16 px)' },
  'bitrate': { type: 'number', default: 1000, help: 'video bit rate, kbit/s (x264 baseline, ultrafast, zerolatency)' },
  'audio-bitrate': { type: 'number', default: 96, help: 'AAC-LC bit rate, kbit/s (48 kHz stereo)' },
  'ffmpeg': { type: 'string', default: 'ffmpeg', help: 'ffmpeg executable' },
  'max-seconds': { type: 'number', default: 3600, help: 'safety: ffmpeg stops by itself after this many seconds' },
  'exit-after': { type: 'number', default: 0, help: 'origin exits by itself after this many seconds (0 = until killed or /control/stop)' },
  // playlist policy (defaults = NPSegmentStore.response)
  'window-segments': { type: 'number', default: 6, help: 'playlist advertises at least this many segments (NPPolicy.castWindowSegments)' },
  'window-seconds': { type: 'number', default: 3, help: '... and at least this many seconds (NPPolicy.castWindowSeconds)' },
  'start-segments': { type: 'number', default: 3, help: 'playlist answers 503 until this many segments exist (NPPolicy.castStartSegments)' },
  'target-duration': { type: 'string', default: '1', help: '#EXT-X-TARGETDURATION value; "auto" = ceil(segment length)' },
  'hls-version': { type: 'number', default: 7, help: '#EXT-X-VERSION value' },
  'store-segments': { type: 'number', default: 24, help: 'segments kept in RAM and still served after leaving the playlist (NPSegmentStore.maxSegments)' },
  'hold-back': { type: 'number', default: 0, help: 'adds #EXT-X-SERVER-CONTROL:HOLD-BACK=<s> (0 = tag absent, as the sender)' },
  'pdt': { type: 'bool', default: false, help: 'adds #EXT-X-PROGRAM-DATE-TIME (capture wall clock) before every segment' },
  'extra-tags': { type: 'string', default: '', help: 'extra playlist header lines, separated by "|" (inserted after #EXT-X-TARGETDURATION)' },
  // LL-HLS
  'part': { type: 'number', default: 0, help: 'LL-HLS part length in seconds (0 = no parts); a whole number of frames, must divide --seg' },
  'part-hold-back': { type: 'number', default: 0, help: 'PART-HOLD-BACK in seconds (0 with parts = 3 x part length)' },
  'can-block-reload': { type: 'bool', default: true, help: 'with parts: advertise CAN-BLOCK-RELOAD=YES and honour _HLS_msn/_HLS_part' },
  'parts-segments': { type: 'number', default: 3, help: 'with parts: number of newest complete segments that still list their parts' },
  'preload-hint': { type: 'bool', default: true, help: 'with parts: advertise #EXT-X-PRELOAD-HINT and block the hinted part request until it exists' },
  // network shaping
  'delay-ms': { type: 'number', default: 0, help: 'delay added to every stream response (half before the content is chosen, half before the first byte)' },
  'jitter-ms': { type: 'number', default: 0, help: 'uniform random +-jitter added to --delay-ms, per response' },
  'rate-kbps': { type: 'number', default: 0, help: 'throughput cap shared by all stream responses, kbit/s (0 = none)' },
  'outage-at': { type: 'number', default: -1, help: 'induced outage: seconds after origin start (-1 = none; run.js schedules its own, relative to the first frame)' },
  'outage-secs': { type: 'number', default: 2, help: 'induced outage length in seconds' },
  'outage-mode': { type: 'string', default: 'hold', help: 'hold = requests and bodies freeze and resume afterwards (lost Wi-Fi + TCP retransmission); reset = connections are destroyed during the outage' },
  'conn-timeout': { type: 'number', default: 8, help: 'a connection is cut this many seconds after accept (NPHTTPServer: 8); 0 = never' },
  'max-conns': { type: 'number', default: 8, help: 'connections beyond this many are refused (NPHTTPServer: 8); 0 = unlimited' },
  'log': { type: 'bool', default: false, help: 'print one JSON line per event (segment, request) on stdout' },
};
