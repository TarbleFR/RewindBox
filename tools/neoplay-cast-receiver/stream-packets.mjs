// Pure helpers of the RewindBox Cast receiver, shared with the Node checks.
//
// The phone serves the NeoPlay v2 packets (see protocol.mjs: 3 configuration,
// 4 picture, 5 sound) as one endless HTTP response, each packet preceded by its
// length (u32, big-endian). Network chunks cut packets anywhere: the splitter
// rebuilds them.
export class PacketSplitter {
  constructor(maxPacket = 4 * 1024 * 1024) { this.max = maxPacket; this.rest = new Uint8Array(0); }
  // Returns the packets completed by this chunk, oldest first. Throws on a length the protocol cannot carry.
  push(chunk) {
    const bytes = chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk);
    let data = bytes;
    if (this.rest.length) { data = new Uint8Array(this.rest.length + bytes.length); data.set(this.rest); data.set(bytes, this.rest.length); }
    const packets = [];
    let at = 0;
    while (data.length - at >= 4) {
      const size = (data[at] * 16777216) + (data[at + 1] << 16 | data[at + 2] << 8 | data[at + 3]);
      if (size === 0 || size > this.max) throw new Error(`Invalid packet length ${size}`);
      if (data.length - at - 4 < size) break;
      packets.push(data.subarray(at + 4, at + 4 + size)); at += 4 + size;
    }
    this.rest = data.slice(at);
    return packets;
  }
  get pending() { return this.rest.length; }
}

// Top-level MP4 boxes found in `bytes`, for the MediaSource engine, which must
// read the initialization segment (ftyp + moov) before it can name the codecs.
// Returns the end offset of the first moov, or -1 while it is incomplete.
export function initializationEnd(bytes) {
  let at = 0;
  while (bytes.length - at >= 8) {
    const size = bytes[at] * 16777216 + (bytes[at + 1] << 16 | bytes[at + 2] << 8 | bytes[at + 3]);
    const type = String.fromCharCode(bytes[at + 4], bytes[at + 5], bytes[at + 6], bytes[at + 7]);
    if (size < 8) throw new Error(`Invalid MP4 box ${type}`);
    if (type === 'moov') return bytes.length - at >= size ? at + size : -1;
    if (type !== 'ftyp') throw new Error(`Unexpected MP4 box ${type} before moov`);
    at += size;
  }
  return -1;
}

// Running figures of one statistics period: mean, 95th percentile and highest value.
export class Spread {
  constructor(limit = 600) { this.limit = limit; this.values = []; }
  add(value) { if (Number.isFinite(value)) { this.values.push(value); if (this.values.length > this.limit) this.values.shift(); } }
  get count() { return this.values.length; }
  summary({ reset = true } = {}) {
    const values = [...this.values].sort((a, b) => a - b);
    if (reset) this.values = [];
    if (!values.length) return null;
    const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
    const round = value => Math.round(value * 10) / 10;
    return { n: values.length, mean: round(mean), p95: round(values[Math.min(values.length - 1, Math.floor(values.length * 0.95))]), max: round(values[values.length - 1]), min: round(values[0]) };
  }
}

// Decides when the picture engine cannot follow the stream on this device: four
// consecutive seconds where fewer than 40 % of the pictures reach the screen,
// or where the decoder's queue stays at the point where pictures are skipped.
// The engine then asks for the MediaSource one. A display refreshing at 30 Hz
// still shows half of a 60 fps stream, and a hardware decoder may hold a few
// pictures in flight while keeping up: neither is a reason to leave (the time
// a picture spends in the decoder is reported, not judged).
// `sample` takes the counters of one second.
export class SlowWatch {
  constructor({ seconds = 4, minimumPictures = 20, queueLimit = 8 } = {}) { this.seconds = seconds; this.minimum = minimumPictures; this.queueLimit = queueLimit; this.run = 0; this.reason = null; }
  sample({ pictures, presented, queue }) {
    let reason = null;
    if (pictures >= this.minimum && presented < pictures * 0.4) reason = `presented ${presented}/${pictures}`;
    else if (queue >= this.queueLimit) reason = `queue ${queue}`;
    this.run = reason ? this.run + 1 : 0; this.reason = reason;
    return this.run >= this.seconds;
  }
}

// Playback-rate decision of the MediaSource engine: the media element plays an
// endless stream and never catches up by itself. `lag` is the buffered span
// ahead of the play head in seconds. Above `seekAbove` it jumps; above the
// target it plays slightly faster; a stall raises the target (up to `ceiling`),
// a calm minute lowers it again.
export class EdgeChase {
  constructor({ target = 0.3, floor = 0.2, ceiling = 1.0, seekAbove = 1.5 } = {}) {
    Object.assign(this, { target, floor, ceiling, seekAbove, rate: 1, stalls: 0, seeks: 0, calmSince: null });
  }
  stalled(now) { this.stalls++; this.target = Math.min(this.ceiling, this.target + 0.1); this.calmSince = now; }
  sample(lag, now) {
    if (this.calmSince === null) this.calmSince = now;
    if (now - this.calmSince > 60_000) { this.target = Math.max(this.floor, this.target - 0.04); this.calmSince = now; }
    if (lag > this.seekAbove) { this.seeks++; this.rate = 1; return { seek: true, rate: 1 }; }
    const excess = lag - this.target;
    this.rate = excess > 0.5 ? 1.25 : excess > 0.15 ? 1.1 : excess > 0.04 && this.rate > 1 ? 1.05 : 1;
    return { seek: false, rate: this.rate };
  }
}
