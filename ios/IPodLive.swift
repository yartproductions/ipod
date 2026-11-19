import Foundation
import ActivityKit
import WidgetKit

/// Takes what the page is playing and keeps the CarPlay widget and the Live Activity up to date.
@MainActor
final class IPodLive {
    static let shared = IPodLive()

    private var activity: Activity<IPodActivityAttributes>?
    private var current = IPodNowPlaying.load() ?? IPodNowPlaying()
    private var lastActivityState: IPodActivityAttributes.ContentState?

    /// `body` is the message the page posts to `ipodNowPlaying`.
    func update(from body: [String: Any]) {
        var next = current
        next.title = body["title"] as? String ?? ""
        next.artist = body["artist"] as? String ?? ""
        next.album = body["album"] as? String ?? ""
        next.playing = body["playing"] as? Bool ?? false
        next.duration = (body["duration"] as? NSNumber)?.doubleValue ?? 0
        next.elapsed = (body["elapsed"] as? NSNumber)?.doubleValue ?? 0
        next.tone = body["tone"] as? String ?? next.tone
        next.lyric = body["lyric"] as? String ?? ""
        next.updatedAt = Date()

        if let art = body["art"] as? String, let name = saveImage(dataURL: art, name: "art") {
            next.art = name
        } else if next.title.isEmpty {
            next.art = nil
        }
        if let flow = body["flow"] as? [[String: Any]] {
            next.flow = flow.enumerated().map { k, f in
                IPodFlowAlbum(album: f["album"] as? String ?? "",
                              artist: f["artist"] as? String ?? "",
                              art: saveImage(dataURL: f["art"] as? String ?? "", name: "flow\(k)"),
                              current: f["current"] as? Bool ?? false,
                              index: (f["index"] as? NSNumber)?.intValue ?? 0)
            }
        }

        let songChanged = next.title != current.title || next.artist != current.artist
        let playChanged = next.playing != current.playing
        let flowChanged = next.flow != current.flow
        if songChanged || playChanged { next.spin += songChanged ? 720 : 180 }
        let widgetChanged = songChanged || playChanged || flowChanged || next.art != current.art || next.tone != current.tone
        current = next
        current.save()
        if widgetChanged { WidgetCenter.shared.reloadAllTimelines() }

        let live = body["live"] as? Bool ?? true
        updateActivity(enabled: live && !current.title.isEmpty)
    }

    private func updateActivity(enabled: Bool) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        if activity == nil { activity = Activity<IPodActivityAttributes>.activities.first }
        guard enabled else {
            if let a = activity {
                activity = nil
                lastActivityState = nil
                Task { await a.end(nil, dismissalPolicy: .immediate) }
            }
            return
        }
        let state = IPodActivityAttributes.ContentState(title: current.title, artist: current.artist,
                                                        lyric: current.lyric, playing: current.playing,
                                                        tone: current.tone, art: current.art)
        guard state != lastActivityState else { return }
        lastActivityState = state
        let content = ActivityContent(state: state, staleDate: nil)
        if let a = activity {
            Task { await a.update(content) }
        } else {
            activity = try? Activity.request(attributes: IPodActivityAttributes(), content: content, pushType: nil)
        }
    }

    /// Writes a `data:image/jpeg;base64,…` URL into the shared folder and returns its file name.
    /// Each write gets a fresh name so the widget never shows a cached old picture.
    private func saveImage(dataURL: String, name: String) -> String? {
        guard let comma = dataURL.firstIndex(of: ","), dataURL.hasPrefix("data:image"),
              let data = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])),
              let dir = IPodShared.container else { return nil }
        let file = "\(name)-\(abs(data.hashValue) % 1_000_000).jpg"
        let url = dir.appendingPathComponent(file)
        if !FileManager.default.fileExists(atPath: url.path) {
            try? data.write(to: url, options: .atomic)
            // tidy up older copies of this image
            if let old = try? FileManager.default.contentsOfDirectory(atPath: dir.path) {
                for f in old where f.hasPrefix(name + "-") && f != file {
                    try? FileManager.default.removeItem(at: dir.appendingPathComponent(f))
                }
            }
        }
        return file
    }
}
