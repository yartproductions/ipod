import Foundation
import AVFoundation
import MediaPlayer
import UIKit

/// One song in the native queue (the page sends the queue in play order, already shuffled if shuffle is on).
struct IPodTrack: Equatable {
    let id: String
    let title: String
    let artist: String
    let album: String
}

/// The iPod's native audio engine. Plays the songs stored by IPodMusicStore with AVPlayer, keeps the
/// queue itself so it carries on with the screen locked or in CarPlay, crossfades with two players,
/// always at exactly 1× speed, and owns the Lock Screen / CarPlay / headphone controls.
/// Everything runs on the main thread.
final class IPodPlayer: NSObject {
    static let shared = IPodPlayer()

    /// Called with the playing state about four times a second (and on every change), for the page.
    var onState: (([String: Any]) -> Void)?

    private(set) var queue: [IPodTrack] = []
    private(set) var index = 0
    var repeatMode = "Off"          // Off | One | All
    var crossfade: Double = 0       // seconds; 0 = straight cut (gapless-style)
    var stopAfterCurrent = false    // Sleep Timer "end of song"

    private var current: AVPlayer?
    private var incoming: AVPlayer?
    private var incomingIndex = -1
    private var timeObserver: Any?
    private var observedPlayer: AVPlayer?
    private var endObserver: NSObjectProtocol?
    private var fadeTimer: Timer?
    private var fadeStarted = Date()
    private var fadeLength: Double = 0
    private var wantsPlay = false
    private var remoteReady = false
    private var art: (id: String, artwork: MPMediaItemArtwork?)?
    private var lastInfoDuration: Double = 0

    private override init() {
        super.init()
        let nc = NotificationCenter.default
        nc.addObserver(self, selector: #selector(interrupted(_:)), name: AVAudioSession.interruptionNotification, object: nil)
        nc.addObserver(self, selector: #selector(routeChanged(_:)), name: AVAudioSession.routeChangeNotification, object: nil)
    }

    var isPlaying: Bool { (current?.rate ?? 0) > 0 }
    var elapsed: Double { let t = current.map { CMTimeGetSeconds($0.currentTime()) } ?? 0; return t.isFinite ? max(0, t) : 0 }
    var duration: Double {
        guard let d = current?.currentItem?.duration else { return 0 }
        let s = CMTimeGetSeconds(d); return s.isFinite ? s : 0
    }
    var currentTrack: IPodTrack? { queue.indices.contains(index) ? queue[index] : nil }

    // MARK: - Commands from the page

    /// Replace the queue and start at `index`.
    func load(_ tracks: [IPodTrack], index i: Int, at t: Double, play: Bool) {
        setupRemoteCommands()
        queue = tracks
        start(index: i, at: t, play: play)
    }

    /// Replace the queue without interrupting the current song (e.g. shuffle switched on mid-song).
    func requeue(_ tracks: [IPodTrack], index i: Int) {
        guard tracks.indices.contains(i), tracks[i].id == currentTrack?.id else {
            load(tracks, index: i, at: 0, play: wantsPlay); return
        }
        cancelFade()
        queue = tracks; index = i
        publish()
    }

    func jump(to i: Int, play: Bool) { start(index: i, at: 0, play: play) }

    func play() {
        guard let p = current else { return }
        activateSession()
        wantsPlay = true
        p.playImmediately(atRate: 1)
        incoming?.playImmediately(atRate: 1)
        updateNowPlaying(); publish()
    }

    func pause() {
        wantsPlay = false
        cancelFade()
        current?.pause()
        updateNowPlaying(); publish()
    }

    func toggle() { isPlaying ? pause() : play() }

    func seek(to t: Double) {
        guard let p = current, t.isFinite else { return }
        cancelFade()
        p.seek(to: CMTime(seconds: max(0, t), preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
            self?.updateNowPlaying(); self?.publish()
        }
    }

    /// Next / previous from the Lock Screen, CarPlay or headphones (the page sends its own jumps).
    func next() {
        guard !queue.isEmpty else { return }
        let n = index + 1 < queue.count ? index + 1 : 0
        start(index: n, at: 0, play: true)
    }

    func previous() {
        guard !queue.isEmpty else { return }
        if elapsed > 3 { seek(to: 0); return }
        start(index: max(0, index - 1), at: 0, play: true)
    }

    func stop() {
        wantsPlay = false
        cancelFade()
        teardown(current); current = nil
        queue = []; index = 0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        publish()
    }

    func state() -> [String: Any] {
        ["id": currentTrack?.id ?? "", "index": index, "t": elapsed, "d": duration, "playing": isPlaying, "count": queue.count]
    }

    // MARK: - Playing a song

    private func makePlayer(for t: IPodTrack) -> AVPlayer? {
        guard let url = IPodMusicStore.shared.fileURL(for: t.id) else { return nil }
        let item = AVPlayerItem(url: url)
        item.audioTimePitchAlgorithm = .timeDomain
        let p = AVPlayer(playerItem: item)
        p.automaticallyWaitsToMinimizeStalling = false
        p.actionAtItemEnd = .pause
        return p
    }

    private func start(index i: Int, at t: Double, play: Bool) {
        cancelFade()
        teardown(current); current = nil
        guard queue.indices.contains(i) else { publish(); return }
        index = i
        guard let p = makePlayer(for: queue[i]) else {
            // The file is missing: skip it rather than stopping the music.
            publish(extra: ["error": "missing", "missingId": queue[i].id])
            if play, queue.count > 1, i + 1 < queue.count { start(index: i + 1, at: 0, play: true) }
            return
        }
        current = p
        attach(p)
        if t > 0 { p.seek(to: CMTime(seconds: t, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero) }
        wantsPlay = play
        if play { activateSession(); p.playImmediately(atRate: 1) }
        lastInfoDuration = 0
        updateNowPlaying(); publish()
    }

    private func attach(_ p: AVPlayer) {
        detachObservers()
        observedPlayer = p
        timeObserver = p.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 4), queue: .main) { [weak self] _ in
            self?.tick()
        }
        endObserver = NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: p.currentItem, queue: .main) { [weak self] _ in
            self?.trackEnded()
        }
    }

    private func detachObservers() {
        if let o = timeObserver, let p = observedPlayer { p.removeTimeObserver(o) }
        timeObserver = nil; observedPlayer = nil
        if let e = endObserver { NotificationCenter.default.removeObserver(e) }
        endObserver = nil
    }

    private func teardown(_ p: AVPlayer?) {
        guard let p else { return }
        if p === observedPlayer { detachObservers() }
        p.pause()
        p.replaceCurrentItem(with: nil)
    }

    private func tick() {
        // keep speed locked at 1× while playing
        if wantsPlay, let p = current, p.rate > 0, abs(p.rate - 1) > 0.001 { p.rate = 1 }
        let d = duration
        if d > 0, abs(d - lastInfoDuration) > 0.5 { lastInfoDuration = d; updateNowPlaying() }
        if crossfade > 0, incoming == nil, isPlaying, !stopAfterCurrent, repeatMode != "One", d > 0 {
            let remaining = d - elapsed
            if remaining > 0.3, remaining <= min(crossfade, d / 2) { beginFade(length: remaining) }
        }
        publish()
    }

    private func upcomingIndex() -> Int? {
        if index + 1 < queue.count { return index + 1 }
        return repeatMode == "All" && !queue.isEmpty ? 0 : nil
    }

    private func trackEnded() {
        if incoming != nil { return }   // a crossfade already took over
        if stopAfterCurrent {
            stopAfterCurrent = false; wantsPlay = false
            updateNowPlaying(); publish(extra: ["sleep": true]); return
        }
        if repeatMode == "One" { seek(to: 0); current?.playImmediately(atRate: 1); return }
        if let n = upcomingIndex() { start(index: n, at: 0, play: true) }
        else { wantsPlay = false; updateNowPlaying(); publish(extra: ["ended": true]) }
    }

    // MARK: - Crossfade (two players, volume ramps; AVPlayer volume is the player's own, not the system's)

    private func beginFade(length: Double) {
        guard let n = upcomingIndex(), n != index, let p = makePlayer(for: queue[n]) else { return }
        incoming = p; incomingIndex = n
        fadeLength = max(0.3, length); fadeStarted = Date()
        p.volume = 0
        p.playImmediately(atRate: 1)
        fadeTimer?.invalidate()
        fadeTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in self?.fadeStep() }
    }

    private func fadeStep() {
        guard let out = current, let inc = incoming else { cancelFade(); return }
        let k = min(1, Date().timeIntervalSince(fadeStarted) / fadeLength)
        // equal-power curve so the loudness stays even through the fade
        out.volume = Float(cos(k * .pi / 2))
        inc.volume = Float(sin(k * .pi / 2))
        if k >= 1 { finishFade() }
    }

    private func finishFade() {
        fadeTimer?.invalidate(); fadeTimer = nil
        guard let inc = incoming else { return }
        let old = current
        detachObservers()
        teardown(old)
        current = inc; incoming = nil
        index = incomingIndex; incomingIndex = -1
        inc.volume = 1
        attach(inc)
        lastInfoDuration = 0
        updateNowPlaying(); publish()
    }

    private func cancelFade() {
        fadeTimer?.invalidate(); fadeTimer = nil
        if let inc = incoming { inc.pause(); inc.replaceCurrentItem(with: nil) }
        incoming = nil; incomingIndex = -1
        current?.volume = 1
    }

    // MARK: - Audio session, interruptions, unplugging

    private func activateSession() {
        let s = AVAudioSession.sharedInstance()
        try? s.setCategory(.playback, mode: .default)
        try? s.setActive(true)
    }

    @objc private func interrupted(_ note: Notification) {
        guard let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            if type == .began { self.cancelFade(); self.publish(); return }
            let opts = (note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt).map(AVAudioSession.InterruptionOptions.init(rawValue:)) ?? []
            if opts.contains(.shouldResume), self.wantsPlay { self.play() } else { self.updateNowPlaying(); self.publish() }
        }
    }

    @objc private func routeChanged(_ note: Notification) {
        guard let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
              AVAudioSession.RouteChangeReason(rawValue: raw) == .oldDeviceUnavailable else { return }
        // headphones unplugged / Bluetooth gone: pause, like an iPod
        DispatchQueue.main.async { [weak self] in self?.pause() }
    }

    // MARK: - Lock Screen, Control Center, CarPlay, headphones

    private func setupRemoteCommands() {
        guard !remoteReady else { return }
        remoteReady = true
        let c = MPRemoteCommandCenter.shared()
        c.playCommand.addTarget { [weak self] _ in self?.play(); return .success }
        c.pauseCommand.addTarget { [weak self] _ in self?.pause(); return .success }
        c.togglePlayPauseCommand.addTarget { [weak self] _ in self?.toggle(); return .success }
        c.nextTrackCommand.addTarget { [weak self] _ in self?.next(); return .success }
        c.previousTrackCommand.addTarget { [weak self] _ in self?.previous(); return .success }
        c.changePlaybackPositionCommand.addTarget { [weak self] e in
            guard let e = e as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            self?.seek(to: e.positionTime); return .success
        }
        c.skipForwardCommand.isEnabled = false
        c.skipBackwardCommand.isEnabled = false
        c.changePlaybackRateCommand.isEnabled = false
    }

    private func artwork(for id: String) -> MPMediaItemArtwork? {
        if let a = art, a.id == id { return a.artwork }
        var artwork: MPMediaItemArtwork?
        if let url = IPodMusicStore.shared.artURL(for: id), let image = UIImage(contentsOfFile: url.path) {
            artwork = MPMediaItemArtwork(boundsSize: image.size) { _ in image }
        }
        art = (id, artwork)
        return artwork
    }

    /// The artwork for a song changed (the page found or saved a new cover).
    func artworkChanged(for id: String) {
        if art?.id == id { art = nil }
        if currentTrack?.id == id { updateNowPlaying() }
    }

    private func updateNowPlaying() {
        guard let t = currentTrack, current != nil else { MPNowPlayingInfoCenter.default().nowPlayingInfo = nil; return }
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: t.title,
            MPMediaItemPropertyArtist: t.artist,
            MPMediaItemPropertyAlbumTitle: t.album,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: elapsed,
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? 1.0 : 0.0,
            MPNowPlayingInfoPropertyDefaultPlaybackRate: 1.0,
            MPNowPlayingInfoPropertyPlaybackQueueIndex: index,
            MPNowPlayingInfoPropertyPlaybackQueueCount: queue.count,
            MPNowPlayingInfoPropertyMediaType: MPNowPlayingInfoMediaType.audio.rawValue
        ]
        if duration > 0 { info[MPMediaItemPropertyPlaybackDuration] = duration }
        if let a = artwork(for: t.id) { info[MPMediaItemPropertyArtwork] = a }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private var widgetKey = ""
    /// Tell the CarPlay widget / Live Activity when the song or play state changes.
    private func refreshWidget() {
        guard let t = currentTrack else { return }
        let key = "\(t.id)|\(isPlaying)"
        guard key != widgetKey else { return }
        widgetKey = key
        let playing = isPlaying, art = IPodMusicStore.shared.artURL(for: t.id)
        Task { @MainActor in
            IPodLive.shared.nativeChanged(title: t.title, artist: t.artist, album: t.album, playing: playing, artFile: art)
        }
    }

    private func publish(extra: [String: Any] = [:]) {
        refreshWidget()
        var s = state()
        for (k, v) in extra { s[k] = v }
        onState?(s)
    }
}
