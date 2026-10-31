import Foundation
import SQLite3

// Ownership is private to AchievementTranslationCache's actor. This wrapper only
// makes final handle destruction safe from a nonisolated actor deinitializer;
// no caller can access or concurrently use the raw connection.
private final class SQLiteConnection: @unchecked Sendable {
    let handle: OpaquePointer
    init(_ handle: OpaquePointer) { self.handle = handle }
    deinit { sqlite3_close_v2(handle) }
}

public actor AchievementTranslationCache {
    private let connection: SQLiteConnection

    public static func defaultURL() -> URL? {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first?.appendingPathComponent("AchievementTranslation/cache-v1.sqlite")
    }

    public init(fileURL: URL) throws {
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(),
                                               withIntermediateDirectories: true)
        var handle: OpaquePointer?
        let result = sqlite3_open_v2(fileURL.path, &handle,
                                    SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil)
        guard result == SQLITE_OK, let db = handle else {
            if let handle { sqlite3_close_v2(handle) }
            throw AchievementTranslationError.cache("Cannot open translation cache (\(result))")
        }
        let owned = SQLiteConnection(db)
        sqlite3_busy_timeout(db, 2_000)
        let sql = """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS translations (
              achievement_id INTEGER NOT NULL, language TEXT NOT NULL,
              source_hash TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
              provenance TEXT NOT NULL CHECK(provenance IN ('official','machine')),
              PRIMARY KEY(achievement_id, language));
            """
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else {
            throw AchievementTranslationError.cache(String(cString: sqlite3_errmsg(db)))
        }
        connection = owned
    }

    private var db: OpaquePointer { connection.handle }
    private func error() -> AchievementTranslationError {
        .cache(String(cString: sqlite3_errmsg(db)))
    }

    private func prepare(_ sql: String) throws -> OpaquePointer {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK,
              let statement else { throw error() }
        return statement
    }

    private func bind(_ value: String, at index: Int32, in statement: OpaquePointer) throws {
        let bytes = Array(value.utf8) + [0]
        let status = bytes.withUnsafeBufferPointer { buffer in
            sqlite3_bind_text(statement, index,
                              UnsafeRawPointer(buffer.baseAddress!).assumingMemoryBound(to: CChar.self),
                              Int32(bytes.count - 1), unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        }
        guard status == SQLITE_OK else { throw error() }
    }

    private func string(_ statement: OpaquePointer, _ index: Int32) -> String {
        guard let bytes = sqlite3_column_text(statement, index) else { return "" }
        return String(decoding: UnsafeBufferPointer(start: bytes,
                      count: Int(sqlite3_column_bytes(statement, index))), as: UTF8.self)
    }

    public func fetch(language: String, ids: [Int]) throws -> [Int: CachedAchievementTranslation] {
        let statement = try prepare("SELECT source_hash,title,description,provenance FROM translations WHERE achievement_id=? AND language=?")
        defer { sqlite3_finalize(statement) }
        var rows: [Int: CachedAchievementTranslation] = [:]
        for id in Set(ids) {
            sqlite3_reset(statement)
            sqlite3_clear_bindings(statement)
            guard sqlite3_bind_int64(statement, 1, Int64(id)) == SQLITE_OK else { throw error() }
            try bind(language, at: 2, in: statement)
            let status = sqlite3_step(statement)
            if status == SQLITE_DONE { continue }
            guard status == SQLITE_ROW else { throw error() }
            // Corrupt/older rows cannot manufacture official or machine provenance.
            guard let provenance = TranslationProvenance(rawValue: string(statement, 3)),
                  provenance != .original else { continue }
            rows[id] = CachedAchievementTranslation(achievementID: id,
                sourceHash: string(statement, 0), title: string(statement, 1),
                description: string(statement, 2), provenance: provenance)
            guard sqlite3_step(statement) == SQLITE_DONE else { throw error() }
        }
        return rows
    }

    public func store(_ rows: [CachedAchievementTranslation], language: String) throws {
        guard rows.allSatisfy({ $0.provenance != .original }) else {
            throw AchievementTranslationError.invalidProvenance
        }
        guard !rows.isEmpty else { return }
        try execute("BEGIN IMMEDIATE")
        do {
            let statement = try prepare("INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?,?)")
            defer { sqlite3_finalize(statement) }
            for row in rows {
                sqlite3_reset(statement)
                sqlite3_clear_bindings(statement)
                guard sqlite3_bind_int64(statement, 1, Int64(row.achievementID)) == SQLITE_OK else { throw error() }
                for (offset, text) in [language, row.sourceHash, row.title, row.description, row.provenance.rawValue].enumerated() {
                    try bind(text, at: Int32(offset + 2), in: statement)
                }
                guard sqlite3_step(statement) == SQLITE_DONE else { throw error() }
            }
            try execute("COMMIT")
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    public func purge(language: String) throws {
        let statement = try prepare("DELETE FROM translations WHERE language=?")
        defer { sqlite3_finalize(statement) }
        try bind(language, at: 1, in: statement)
        guard sqlite3_step(statement) == SQLITE_DONE else { throw error() }
    }

    public func count(language: String) throws -> Int {
        let statement = try prepare("SELECT COUNT(*) FROM translations WHERE language=?")
        defer { sqlite3_finalize(statement) }
        try bind(language, at: 1, in: statement)
        guard sqlite3_step(statement) == SQLITE_ROW else { throw error() }
        let count = Int(sqlite3_column_int64(statement, 0))
        guard sqlite3_step(statement) == SQLITE_DONE else { throw error() }
        return count
    }

    private func execute(_ sql: String) throws {
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else { throw error() }
    }
}
