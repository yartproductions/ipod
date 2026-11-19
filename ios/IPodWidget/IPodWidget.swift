import WidgetKit
import SwiftUI
import AppIntents
import ActivityKit

// MARK: - Timeline

struct IPodEntry: TimelineEntry {
    let date: Date
    let np: IPodNowPlaying?
}

struct IPodProvider: TimelineProvider {
    func placeholder(in context: Context) -> IPodEntry { IPodEntry(date: Date(), np: nil) }

    func getSnapshot(in context: Context, completion: @escaping (IPodEntry) -> Void) {
        completion(IPodEntry(date: Date(), np: IPodNowPlaying.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<IPodEntry>) -> Void) {
        let now = Date()
        let np = IPodNowPlaying.load()
        var entries = [IPodEntry(date: now, np: np)]
        // While music plays, give the record another turn every few minutes so it looks alive.
        if var n = np, n.playing {
            for i in 1...6 {
                n.spin += 360
                entries.append(IPodEntry(date: now.addingTimeInterval(Double(i) * 300), np: n))
            }
        }
        completion(Timeline(entries: entries, policy: .atEnd))
    }
}

// MARK: - Helpers

extension Color {
    init(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("#") { s.removeFirst() }
        let v = UInt64(s, radix: 16) ?? 0x3a78c9
        self.init(red: Double((v >> 16) & 0xff) / 255, green: Double((v >> 8) & 0xff) / 255, blue: Double(v & 0xff) / 255)
    }
}

func ipodImage(_ name: String?) -> Image? {
    guard let url = IPodShared.fileURL(name), let ui = UIImage(contentsOfFile: url.path) else { return nil }
    return Image(uiImage: ui)
}

struct CoverView: View {
    let name: String?
    var corner: CGFloat = 6
    var body: some View {
        Group {
            if let img = ipodImage(name) {
                img.resizable().aspectRatio(contentMode: .fill)
            } else {
                LinearGradient(colors: [Color(hex: "#3a78c9"), Color(hex: "#8db8ea")], startPoint: .topLeading, endPoint: .bottomTrailing)
                    .overlay(Image(systemName: "music.note").font(.title2).foregroundStyle(.white.opacity(0.8)))
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: corner, style: .continuous))
    }
}

/// The colored record, tinted from the cover. `spin` grows with every update so WidgetKit animates a turn.
struct RecordView: View {
    let tone: Color
    let spin: Double
    var body: some View {
        ZStack {
            Circle().fill(AngularGradient(colors: [tone.opacity(0.45), .white, tone.opacity(0.3), Color(white: 0.95), tone.opacity(0.5), .white, tone.opacity(0.45)], center: .center))
            ForEach(1..<7) { i in
                Circle().stroke(Color.black.opacity(0.05), lineWidth: 0.5).padding(CGFloat(i) * 4)
            }
            Circle().fill(tone).scaleEffect(0.36)
            Circle().fill(Color(white: 0.92)).scaleEffect(0.05)
        }
        .rotationEffect(.degrees(spin))
        .animation(.easeOut(duration: 2), value: spin)
        .shadow(color: .black.opacity(0.25), radius: 4, y: 2)
    }
}

/// Invisible full-height tap zone.
struct TapZone<I: AppIntent>: View {
    let intent: I
    var body: some View {
        Button(intent: intent) {
            Rectangle().fill(Color.white.opacity(0.001)).frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Now Playing widget: cover + spinning record; tap left = previous, right = next, middle = play/pause

struct NowPlayingView: View {
    let entry: IPodEntry
    @Environment(\.widgetFamily) var family

    var body: some View {
        let np = entry.np
        let tone = Color(hex: np?.tone ?? "#3a78c9")
        GeometryReader { geo in
            let side = min(geo.size.height * (family == .systemSmall ? 0.62 : 0.78), geo.size.width * 0.5)
            ZStack(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 4) {
                    ZStack(alignment: .leading) {
                        RecordView(tone: tone, spin: np?.spin ?? 0)
                            .frame(width: side * 0.94, height: side * 0.94)
                            .offset(x: (np?.playing ?? false) ? side * 0.5 : side * 0.3)
                            .animation(.spring(duration: 0.8), value: np?.playing ?? false)
                        CoverView(name: np?.art)
                            .frame(width: side, height: side)
                            .shadow(color: .black.opacity(0.3), radius: 5, y: 3)
                            .id(np?.art ?? "none")
                            .transition(.push(from: .trailing))
                    }
                    .frame(height: side)
                    if family == .systemSmall {
                        Text(np?.title ?? "iPod").font(.system(size: 13, weight: .bold)).lineLimit(1)
                            .contentTransition(.opacity)
                        Text(np?.artist ?? "Not Playing").font(.system(size: 11, weight: .medium)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                if family != .systemSmall {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("NOW PLAYING").font(.system(size: 10, weight: .bold)).tracking(1).foregroundStyle(.secondary)
                        Text(np?.title ?? "iPod").font(.system(size: 17, weight: .heavy)).lineLimit(2)
                        Text(np?.artist ?? "Not Playing").font(.system(size: 13, weight: .semibold)).foregroundStyle(.secondary).lineLimit(1)
                        if let np, np.playing, np.duration > 0 {
                            Text(Date().addingTimeInterval(max(0, np.duration - np.elapsed) - Date().timeIntervalSince(np.updatedAt)), style: .timer)
                                .font(.system(size: 11, weight: .semibold).monospacedDigit()).foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: geo.size.width * 0.42, alignment: .leading)
                    .offset(x: geo.size.width * 0.56)
                    .frame(maxHeight: .infinity)
                }
                // tap zones over everything
                HStack(spacing: 0) {
                    TapZone(intent: IPodPreviousIntent())
                    TapZone(intent: IPodPlayPauseIntent())
                    TapZone(intent: IPodNextIntent())
                }
                // faint hints at the edges
                HStack {
                    Image(systemName: "backward.fill")
                    Spacer()
                    Image(systemName: (np?.playing ?? false) ? "pause.fill" : "play.fill")
                    Spacer()
                    Image(systemName: "forward.fill")
                }
                .font(.system(size: 9, weight: .bold)).foregroundStyle(.secondary.opacity(0.6))
                .frame(maxHeight: .infinity, alignment: .bottom)
                .allowsHitTesting(false)
            }
        }
        .containerBackground(for: .widget) {
            LinearGradient(colors: [Color(white: 0.97), tone.opacity(0.18)], startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }
}

struct NowPlayingWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: IPodShared.nowPlayingKind, provider: IPodProvider()) { entry in
            NowPlayingView(entry: entry)
        }
        .configurationDisplayName("iPod Now Playing")
        .description("The cover and a spinning record. Tap left for previous, right for next, the middle to play or pause.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

// MARK: - Car Flow widget: album spines around the one playing; tap one to play it

struct SpineView: View {
    let album: IPodFlowAlbum
    let left: Bool
    let height: CGFloat
    let dark: Bool
    var body: some View {
        HStack(spacing: 0) {
            if !left { sliver }
            Text(album.album)
                .font(.system(size: 8, weight: .bold)).lineLimit(1)
                .foregroundStyle(dark ? Color.white : Color.black)
                .fixedSize()
                .rotationEffect(.degrees(-90))
                .frame(width: 13, height: height)
                .background(dark ? Color(white: 0.09) : Color(white: 0.96))
                .clipped()
            if left { sliver }
        }
    }
    var sliver: some View {
        CoverView(name: album.art, corner: 0)
            .frame(width: 18, height: height)
            .rotation3DEffect(.degrees(left ? 55 : -55), axis: (x: 0, y: 1, z: 0), anchor: left ? .leading : .trailing, perspective: 0.6)
    }
}

struct CarFlowView: View {
    let entry: IPodEntry
    @Environment(\.widgetFamily) var family

    var body: some View {
        let flow = entry.np?.flow ?? []
        let ci = flow.firstIndex(where: { $0.current }) ?? (flow.count / 2)
        let reach = family == .systemSmall ? 1 : 3
        GeometryReader { geo in
            let side = min(geo.size.height * 0.72, geo.size.width * 0.5)
            VStack(spacing: 4) {
                HStack(spacing: 3) {
                    ForEach(Array(flow.enumerated()), id: \.offset) { k, a in
                        if k >= ci - reach && k < ci {
                            Button(intent: IPodPlayAlbumIntent(index: a.index)) {
                                SpineView(album: a, left: true, height: side, dark: k % 2 == 0)
                            }.buttonStyle(.plain)
                        }
                    }
                    if flow.indices.contains(ci) {
                        Button(intent: IPodPlayPauseIntent()) {
                            CoverView(name: flow[ci].art, corner: 4)
                                .frame(width: side, height: side)
                                .shadow(color: .black.opacity(0.3), radius: 5, y: 3)
                                .id(flow[ci].album)
                                .transition(.push(from: .trailing))
                        }.buttonStyle(.plain)
                    } else {
                        CoverView(name: nil).frame(width: side, height: side)
                    }
                    ForEach(Array(flow.enumerated()), id: \.offset) { k, a in
                        if k > ci && k <= ci + reach {
                            Button(intent: IPodPlayAlbumIntent(index: a.index)) {
                                SpineView(album: a, left: false, height: side, dark: k % 2 == 1)
                            }.buttonStyle(.plain)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                Text(flow.indices.contains(ci) ? flow[ci].album : "Car Flow")
                    .font(.system(size: 12, weight: .bold)).lineLimit(1)
                    .contentTransition(.opacity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .containerBackground(for: .widget) { Color(white: 0.95) }
    }
}

struct CarFlowWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: IPodShared.carFlowKind, provider: IPodProvider()) { entry in
            CarFlowView(entry: entry)
        }
        .configurationDisplayName("iPod Car Flow")
        .description("Your albums side by side. Tap one to play it.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

// MARK: - Live Activity: cover, song and the current lyric line

struct IPodActivityView: View {
    let state: IPodActivityAttributes.ContentState
    @Environment(\.activityFamily) var activityFamily

    var body: some View {
        if activityFamily == .small {
            // CarPlay and Apple Watch
            HStack(spacing: 8) {
                CoverView(name: state.art, corner: 5).frame(width: 34, height: 34)
                VStack(alignment: .leading, spacing: 1) {
                    Text(state.lyric.isEmpty ? state.title : state.lyric).font(.system(size: 13, weight: .bold)).lineLimit(2)
                    Text(state.lyric.isEmpty ? state.artist : state.title).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .padding(8)
        } else {
            HStack(spacing: 12) {
                CoverView(name: state.art, corner: 8).frame(width: 58, height: 58)
                VStack(alignment: .leading, spacing: 2) {
                    Text(state.title).font(.system(size: 15, weight: .bold)).lineLimit(1)
                    Text(state.artist).font(.system(size: 13)).foregroundStyle(.secondary).lineLimit(1)
                    if !state.lyric.isEmpty {
                        Text(state.lyric).font(.system(size: 14, weight: .semibold)).lineLimit(2)
                            .contentTransition(.opacity).padding(.top, 2)
                    }
                }
                Spacer(minLength: 0)
                HStack(spacing: 14) {
                    Button(intent: IPodPreviousIntent()) { Image(systemName: "backward.fill") }.buttonStyle(.plain)
                    Button(intent: IPodPlayPauseIntent()) { Image(systemName: state.playing ? "pause.fill" : "play.fill") }.buttonStyle(.plain)
                    Button(intent: IPodNextIntent()) { Image(systemName: "forward.fill") }.buttonStyle(.plain)
                }
                .font(.system(size: 17))
            }
            .padding(14)
        }
    }
}

struct IPodLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: IPodActivityAttributes.self) { context in
            IPodActivityView(state: context.state)
                .activityBackgroundTint(Color(hex: context.state.tone).opacity(0.25))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    CoverView(name: context.state.art, corner: 6).frame(width: 44, height: 44)
                }
                DynamicIslandExpandedRegion(.center) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(context.state.title).font(.system(size: 14, weight: .bold)).lineLimit(1)
                        Text(context.state.artist).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Button(intent: IPodPlayPauseIntent()) { Image(systemName: context.state.playing ? "pause.fill" : "play.fill") }.buttonStyle(.plain)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    if !context.state.lyric.isEmpty {
                        Text(context.state.lyric).font(.system(size: 14, weight: .semibold)).lineLimit(2)
                    }
                }
            } compactLeading: {
                CoverView(name: context.state.art, corner: 4).frame(width: 22, height: 22)
            } compactTrailing: {
                Image(systemName: context.state.playing ? "waveform" : "pause.fill")
                    .foregroundStyle(Color(hex: context.state.tone))
            } minimal: {
                Image(systemName: "opticaldisc")
            }
        }
        .supplementalActivityFamilies([.small, .medium])
    }
}

// MARK: - Bundle

@main
struct IPodWidgets: WidgetBundle {
    var body: some Widget {
        NowPlayingWidget()
        CarFlowWidget()
        IPodLiveActivity()
    }
}
