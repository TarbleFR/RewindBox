import Foundation
import Network
import Darwin

final class NPHTTPServer {
    private let queue = DispatchQueue(label: "neoplay.http", qos: .userInitiated)
    private var listener: NWListener?
    private var connections: [ObjectIdentifier: NWConnection] = [:]
    private let store: NPSegmentStore?
    private let live: NPLiveSource?
    private let resource: String              // name of the live resource: live.mp4 (NPDirectStream) or frames (NPFramesStream)
    private let liveType: String
    private var liveKey: ObjectIdentifier? // the one connection that reads the endless stream
    private let secret = UUID().uuidString.replacingOccurrences(of: "-", with: "")
    var onLiveClosed: (() -> Void)?            // the receiver's connection to the endless stream ended (server queue)
    var onReceiverAgent: ((String) -> Void)?   // User-Agent of the receiver's request for the stream (server queue)
    // HLS: a segment store, resource index.m3u8. Direct route: an endless fragmented MP4, resource live.mp4. RewindBox
    // receiver: the same fragmented MP4 (its MediaSource engine), or the encoder's packets, resource frames.
    init(store: NPSegmentStore?, live: NPLiveSource? = nil, resource: String = "live.mp4", contentType: String = "video/mp4") {
        self.store = store; self.live = live; self.resource = live == nil ? "index.m3u8" : resource; liveType = contentType
    }
    func start(_ completion: @escaping (Result<URL, NPError>) -> Void) {
        let resource = self.resource
        guard let ip = Self.wifiAddress() else { completion(.failure(.wifiRequired)); return }
        do {
            // No Nagle delay: a fragment is one picture and must leave at once, not wait for the next one.
            let tcp = NWProtocolTCP.Options(); tcp.noDelay = true
            let parameters = NWParameters(tls: nil, tcp: tcp)
            parameters.includePeerToPeer = false
            let listener = try NWListener(using: parameters, on: .any); self.listener = listener
            var answered = false
            listener.stateUpdateHandler = { [weak self] state in
                guard let self, !answered else { return }
                switch state {
                case .ready:
                    answered = true
                    guard let port = listener.port, let url = URL(string: "http://\(ip):\(port.rawValue)/s/\(self.secret)/\(resource)") else { completion(.failure(.network)); return }
                    completion(.success(url))
                case .failed: answered = true; completion(.failure(.network))
                default: break
                }
            }
            listener.newConnectionHandler = { [weak self] connection in
                guard let self, self.connections.count < 8 else { connection.cancel(); return }
                let key = ObjectIdentifier(connection); self.connections[key] = connection
                connection.stateUpdateHandler = { [weak self] state in
                    if case .cancelled = state { self?.closed(key) }
                    if case .failed = state { connection.cancel() }
                }
                connection.start(queue: self.queue)
                // A request is answered within 8 s; the endless stream is the one connection that stays.
                self.queue.asyncAfter(deadline: .now() + 8) { [weak self] in if self?.liveKey != key { connection.cancel() } }
                self.read(connection, header: Data())
            }
            listener.start(queue: queue)
        } catch { completion(.failure(.network)) }
    }
    private func read(_ connection: NWConnection, header: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, complete, error in
            guard let self, error == nil else { connection.cancel(); return }
            var header = header; if let data { header.append(data) }
            guard header.count <= 8192 else { connection.cancel(); return }
            guard let text = String(data: header, encoding: .utf8), text.contains("\r\n\r\n") else {
                if complete { connection.cancel() } else { self.read(connection, header: header) }; return
            }
            let first = text.components(separatedBy: "\r\n")[0].split(separator: " ")
            guard first.count == 3, ["GET", "HEAD", "OPTIONS"].contains(String(first[0])) else { connection.cancel(); return }
            let prefix = "/s/\(self.secret)/", target = String(first[1])
            if first[0] == "GET", target == prefix + self.resource, let live = self.live, live.isReady {
                // A request that resumes at a byte offset is the player retrying a broken connection: the stream has no such
                // offset. Refusing it makes the player give up, and the sender loads the stream again from the live picture.
                if let range = Self.header("range", in: text), range.hasPrefix("bytes="), !range.hasPrefix("bytes=0-") { connection.cancel(); return }
                self.serveLive(connection, stream: live, agent: Self.header("user-agent", in: text)); return
            }
            let result: (Int, String, Data)
            if !target.hasPrefix(prefix) { result = (403, "text/plain", Data()) }
            else if first[0] == "OPTIONS" { result = (204, "text/plain", Data()) }
            else if let store = self.store { result = store.response(String(target.dropFirst(prefix.count))) }
            else { result = (target == prefix + self.resource ? 503 : 404, "text/plain", Data()) }
            let status = result.0, body = result.2
            let reasons = [200:"OK", 204:"No Content", 403:"Forbidden", 404:"Not Found", 503:"Service Unavailable"]
            var response = Data("HTTP/1.1 \(status) \(reasons[status] ?? "Error")\r\nContent-Type: \(result.1)\r\nContent-Length: \(body.count)\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, HEAD, OPTIONS\r\nAccess-Control-Allow-Headers: Range\r\nAccess-Control-Allow-Private-Network: true\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n".utf8)
            if first[0] != "HEAD" { response.append(body) }
            connection.send(content: response, completion: .contentProcessed { _ in connection.cancel() })
        }
    }
    // One endless chunked response. The stream starts it on the next key picture and reports how many bytes
    // wait in the connection, which is how it knows that the link cannot follow.
    private func serveLive(_ connection: NWConnection, stream: NPLiveSource, agent: String?) {
        let key = ObjectIdentifier(connection)
        let previous = liveKey.flatMap { connections[$0] }
        liveKey = key
        previous?.cancel() // one receiver at a time: a new request (a reload) replaces the previous connection
        if let agent { onReceiverAgent?(agent) }
        let waiting = NPPendingBytes()
        let head = "HTTP/1.1 200 OK\r\nContent-Type: \(liveType)\r\nTransfer-Encoding: chunked\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Private-Network: true\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
        connection.send(content: Data(head.utf8), completion: .contentProcessed { error in if error != nil { connection.cancel() } })
        let accepted = stream.attach(send: { [weak connection] data in
            guard let connection else { return }
            var chunk = Data(String(data.count, radix: 16).utf8); chunk.append(contentsOf: [13, 10]); chunk.append(data); chunk.append(contentsOf: [13, 10])
            let size = chunk.count; waiting.add(size)
            connection.send(content: chunk, completion: .contentProcessed { error in waiting.add(-size); if error != nil { connection.cancel() } })
        }, pending: { waiting.value }, at: ProcessInfo.processInfo.systemUptime)
        if !accepted { connection.cancel() }
    }
    private func closed(_ key: ObjectIdentifier) {
        connections.removeValue(forKey: key)
        guard liveKey == key else { return }
        liveKey = nil; live?.detach(); onLiveClosed?()
    }
    // The stream stalled or changed its picture size: the receiver's connection is closed, a new load opens another.
    func closeLive() { queue.async { [self] in if let key = liveKey { connections[key]?.cancel() } } }
    private static func header(_ name: String, in request: String) -> String? {
        for line in request.components(separatedBy: "\r\n").dropFirst() {
            guard let colon = line.firstIndex(of: ":"), line[..<colon].lowercased() == name else { continue }
            return String(line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces).prefix(300))
        }
        return nil
    }
    func stop() { queue.async { [self] in listener?.cancel(); listener = nil; liveKey = nil; live?.detach(); connections.values.forEach { $0.cancel() }; connections.removeAll() } }
    private static func wifiAddress() -> String? {
        var list: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&list) == 0, let first = list else { return nil }; defer { freeifaddrs(list) }
        var entry: UnsafeMutablePointer<ifaddrs>? = first
        while let item = entry {
            defer { entry = item.pointee.ifa_next }
            guard String(cString: item.pointee.ifa_name) == "en0", let address = item.pointee.ifa_addr, address.pointee.sa_family == UInt8(AF_INET) else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            if getnameinfo(address, socklen_t(address.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST) == 0 { return String(cString: host) }
        }
        return nil
    }
}

// Bytes handed to a connection and not yet taken by the network.
final class NPPendingBytes {
    private let lock = NSLock()
    private var bytes = 0
    var value: Int { lock.lock(); defer { lock.unlock() }; return bytes }
    func add(_ count: Int) { lock.lock(); bytes += count; lock.unlock() }
}
