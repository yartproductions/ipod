import Foundation
import AppIntents
import ActivityKit

/// Shared by the iPod app and its widget extension (CarPlay widget + Live Activity).
enum IPodShared {
    static let group = "group.com.yartproductions.ipod"
    static let nowPlayingKind = "IPodNowPlaying"
    static let carFlowKind = "IPodCarFlow"

    static var container: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group)
    }

    static func fileURL(_ name: String?) -> URL? {
        guard let name, !name.isEmpty, let dir = container else { return nil }
        return dir.appendingPathComponent(name)
    }
}

/// One album shown in Car Flow on the widget. `index` is its place in the iPod's album list.
struct IPodFlowAlbum: Codable, Hashable {
    var album: String
    var artist: String
    var art: String?
    var current: Bool
    var index: Int
}

/// What the iPod is playing, written by the app and read by the widget.
struct IPodNowPlaying: Codable, Equatable {
    var title: String = ""
    var artist: String = ""
    var album: String = ""
    var playing: Bool = false
    var duration: Double = 0
    var elapsed: Double = 0
    var updatedAt: Date = Date()
    var art: String? = nil
    var tone: String = "#3a78c9"
    var lyric: String = ""
    /// Degrees the record has turned; raised on every change so the widget animates a spin.
    var spin: Double = 0
    var flow: [IPodFlowAlbum] = []

    static func load() -> IPodNowPlaying? {
        guard let url = IPodShared.fileURL("nowplaying.json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(IPodNowPlaying.self, from: data)
    }

    func save() {
        guard let url = IPodShared.fileURL("nowplaying.json"),
              let data = try? JSONEncoder().encode(self) else { return }
        try? data.write(to: url, options: .atomic)
    }
}

/// The Live Activity: song, artist and the current lyric line (shown on the Lock Screen and in CarPlay).
struct IPodActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var title: String
        var artist: String
        var lyric: String
        var playing: Bool
        var tone: String
        var art: String?
    }
    var name: String = "iPod"
}

extension Notification.Name {
    /// Posted in the app when a widget or Live Activity button is tapped.
    static let ipodRemote = Notification.Name("IPodRemoteCommand")
}

/// Hands a widget tap to the running iPod page.
enum IPodRemote {
    static func send(_ command: String, _ argument: Int = 0) async {
        await MainActor.run {
            NotificationCenter.default.post(name: .ipodRemote, object: nil,
                                            userInfo: ["cmd": command, "arg": argument])
        }
    }
}

// Audio playback intents run inside the app (not the widget), so they reach the player directly.
struct IPodNextIntent: AudioPlaybackIntent {
    static let title: LocalizedStringResource = "Next Song"
    init() {}
    func perform() async throws -> some IntentResult {
        await IPodRemote.send("next")
        return .result()
    }
}

struct IPodPreviousIntent: AudioPlaybackIntent {
    static let title: LocalizedStringResource = "Previous Song"
    init() {}
    func perform() async throws -> some IntentResult {
        await IPodRemote.send("prev")
        return .result()
    }
}

struct IPodPlayPauseIntent: AudioPlaybackIntent {
    static let title: LocalizedStringResource = "Play or Pause"
    init() {}
    func perform() async throws -> some IntentResult {
        await IPodRemote.send("toggle")
        return .result()
    }
}

struct IPodPlayAlbumIntent: AudioPlaybackIntent {
    static let title: LocalizedStringResource = "Play Album"
    @Parameter(title: "Album") var index: Int
    init() {}
    init(index: Int) { self.index = index }
    func perform() async throws -> some IntentResult {
        await IPodRemote.send("album", index)
        return .result()
    }
}
