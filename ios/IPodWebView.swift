import SwiftUI
import WebKit
import UIKit
import CoreHaptics

// Root view of the native wrapper. Loads the hosted iPod page in a WKWebView and turns
// `window.webkit.messageHandlers.ipodHaptics.postMessage(...)` calls into Taptic Engine feedback.
// Only the top-level page from the trusted origin (hostedURL's scheme + host) can trigger haptics;
// messages from other origins or from embedded frames (e.g. the YouTube player) are ignored.
//
// Message body: either a plain kind string ("selection" | "confirm" | "success"), or an object
// { kind, intensity: 0–1, sharpness: 0–1, count } built from the iPod's Settings ▸ Haptic Strength / Feel.
struct IPodWebView: UIViewRepresentable {
    let hostedURL: URL

    func makeCoordinator() -> Coordinator { Coordinator(trustedURL: hostedURL) }

    func makeUIView(context: Context) -> WKWebView {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: Coordinator.handlerName)
        controller.add(context.coordinator, name: Coordinator.batteryHandlerName)

        let configuration = WKWebViewConfiguration()
        configuration.userContentController = controller
        configuration.allowsInlineMediaPlayback = true
        configuration.mediaTypesRequiringUserActionForPlayback = []

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.isOpaque = false
        webView.backgroundColor = .black
        webView.scrollView.backgroundColor = .black
        webView.scrollView.isScrollEnabled = false
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never   // the page handles safe areas itself
        webView.allowsBackForwardNavigationGestures = false
        #if DEBUG
        if #available(iOS 16.4, *) { webView.isInspectable = true }   // Safari ▸ Develop for on-device debugging
        #endif
        context.coordinator.monitorBattery(in: webView)
        webView.load(URLRequest(url: hostedURL, cachePolicy: .reloadRevalidatingCacheData))   // always pick up the latest site
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) {
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.handlerName)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.batteryHandlerName)
        coordinator.stopMonitoringBattery()
    }

    final class Coordinator: NSObject, WKScriptMessageHandler {
        static let handlerName = "ipodHaptics"
        static let batteryHandlerName = "ipodBattery"
        private weak var batteryWebView: WKWebView?
        private var previousBatteryMonitoring = false

        private let trustedScheme: String
        private let trustedHost: String
        private let trustedPort: Int
        private let player = HapticPlayer()

        init(trustedURL: URL) {
            trustedScheme = (trustedURL.scheme ?? "https").lowercased()
            trustedHost = (trustedURL.host ?? "").lowercased()
            trustedPort = trustedURL.port ?? (trustedScheme == "https" ? 443 : 80)
        }

        func monitorBattery(in webView: WKWebView) {
            batteryWebView = webView
            previousBatteryMonitoring = UIDevice.current.isBatteryMonitoringEnabled
            UIDevice.current.isBatteryMonitoringEnabled = true
            for name in [UIDevice.batteryLevelDidChangeNotification,
                         UIDevice.batteryStateDidChangeNotification,
                         UIApplication.didBecomeActiveNotification] {
                NotificationCenter.default.addObserver(self, selector: #selector(batteryChanged(_:)),
                                                       name: name, object: nil)
            }
        }

        func stopMonitoringBattery() {
            NotificationCenter.default.removeObserver(self)
            UIDevice.current.isBatteryMonitoringEnabled = previousBatteryMonitoring
            batteryWebView = nil
        }

        @objc private func batteryChanged(_ notification: Notification) {
            sendBattery()
        }

        private func sendBattery() {
            let device = UIDevice.current
            let level = device.batteryLevel
            let charging = device.batteryState == .charging || device.batteryState == .full
            let script = """
                const port = location.port || (location.protocol === 'https:' ? '443' : '80');
                if (location.protocol === scheme + ':' && location.hostname === host && port === expectedPort) {
                    window.ipodSetBattery?.(level, charging);
                }
                """
            batteryWebView?.callAsyncJavaScript(script, arguments: [
                "level": Double(level), "charging": charging, "scheme": trustedScheme,
                "host": trustedHost, "expectedPort": String(trustedPort)
            ], in: nil, in: .page, completionHandler: nil)
        }

        /// True only for the main frame of the hosted page's own origin.
        func isTrusted(_ message: WKScriptMessage) -> Bool {
            guard message.frameInfo.isMainFrame else { return false }
            let origin = message.frameInfo.securityOrigin
            let port = origin.port == 0 ? (origin.protocol == "https" ? 443 : 80) : origin.port
            return origin.protocol.lowercased() == trustedScheme
                && origin.host.lowercased() == trustedHost
                && port == trustedPort
        }

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard isTrusted(message) else { return }
            if message.name == Self.batteryHandlerName {
                sendBattery()
                return
            }
            guard message.name == Self.handlerName else { return }

            var kind = "selection"
            var intensity: Float?
            var sharpness: Float?
            var count = 1
            if let s = message.body as? String {
                kind = s
            } else if let d = message.body as? [String: Any] {
                kind = d["kind"] as? String ?? kind
                intensity = (d["intensity"] as? NSNumber)?.floatValue
                sharpness = (d["sharpness"] as? NSNumber)?.floatValue
                count = (d["count"] as? NSNumber)?.intValue ?? count
            } else { return }

            // Defaults for plain-string messages from older versions of the page.
            let defaults: (Float, Float, Int) = {
                switch kind {
                case "confirm": return (1.0, 0.6, 1)
                case "success": return (1.0, 0.8, 2)
                default:        return (0.85, 0.9, 1)
                }
            }()
            let i = min(max(intensity ?? defaults.0, 0), 1)
            let s = min(max(sharpness ?? defaults.1, 0), 1)
            let n = min(max(count, 1), 4)
            DispatchQueue.main.async { self.player.play(intensity: i, sharpness: s, count: n) }
        }
    }
}

/// Plays short transient taps on the Taptic Engine with a given intensity and sharpness.
/// Uses Core Haptics where available (stronger and more tunable than UISelectionFeedbackGenerator),
/// and falls back to UIImpactFeedbackGenerator otherwise.
final class HapticPlayer {
    private var engine: CHHapticEngine?
    private var engineRunning = false
    private let fallback = UIImpactFeedbackGenerator(style: .rigid)

    init() {
        fallback.prepare()
        guard CHHapticEngine.capabilitiesForHardware().supportsHaptics,
              let engine = try? CHHapticEngine() else { return }
        engine.playsHapticsOnly = true            // don't interfere with music playback
        engine.isAutoShutdownEnabled = true       // save battery when the wheel is idle
        engine.stoppedHandler = { [weak self] _ in self?.engineRunning = false }
        engine.resetHandler = { [weak self] in
            self?.engineRunning = false
            self?.startEngine()
        }
        self.engine = engine
        startEngine()
    }

    private func startEngine() {
        guard let engine, !engineRunning else { return }
        do { try engine.start(); engineRunning = true } catch { engineRunning = false }
    }

    func play(intensity: Float, sharpness: Float, count: Int, gap: TimeInterval = 0.08) {
        guard let engine else { playFallback(intensity: intensity, count: count, gap: gap); return }
        startEngine()
        let events = (0..<count).map { n in
            CHHapticEvent(eventType: .hapticTransient,
                          parameters: [CHHapticEventParameter(parameterID: .hapticIntensity, value: intensity),
                                       CHHapticEventParameter(parameterID: .hapticSharpness, value: sharpness)],
                          relativeTime: gap * Double(n))
        }
        do {
            let pattern = try CHHapticPattern(events: events, parameters: [])
            try engine.makePlayer(with: pattern).start(atTime: CHHapticTimeImmediate)
        } catch {
            engineRunning = false
            playFallback(intensity: intensity, count: count, gap: gap)
        }
    }

    private func playFallback(intensity: Float, count: Int, gap: TimeInterval) {
        for n in 0..<count {
            DispatchQueue.main.asyncAfter(deadline: .now() + gap * Double(n)) {
                self.fallback.impactOccurred(intensity: CGFloat(intensity))
                self.fallback.prepare()
            }
        }
    }
}
