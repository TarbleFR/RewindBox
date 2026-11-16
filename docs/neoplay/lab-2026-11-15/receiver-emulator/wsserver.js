'use strict';
// Minimal RFC 6455 WebSocket server (text frames only) - enough to play the
// cast shell's IPC endpoint ws://localhost:<port>/v2/ipc. No dependency.
const http = require('http');
const crypto = require('crypto');
const { EventEmitter } = require('events');

class Peer extends EventEmitter {
  constructor(socket) {
    super();
    this.socket = socket;
    this.buffer = Buffer.alloc(0);
    this.fragments = [];
    this.open = true;
    socket.on('data', (chunk) => { this.buffer = Buffer.concat([this.buffer, chunk]); this.parse(); });
    socket.on('close', () => { if (this.open) { this.open = false; this.emit('close'); } });
    socket.on('error', () => {});
  }
  parse() {
    for (;;) {
      const b = this.buffer;
      if (b.length < 2) return;
      const fin = (b[0] & 0x80) !== 0, opcode = b[0] & 0x0f, masked = (b[1] & 0x80) !== 0;
      let length = b[1] & 0x7f, offset = 2;
      if (length === 126) { if (b.length < 4) return; length = b.readUInt16BE(2); offset = 4; }
      else if (length === 127) { if (b.length < 10) return; length = Number(b.readBigUInt64BE(2)); offset = 10; }
      const maskLength = masked ? 4 : 0;
      if (b.length < offset + maskLength + length) return;
      let payload = Buffer.from(b.subarray(offset + maskLength, offset + maskLength + length));
      if (masked) { const mask = b.subarray(offset, offset + 4); for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3]; }
      this.buffer = b.subarray(offset + maskLength + length);
      if (opcode === 0x8) { this.frame(0x8, Buffer.alloc(0)); this.socket.end(); return; }
      if (opcode === 0x9) { this.frame(0xA, payload); continue; }
      if (opcode === 0xA) continue;
      this.fragments.push(payload);
      if (fin) { const text = Buffer.concat(this.fragments).toString('utf8'); this.fragments = []; this.emit('message', text); }
    }
  }
  frame(opcode, payload) {
    if (!this.open) return;
    let header;
    if (payload.length < 126) header = Buffer.from([0x80 | opcode, payload.length]);
    else if (payload.length < 65536) { header = Buffer.alloc(4); header[0] = 0x80 | opcode; header[1] = 126; header.writeUInt16BE(payload.length, 2); }
    else { header = Buffer.alloc(10); header[0] = 0x80 | opcode; header[1] = 127; header.writeBigUInt64BE(BigInt(payload.length), 2); }
    this.socket.write(Buffer.concat([header, payload]));
  }
  send(text) { this.frame(0x1, Buffer.from(text, 'utf8')); }
  close() { this.frame(0x8, Buffer.alloc(0)); this.socket.end(); }
}

// listen(port, path, onPeer) -> Promise<{port, close}>
function listen(port, path, onPeer) {
  const server = http.createServer((req, res) => { res.writeHead(404); res.end(); });
  const sockets = new Set();
  server.on('connection', (s) => { sockets.add(s); s.on('close', () => sockets.delete(s)); });
  server.on('upgrade', (req, socket) => {
    if (req.url.split('?')[0] !== path || (req.headers.upgrade || '').toLowerCase() !== 'websocket') { socket.destroy(); return; }
    const accept = crypto.createHash('sha1').update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
    socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n');
    socket.setNoDelay(true);
    onPeer(new Peer(socket), req);
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve({
      port: server.address().port,
      close: () => new Promise((done) => { for (const s of sockets) s.destroy(); server.close(() => done()); }),
    }));
  });
}

module.exports = { listen };
