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
    let track: Int
    var local: Bool = true      // false = this song is still played by the web page (not moved into the app yet)
}

/// What the start and end of a song sound like, for gapless / smart crossfade.
struct IPodSongShape {
    var introSkip: Double = 0      // seconds of silence at the start
    var end: Double = 0            // where the sound really ends (trailing silence trimmed), seconds
    var outroStart: Double = 0     // where the song starts fading out by itself (0 = it doesn't)
}

/// The iPod's native audio engine (AVAudioEngine):
/// - two player decks feeding a mixer → 10-band EQ → output; the next song is loaded ahead of time so
///   songs change without a gap, and crossfades are volume ramps between the decks
/// - Smart crossfade: skips silence, starts the blend where a song fades out by itself, and keeps albums gapless
/// - the output is rewired when CarPlay / Bluetooth / headphones change the hardware format, so the speed never drifts
/// - keeps its own queue, so it carries on with the screen locked or in CarPlay; owns the Lock Screen controls
/// Everything runs on the main thread except the song analysis.
final class IPodPlayer: NSObject {
    static let shared = IPodPlayer()

    /// Called with the playing state about four times a second (and on every change), for the page.
    var onState: (([String: Any]) -> Void)?

    private(set) var queue: [IPodTrack] = []
    private(set) var index = 0
    var repeatMode = "Off"          // Off | One | All
    var crossfade: Double = 0       // seconds; 0 = gapless cut
    var smart = false               // Smart crossfade
    var stopAfterCurrent = false    // Sleep Timer "end of song"

    // MARK: engine

    private final class Deck {
        let node = AVAudioPlayerNode()
        var file: AVAudioFile?
        var trackIndex = -1
        var trackId = ""
        var startFrame: AVAudioFramePosition = 0
        var endFrame: AVAudioFramePosition = 0
        var token = 0
        var started = false          // node.play() has been called for this schedule
        var queued = false           // set to start on the audio clock right as the other deck ends (gapless)
        var heldPosition: Double = 0 // position while not rendering (paused / stopped)
        var sampleRate: Double { file?.processingFormat.sampleRate ?? 44100 }
        var duration: Double { file.map { Double($0.length) / $0.processingFormat.sampleRate } ?? 0 }
        var endTime: Double { Double(endFrame) / sampleRate }
        func position() -> Double {
            guard started, node.isPlaying, let nt = node.lastRenderTime, nt.isSampleTimeValid,
                  let pt = node.playerTime(forNodeTime: nt) else { return heldPosition }
            return min(duration, max(0, Double(startFrame + pt.sampleTime) / sampleRate))
        }
    }

    private let engine = AVAudioEngine()
    private let eq = AVAudioUnitEQ(numberOfBands: 10)
    private let decks = [Deck(), Deck()]
    private var active = 0
    private var other: Int { 1 - active }
    private var built = false
    private var wantsPlay = false
    private var ticker: Timer?
    private var fadeTimer: Timer?
    private var fade: (from: Int, to: Int, started: Date, length: Double)?
    private var shapes: [String: IPodSongShape] = [:]
    private let analysisQueue = DispatchQueue(label: "ipod.analysis", qos: .utility)
    private var remoteReady = false
    private var art: (id: String, artwork: MPMediaItemArtwork?)?
    private var widgetKey = ""

    static let eqFrequencies: [Float] = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

    private override init() {
        super.init()
        let nc = NotificationCenter.default
        nc.addObserver(self, selector: #selector(interrupted(_:)), name: AVAudioSession.interruptionNotification, object: nil)
        nc.addObserver(self, selector: #selector(routeChanged(_:)), name: AVAudioSession.routeChangeNotification, object: nil)
        nc.addObserver(self, selector: #selector(engineConfigChanged(_:)), name: .AVAudioEngineConfigurationChange, object: engine)
    }

    private func buildEngine() {
        guard !built else { return }
        built = true
        engine.attach(eq)
        for d in decks { engine.attach(d.node) }
        for (i, f) in Self.eqFrequencies.enumerated() {
            let band = eq.bands[i]
            band.filterType = i == 0 ? .lowShelf : (i == 9 ? .highShelf : .parametric)
            band.frequency = f
            band.bandwidth = 1.0
            band.gain = 0
            band.bypass = false
        }
        eq.bypass = true
        wireOutput()
    }

    /// mixer → EQ → speaker, in the hardware's current format (rewired when the output changes).
    private func wireOutput() {
        let mixer = engine.mainMixerNode
        let format = engine.outputNode.inputFormat(forBus: 0)
        engine.disconnectNodeOutput(mixer)
        engine.disconnectNodeOutput(eq)
        engine.connect(mixer, to: eq, format: format)
        engine.connect(eq, to: engine.outputNode, format: format)
    }

    private func ensureRunning() {
        buildEngine()
        activateSession()
        if !engine.isRunning {
            engine.prepare()
            try? engine.start()
        }
    }

    // MARK: - Settings from the page

    /// 10 gains in dB (−12…+12); nil or all zero = EQ off.
    func setEQ(_ gains: [Double]?) {
        buildEngine()
        let g = (gains ?? []).prefix(10).map { Float(max(-12, min(12, $0))) }
        let on = g.count == 10 && g.contains { abs($0) > 0.05 }
        for i in 0..<10 { eq.bands[i].gain = on ? g[i] : 0 }
        // headroom so boosts don't clip
        eq.globalGain = on ? -max(0, (g.max() ?? 0)) * 0.6 : 0
        eq.bypass = !on
    }

    // MARK: - Commands from the page

    var isPlaying: Bool { wantsPlay && decks[active].node.isPlaying }
    var elapsed: Double { decks[active].file == nil ? 0 : decks[active].position() }
    var duration: Double { decks[active].duration }
    var currentTrack: IPodTrack? { queue.indices.contains(index) ? queue[index] : nil }

    func load(_ tracks: [IPodTrack], index i: Int, at t: Double, play: Bool) {
        setupRemoteCommands()
        queue = tracks
        unloadDeck(decks[other])
        start(index: i, at: t, play: play)
    }

    /// Replace the queue without interrupting the current song (e.g. shuffle switched on mid-song).
    func requeue(_ tracks: [IPodTrack], index i: Int) {
        guard tracks.indices.contains(i), tracks[i].id == currentTrack?.id else {
            load(tracks, index: i, at: 0, play: wantsPlay); return
        }
        cancelFade()
        queue = tracks; index = i
        decks[active].trackIndex = i
        unloadDeck(decks[other])          // the preloaded "next" may have changed
        publish()
    }

    func jump(to i: Int, play: Bool) { start(index: i, at: 0, play: play) }

    func play() {
        guard decks[active].file != nil else { return }
        ensureRunning()
        wantsPlay = true
        let d = decks[active]
        d.node.play(); d.started = true
        if let f = fade { decks[f.from].node.play() }
        startTicker()
        updateNowPlaying(); publish()
    }

    func pause() {
        wantsPlay = false
        cancelFade()
        let d = decks[active]
        d.heldPosition = d.position()
        d.node.pause()
        let o = decks[other]
        if o.queued, let f = o.file { schedule(o, from: AVAudioFramePosition(o.heldPosition * f.processingFormat.sampleRate)) }
        updateNowPlaying(); publish()
    }

    func toggle() { isPlaying ? pause() : play() }

    func seek(to t: Double) {
        let d = decks[active]
        guard let f = d.file, t.isFinite else { return }
        cancelFade()
        unloadDeck(decks[other])
        let frame = AVAudioFramePosition(max(0, min(t, d.duration - 0.05)) * f.processingFormat.sampleRate)
        schedule(d, from: frame)
        if wantsPlay { ensureRunning(); d.node.play(); d.started = true }
        updateNowPlaying(); publish()
    }

    func next() {
        guard !queue.isEmpty else { return }
        start(index: index + 1 < queue.count ? index + 1 : 0, at: 0, play: true)
    }

    func previous() {
        guard !queue.isEmpty else { return }
        if elapsed > 3 { seek(to: 0); return }
        start(index: max(0, index - 1), at: 0, play: true)
    }

    func stop() {
        wantsPlay = false
        cancelFade()
        for d in decks { unloadDeck(d) }
        queue = []; index = 0
        ticker?.invalidate(); ticker = nil
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        publish()
    }

    func state() -> [String: Any] {
        ["id": currentTrack?.id ?? "", "index": index, "t": elapsed, "d": duration, "playing": isPlaying, "count": queue.count]
    }

    // MARK: - Loading and scheduling

    private func unloadDeck(_ d: Deck) {
        d.token += 1
        d.node.stop()
        d.node.volume = 1
        d.file = nil; d.trackIndex = -1; d.trackId = ""; d.started = false; d.queued = false; d.heldPosition = 0
    }

    /// Opens a song onto a deck and schedules it (not playing yet). Returns false if the file is missing or unreadable.
    @discardableResult
    private func prepare(_ d: Deck, index i: Int, at seconds: Double) -> Bool {
        guard queue.indices.contains(i), let url = IPodMusicStore.shared.fileURL(for: queue[i].id),
              let f = try? AVAudioFile(forReading: url) else { return false }
        buildEngine()
        d.token += 1
        d.node.stop()
        engine.disconnectNodeOutput(d.node)
        engine.connect(d.node, to: engine.mainMixerNode, format: f.processingFormat)
        d.file = f; d.trackIndex = i; d.trackId = queue[i].id
        d.node.volume = 1
        var from = seconds
        if from <= 0, smart, let s = shapes[queue[i].id] { from = s.introSkip }
        schedule(d, from: AVAudioFramePosition(from * f.processingFormat.sampleRate))
        return true
    }

    private func schedule(_ d: Deck, from: AVAudioFramePosition) {
        guard let f = d.file else { return }
        d.token += 1
        let token = d.token
        d.node.stop()
        d.started = false; d.queued = false
        var end = f.length
        if smart, let s = shapes[d.trackId], s.end > 0 {
            end = min(f.length, AVAudioFramePosition(s.end * f.processingFormat.sampleRate))
        }
        let start = max(0, min(from, end - 1))
        d.startFrame = start; d.endFrame = end
        d.heldPosition = Double(start) / f.processingFormat.sampleRate
        let count = AVAudioFrameCount(max(1, end - start))
        // .dataRendered fires as the last audio leaves the deck, so the next song can start right behind it
        d.node.scheduleSegment(f, startingFrame: start, frameCount: count, at: nil, completionCallbackType: .dataRendered) { [weak self, weak d] _ in
            DispatchQueue.main.async {
                guard let self, let d, d.token == token else { return }
                self.deckFinished(d)
            }
        }
    }

    private func start(index i: Int, at t: Double, play: Bool) {
        cancelFade()
        guard queue.indices.contains(i) else { publish(); return }
        guard queue[i].local else { handOff(i, play: play); return }
        if decks[other].trackIndex == i, decks[other].file != nil, t <= 0 {
            // reuse the preloaded deck: it already holds this song
            unloadDeck(decks[active]); active = other
        } else {
            unloadDeck(decks[other])
            var j = i
            while !prepare(decks[active], index: j, at: t) {
                // the file is missing: skip it rather than stopping the music
                publish(extra: ["error": "missing", "missingId": queue[j].id])
                guard play, j + 1 < queue.count else { index = j; unloadDeck(decks[active]); publish(); return }
                j += 1
            }
        }
        index = decks[active].trackIndex
        analyzeAhead()
        wantsPlay = play
        if play { ensureRunning(); decks[active].node.play(); decks[active].started = true }
        startTicker()
        updateNowPlaying(); publish()
    }

    /// The next song isn't in the app yet: stop here and let the page's own player take over from that song.
    private func handOff(_ i: Int, play: Bool) {
        wantsPlay = false
        for d in decks { unloadDeck(d) }
        index = i
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        var s = state()
        s["handoff"] = i; s["play"] = play
        onState?(s)
    }

    private func upcomingIndex() -> Int? {
        if index + 1 < queue.count { return index + 1 }
        return repeatMode == "All" && !queue.isEmpty ? 0 : nil
    }

    /// A deck reached the end of its song.
    private func deckFinished(_ d: Deck) {
        guard d === decks[active], fade == nil else { return }   // a faded-out deck finishing: nothing to do
        let up = upcomingIndex()
        let continues = !stopAfterCurrent && repeatMode != "One" && up != nil && decks[other].trackIndex == up
        if decks[other].queued, !continues { unloadDeck(decks[other]) }   // plans changed since it was queued
        if stopAfterCurrent {
            stopAfterCurrent = false; wantsPlay = false
            d.heldPosition = d.endTime
            updateNowPlaying(); publish(extra: ["sleep": true]); return
        }
        if repeatMode == "One" { seek(to: smart ? (shapes[d.trackId]?.introSkip ?? 0) : 0); return }
        guard let n = up else {
            wantsPlay = false; d.heldPosition = d.endTime
            updateNowPlaying(); publish(extra: ["ended": true]); return
        }
        guard queue[n].local else { handOff(n, play: wantsPlay); return }
        let o = decks[other]
        if o.trackIndex == n, o.file != nil, wantsPlay {
            // gapless: the next song is already loaded (and usually already running on the audio clock)
            if !o.queued { ensureRunning(); o.node.play() }
            o.started = true; o.queued = false
            unloadDeck(d)
            active = other; index = n
            analyzeAhead()
            updateNowPlaying(); publish()
        } else {
            start(index: n, at: 0, play: wantsPlay)
        }
    }

    // MARK: - Every quarter second: preload, crossfade, report

    private func startTicker() {
        guard ticker == nil else { return }
        ticker = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.tick() }
    }

    private func tick() {
        let d = decks[active]
        guard d.file != nil else { return }
        if isPlaying, fade == nil, let n = upcomingIndex(), queue[n].local, repeatMode != "One", !stopAfterCurrent {
            let remaining = d.endTime - d.position()
            // load the next song well ahead so the change is instant
            if remaining < 12, decks[other].trackIndex != n {
                prepare(decks[other], index: n, at: 0)
            }
            let len = fadeLength(from: index, to: n)
            if len == 0, remaining < 1.5 { queueGapless(after: d) }
            if len > 0, remaining > 0.2, remaining <= len, decks[other].trackIndex == n, decks[other].file != nil {
                beginFade(length: remaining)
            }
        }
        publish()
    }

    /// Start the preloaded deck on the audio clock at the exact sample the current song ends — no gap, no overlap.
    private func queueGapless(after d: Deck) {
        let o = decks[other]
        guard !o.queued, o.file != nil, o.trackIndex == upcomingIndex(), engine.isRunning,
              let nt = d.node.lastRenderTime, nt.isSampleTimeValid, let pt = d.node.playerTime(forNodeTime: nt) else { return }
        let left = Double(d.endFrame - (d.startFrame + pt.sampleTime)) / d.sampleRate
        guard left > 0.05 else { return }
        let when = AVAudioTime(sampleTime: nt.sampleTime + AVAudioFramePosition(left * nt.sampleRate), atRate: nt.sampleRate)
        o.node.play(at: when)
        o.queued = true
    }

    /// How long to blend song `a` into song `b` (0 = gapless).
    private func fadeLength(from a: Int, to b: Int) -> Double {
        guard queue.indices.contains(a), queue.indices.contains(b) else { return 0 }
        if smart {
            let x = queue[a], y = queue[b]
            // albums play straight through, like the record
            if !x.album.isEmpty, x.album == y.album, x.track > 0, y.track == x.track + 1 { return 0 }
            if let s = shapes[x.id], s.outroStart > 0, s.end > s.outroStart {
                return max(2, min(10, s.end - s.outroStart))     // start where it already fades out
            }
            return 5
        }
        return crossfade
    }

    private func beginFade(length: Double) {
        let from = active, to = other
        let inc = decks[to]
        inc.node.volume = 0
        ensureRunning()
        inc.node.play(); inc.started = true
        fade = (from, to, Date(), max(0.3, length))
        fadeTimer?.invalidate()
        fadeTimer = Timer.scheduledTimer(withTimeInterval: 0.03, repeats: true) { [weak self] _ in self?.fadeStep() }
        // the new song counts as the current one from the start of the blend (Lock Screen, page)
        active = to; index = inc.trackIndex
        analyzeAhead()
        updateNowPlaying(); publish()
    }

    private func fadeStep() {
        guard let f = fade else { fadeTimer?.invalidate(); fadeTimer = nil; return }
        let k = min(1, Date().timeIntervalSince(f.started) / f.length)
        // equal-power curve so the loudness stays even through the blend
        decks[f.from].node.volume = Float(cos(k * .pi / 2))
        decks[f.to].node.volume = Float(sin(k * .pi / 2))
        if k >= 1 {
            fadeTimer?.invalidate(); fadeTimer = nil
            fade = nil
            unloadDeck(decks[f.from])
            decks[f.to].node.volume = 1
        }
    }

    private func cancelFade() {
        fadeTimer?.invalidate(); fadeTimer = nil
        guard let f = fade else { return }
        fade = nil
        unloadDeck(decks[f.from])
        decks[f.to].node.volume = 1
    }

    // MARK: - Song shape analysis (silence, built-in fade-outs) for Smart crossfade

    /// Analyse the current and next songs in the background.
    private func analyzeAhead() {
        guard smart else { return }
        var ids: [String] = []
        if let c = currentTrack { ids.append(c.id) }
        if let n = upcomingIndex() { ids.append(queue[n].id) }
        for id in ids where shapes[id] == nil {
            guard let url = IPodMusicStore.shared.fileURL(for: id) else { continue }
            analysisQueue.async { [weak self] in
                let s = IPodPlayer.analyze(url: url)
                DispatchQueue.main.async { self?.shapes[id] = s }
            }
        }
    }

    /// Reads the first 12 s and last 30 s of a song: leading silence, where the sound ends, and where it starts fading.
    static func analyze(url: URL) -> IPodSongShape {
        var shape = IPodSongShape()
        guard let file = try? AVAudioFile(forReading: url) else { return shape }
        let sr = file.processingFormat.sampleRate
        let total = file.length
        shape.end = Double(total) / sr
        let window = AVAudioFrameCount(max(1, sr * 0.1))          // 100 ms
        let silence: Float = 0.004                                 // about −48 dBFS
        func rmsWindows(from: AVAudioFramePosition, frames: AVAudioFramePosition) -> [Float] {
            guard frames > 0, let buf = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: window) else { return [] }
            var out: [Float] = []
            file.framePosition = from
            var left = frames
            while left > 0 {
                buf.frameLength = 0
                let want = AVAudioFrameCount(min(AVAudioFramePosition(window), left))
                guard (try? file.read(into: buf, frameCount: want)) != nil, buf.frameLength > 0,
                      let ch = buf.floatChannelData else { break }
                let n = Int(buf.frameLength), channels = Int(buf.format.channelCount)
                var sum: Float = 0
                for c in 0..<channels { let p = ch[c]; for k in 0..<n { sum += p[k] * p[k] } }
                out.append(sqrt(sum / Float(max(1, n * channels))))
                left -= AVAudioFramePosition(buf.frameLength)
            }
            return out
        }
        // leading silence
        let head = rmsWindows(from: 0, frames: min(total, AVAudioFramePosition(sr * 12)))
        if let first = head.firstIndex(where: { $0 > silence }) { shape.introSkip = max(0, Double(first) * 0.1 - 0.05) }
        // the ending
        let tailFrames = min(total, AVAudioFramePosition(sr * 30))
        let tailStart = total - tailFrames
        let tail = rmsWindows(from: tailStart, frames: tailFrames)
        guard !tail.isEmpty else { return shape }
        let t0 = Double(tailStart) / sr
        if let lastSound = tail.lastIndex(where: { $0 > silence }) {
            shape.end = min(Double(total) / sr, t0 + Double(lastSound + 1) * 0.1 + 0.05)
            // the song's normal loudness near the end, then where it drops below half of it for good
            let body = Array(tail[0...lastSound]).sorted()
            let ref = body[Int(Double(body.count - 1) * 0.75)]
            if ref > silence * 4, let lastLoud = tail[0...lastSound].lastIndex(where: { $0 >= ref * 0.5 }) {
                let fadeStart = t0 + Double(lastLoud + 1) * 0.1
                if shape.end - fadeStart >= 1.5 { shape.outroStart = fadeStart }
            }
        }
        return shape
    }

    // MARK: - Audio session, interruptions, unplugging, output changes

    private func activateSession() {
        let s = AVAudioSession.sharedInstance()
        try? s.setCategory(.playback, mode: .default)
        try? s.setActive(true)
    }

    @objc private func interrupted(_ note: Notification) {
        guard let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        let opts = (note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt).map(AVAudioSession.InterruptionOptions.init(rawValue:)) ?? []
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            if type == .began {
                let d = self.decks[self.active]; d.heldPosition = d.position()
                self.cancelFade(); self.publish(); return
            }
            if opts.contains(.shouldResume), self.wantsPlay { self.resumeAfterRestart() } else { self.updateNowPlaying(); self.publish() }
        }
    }

    @objc private func routeChanged(_ note: Notification) {
        guard let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
              AVAudioSession.RouteChangeReason(rawValue: raw) == .oldDeviceUnavailable else { return }
        // headphones unplugged / Bluetooth gone: pause, like an iPod
        DispatchQueue.main.async { [weak self] in self?.pause() }
    }

    /// CarPlay, Bluetooth or headphones changed the hardware format and the engine stopped itself.
    /// Rewire for the new format and carry on from the same spot (this is what keeps the speed right).
    @objc private func engineConfigChanged(_ note: Notification) {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.built else { return }
            let d = self.decks[self.active]
            d.heldPosition = d.position()
            self.cancelFade()
            self.wireOutput()
            if self.wantsPlay { self.resumeAfterRestart() } else {
                if d.file != nil { self.schedule(d, from: AVAudioFramePosition(d.heldPosition * d.sampleRate)) }
                self.publish()
            }
        }
    }

    private func resumeAfterRestart() {
        let d = decks[active]
        guard d.file != nil else { return }
        let at = d.position()
        unloadDeck(decks[other])
        schedule(d, from: AVAudioFramePosition(at * d.sampleRate))
        ensureRunning()
        d.node.play(); d.started = true
        updateNowPlaying(); publish()
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
        guard let t = currentTrack, decks[active].file != nil else { MPNowPlayingInfoCenter.default().nowPlayingInfo = nil; return }
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: t.title,
            MPMediaItemPropertyArtist: t.artist,
            MPMediaItemPropertyAlbumTitle: t.album,
            MPMediaItemPropertyPlaybackDuration: duration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: elapsed,
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? 1.0 : 0.0,
            MPNowPlayingInfoPropertyDefaultPlaybackRate: 1.0,
            MPNowPlayingInfoPropertyPlaybackQueueIndex: index,
            MPNowPlayingInfoPropertyPlaybackQueueCount: queue.count,
            MPNowPlayingInfoPropertyMediaType: MPNowPlayingInfoMediaType.audio.rawValue
        ]
        if let a = artwork(for: t.id) { info[MPMediaItemPropertyArtwork] = a }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    /// Tell the CarPlay widget / Live Activity when the song or play state changes.
    private func refreshWidget() {
        guard let t = currentTrack else { return }
        let key = "\(t.id)|\(isPlaying)"
        guard key != widgetKey else { return }
        widgetKey = key
        let playing = isPlaying, artFile = IPodMusicStore.shared.artURL(for: t.id)
        Task { @MainActor in
            IPodLive.shared.nativeChanged(title: t.title, artist: t.artist, album: t.album, playing: playing, artFile: artFile)
        }
    }

    private func publish(extra: [String: Any] = [:]) {
        refreshWidget()
        var s = state()
        for (k, v) in extra { s[k] = v }
        onState?(s)
    }
}
