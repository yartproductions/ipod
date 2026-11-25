import Foundation
import CryptoKit
import AVFoundation

/// The app's own song library: every song file lives in Application Support/IPodMusic/<id>.<ext>.
/// The page sends each song in chunks; the store checks size and SHA-256 before keeping it, so a song is
/// only ever reported as stored when its bytes are exactly the ones the page sent.
final class IPodMusicStore {
    static let shared = IPodMusicStore()

    let musicDir: URL
    let artDir: URL
    private let io = DispatchQueue(label: "ipod.musicstore")

    private final class Upload {
        let temp: URL
        let handle: FileHandle
        var hasher = SHA256()
        var written = 0
        let expectSize: Int
        let expectSha: String
        let ext: String
        init(temp: URL, handle: FileHandle, expectSize: Int, expectSha: String, ext: String) {
            self.temp = temp; self.handle = handle; self.expectSize = expectSize; self.expectSha = expectSha; self.ext = ext
        }
    }
    private var uploads: [String: Upload] = [:]

    private init() {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        musicDir = base.appendingPathComponent("IPodMusic", isDirectory: true)
        artDir = base.appendingPathComponent("IPodArt", isDirectory: true)
        for dir in [musicDir, artDir] {
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        }
    }

    /// Ids only ever use letters, digits, - and _ in file names.
    static func safe(_ id: String) -> String {
        let allowed = Set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        let cleaned = String(id.filter { allowed.contains($0) })
        return cleaned.isEmpty ? "song" : String(cleaned.prefix(80))
    }

    static func safeExt(_ ext: String) -> String {
        let e = ext.lowercased().filter { $0.isLetter || $0.isNumber }
        return e.isEmpty ? "mp3" : String(e.prefix(5))
    }

    /// The stored file for a song id, if there is one.
    func fileURL(for id: String) -> URL? {
        let stem = Self.safe(id) + "."
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: musicDir.path) else { return nil }
        guard let name = names.first(where: { $0.hasPrefix(stem) && !$0.hasSuffix(".part") }) else { return nil }
        return musicDir.appendingPathComponent(name)
    }

    func artURL(for id: String) -> URL? {
        let url = artDir.appendingPathComponent(Self.safe(id) + ".jpg")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    /// { id: { size, art } } for every stored song.
    func inventory() -> [String: Any] {
        var out: [String: Any] = [:]
        let names = (try? FileManager.default.contentsOfDirectory(atPath: musicDir.path)) ?? []
        for name in names where !name.hasSuffix(".part") {
            let url = musicDir.appendingPathComponent(name)
            let id = (name as NSString).deletingPathExtension
            let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            out[id] = ["size": size, "art": artURL(for: id) != nil]
        }
        return out
    }

    // MARK: upload in chunks

    func begin(id: String, ext: String, size: Int, sha: String) throws {
        try io.sync {
            if let old = uploads.removeValue(forKey: id) { try? old.handle.close(); try? FileManager.default.removeItem(at: old.temp) }
            let temp = musicDir.appendingPathComponent(Self.safe(id) + ".part")
            FileManager.default.createFile(atPath: temp.path, contents: nil)
            let handle = try FileHandle(forWritingTo: temp)
            uploads[id] = Upload(temp: temp, handle: handle, expectSize: size, expectSha: sha.lowercased(), ext: Self.safeExt(ext))
        }
    }

    func chunk(id: String, base64: String) throws {
        guard let data = Data(base64Encoded: base64) else { throw StoreError.badChunk }
        try io.sync {
            guard let up = uploads[id] else { throw StoreError.noUpload }
            try up.handle.write(contentsOf: data)
            up.hasher.update(data: data)
            up.written += data.count
        }
    }

    /// Finishes an upload. Only moves the file into place when size and checksum match.
    func end(id: String) throws -> [String: Any] {
        try io.sync {
            guard let up = uploads.removeValue(forKey: id) else { throw StoreError.noUpload }
            try? up.handle.close()
            let sha = up.hasher.finalize().map { String(format: "%02x", $0) }.joined()
            guard up.written == up.expectSize, sha == up.expectSha else {
                try? FileManager.default.removeItem(at: up.temp)
                return ["ok": false, "reason": "checksum", "size": up.written, "sha": sha]
            }
            if let existing = fileURL(for: id) { try? FileManager.default.removeItem(at: existing) }
            let final = musicDir.appendingPathComponent(Self.safe(id) + "." + up.ext)
            try FileManager.default.moveItem(at: up.temp, to: final)
            return ["ok": true, "size": up.written, "sha": sha]
        }
    }

    /// Re-reads a stored file and checks it is a playable song of the expected size and checksum.
    func verify(id: String, size: Int, sha: String) async -> [String: Any] {
        guard let url = fileURL(for: id) else { return ["ok": false, "reason": "missing"] }
        guard let got = Self.sha256(of: url) else { return ["ok": false, "reason": "unreadable"] }
        let fileSize = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? -1
        guard fileSize == size, got == sha.lowercased() else { return ["ok": false, "reason": "checksum"] }
        let asset = AVURLAsset(url: url)
        do {
            let playable = try await asset.load(.isPlayable)
            let duration = try await asset.load(.duration)
            let seconds = CMTimeGetSeconds(duration)
            guard playable, seconds.isFinite, seconds > 0 else { return ["ok": false, "reason": "unplayable"] }
            return ["ok": true, "duration": seconds]
        } catch {
            return ["ok": false, "reason": "unplayable"]
        }
    }

    static func sha256(of url: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        var hasher = SHA256()
        while true {
            guard let data = try? handle.read(upToCount: 1 << 20) else { return nil }
            if data.isEmpty { break }
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    /// Part of a stored song, for page features that need the bytes (quiz, lyrics tags, export).
    func read(id: String, offset: Int, length: Int) -> String? {
        guard let url = fileURL(for: id), let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        do {
            try handle.seek(toOffset: UInt64(max(0, offset)))
            let data = try handle.read(upToCount: max(0, min(length, 4 << 20))) ?? Data()
            return data.base64EncodedString()
        } catch { return nil }
    }

    func saveArt(id: String, dataURL: String) -> Bool {
        guard let comma = dataURL.firstIndex(of: ","),
              let data = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])) else { return false }
        let url = artDir.appendingPathComponent(Self.safe(id) + ".jpg")
        return (try? data.write(to: url, options: .atomic)) != nil
    }

    func delete(id: String) {
        if let url = fileURL(for: id) { try? FileManager.default.removeItem(at: url) }
        if let art = artURL(for: id) { try? FileManager.default.removeItem(at: art) }
    }

    enum StoreError: Error { case badChunk, noUpload }
}
