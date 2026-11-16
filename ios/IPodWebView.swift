import SwiftUI
import WebKit
import UIKit
import CoreHaptics
import AVFoundation
import MediaPlayer

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

    /// Plain container that pins the web view to its edges with Auto Layout, so the page always gets the
    /// real window size (also mid-rotation), and tells the page to re-measure whenever the size changes.
    final class WebContainer: UIView {
        let webView: WKWebView
        private var lastSize: CGSize = .zero
        init(webView: WKWebView) {
            self.webView = webView
            super.init(frame: .zero)
            backgroundColor = .black
            webView.translatesAutoresizingMaskIntoConstraints = false
            addSubview(webView)
            NSLayoutConstraint.activate([
                webView.leadingAnchor.constraint(equalTo: leadingAnchor),
                webView.trailingAnchor.constraint(equalTo: trailingAnchor),
                webView.topAnchor.constraint(equalTo: topAnchor),
                webView.bottomAnchor.constraint(equalTo: bottomAnchor)
            ])
        }
        required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
        override func layoutSubviews() {
            super.layoutSubviews()
            guard bounds.size != lastSize, bounds.width > 0, bounds.height > 0 else { return }
            lastSize = bounds.size
            webView.setNeedsLayout(); webView.layoutIfNeeded()
            // WebKit can report the old viewport for a moment after rotating; ask the page to fit again.
            webView.evaluateJavaScript("window.ipodRefit && window.ipodRefit()", completionHandler: nil)
        }
    }

    func makeUIView(context: Context) -> WebContainer {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: Coordinator.handlerName)
        controller.add(context.coordinator, name: Coordinator.batteryHandlerName)
        controller.add(context.coordinator, name: Coordinator.audioRouteHandlerName)
        controller.add(context.coordinator, name: Coordinator.alarmHandlerName)
        controller.add(context.coordinator, name: Coordinator.volumeHandlerName)
        controller.add(context.coordinator, name: Coordinator.shareFileHandlerName)
        controller.add(context.coordinator, name: Coordinator.keepAwakeHandlerName)

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
        webView.uiDelegate = context.coordinator
        context.coordinator.monitorDevice(in: webView)
        webView.load(URLRequest(url: hostedURL, cachePolicy: .reloadRevalidatingCacheData))   // always pick up the latest site
        return WebContainer(webView: webView)
    }

    func updateUIView(_ uiView: WebContainer, context: Context) {}

    static func dismantleUIView(_ container: WebContainer, coordinator: Coordinator) {
        let uiView = container.webView
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.handlerName)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.batteryHandlerName)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.audioRouteHandlerName)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.alarmHandlerName)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.volumeHandlerName)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.shareFileHandlerName)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.keepAwakeHandlerName)
        coordinator.stopMonitoringDevice()
    }

    final class Coordinator: NSObject, WKScriptMessageHandler, WKUIDelegate {
        static let handlerName = "ipodHaptics"
        static let batteryHandlerName = "ipodBattery"
        static let audioRouteHandlerName = "ipodAudioRoute"
        static let alarmHandlerName = "ipodAlarm"
        static let volumeHandlerName = "ipodVolume"
        static let shareFileHandlerName = "ipodShareFile"
        static let keepAwakeHandlerName = "ipodKeepAwake"
        /// A nearly invisible system volume view: lets the click wheel set the real iPhone volume
        /// and hides the iOS volume pop-up, so the iPod's own volume bar shows instead.
        private let volumeView = MPVolumeView(frame: CGRect(x: -2000, y: -2000, width: 10, height: 10))
        private var volumeObservation: NSKeyValueObservation?
        private weak var deviceWebView: WKWebView?
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

        func monitorDevice(in webView: WKWebView) {
            deviceWebView = webView
            previousBatteryMonitoring = UIDevice.current.isBatteryMonitoringEnabled
            UIDevice.current.isBatteryMonitoringEnabled = true
            for name in [UIDevice.batteryLevelDidChangeNotification,
                         UIDevice.batteryStateDidChangeNotification,
                         UIApplication.didBecomeActiveNotification] {
                NotificationCenter.default.addObserver(self, selector: #selector(batteryChanged(_:)),
                                                       name: name, object: nil)
            }
            volumeView.alpha = 0.01
            volumeView.isUserInteractionEnabled = false
            webView.addSubview(volumeView)
            volumeObservation = AVAudioSession.sharedInstance().observe(\.outputVolume, options: [.new]) { [weak self] session, _ in
                DispatchQueue.main.async { self?.sendVolume(session.outputVolume) }
            }
            NotificationCenter.default.addObserver(self, selector: #selector(wakeRequested(_:)), name: .ipodWakeUp, object: nil)
            if IPodAlarm.shared.pendingWake { deliverWake(attempt: 0) }   // launched by tapping the alarm
            for name in [AVAudioSession.routeChangeNotification, UIApplication.didBecomeActiveNotification] {
                NotificationCenter.default.addObserver(self, selector: #selector(audioRouteChanged(_:)),
                                                       name: name, object: nil)
            }
        }

        @objc private func wakeRequested(_ note: Notification) { deliverWake(attempt: 0) }

        /// Backup & Restore: hand the backup file to the share sheet (Save to Files, AirDrop, …).
        private func shareFile(named name: String, contents: String) {
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
            do { try contents.data(using: .utf8)?.write(to: url, options: .atomic) } catch { return }
            DispatchQueue.main.async {
                guard let webView = self.deviceWebView,
                      let root = webView.window?.rootViewController else { return }
                var top = root
                while let presented = top.presentedViewController { top = presented }
                let sheet = UIActivityViewController(activityItems: [url], applicationActivities: nil)
                sheet.popoverPresentationController?.sourceView = webView
                sheet.popoverPresentationController?.sourceRect = CGRect(x: webView.bounds.midX, y: webView.bounds.midY, width: 1, height: 1)
                top.present(sheet, animated: true)
            }
        }

        private func sendVolume(_ value: Float) {
            deviceWebView?.evaluateJavaScript("window.ipodSystemVolume && window.ipodSystemVolume(\(value))", completionHandler: nil)
        }

        private func setSystemVolume(_ value: Float) {
            let v = min(max(value, 0), 1)
            guard let slider = volumeView.subviews.compactMap({ $0 as? UISlider }).first else { return }
            DispatchQueue.main.async { slider.setValue(v, animated: false); slider.sendActions(for: .valueChanged) }
        }

        /// Calls the page's `ipodWakeUp()`, retrying while the page is still loading.
        private func deliverWake(attempt: Int) {
            guard let webView = deviceWebView, attempt < 40 else { return }
            webView.evaluateJavaScript("window.ipodWakeUp && window.ipodWakeUp() ? 1 : 0") { [weak self] result, _ in
                if (result as? NSNumber)?.intValue == 1 { _ = IPodAlarm.shared.takePendingWake(); return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self?.deliverWake(attempt: attempt + 1) }
            }
        }

        func stopMonitoringDevice() {
            UIApplication.shared.isIdleTimerDisabled = false
            volumeObservation?.invalidate(); volumeObservation = nil
            volumeView.removeFromSuperview()
            NotificationCenter.default.removeObserver(self)
            UIDevice.current.isBatteryMonitoringEnabled = previousBatteryMonitoring
            deviceWebView = nil
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
            deviceWebView?.callAsyncJavaScript(script, arguments: [
                "level": Double(level), "charging": charging, "scheme": trustedScheme,
                "host": trustedHost, "expectedPort": String(trustedPort)
            ], in: nil, in: .page, completionHandler: nil)
        }

        @objc private func audioRouteChanged(_ notification: Notification) {
            DispatchQueue.main.async { [weak self] in self?.sendAudioRoute() }
        }

        private func sendAudioRoute() {
            let outputs = AVAudioSession.sharedInstance().currentRoute.outputs
            let isCarPlay = outputs.contains { $0.portType == .carAudio }
            // Wired EarPods report as headphones (Lightning / 3.5 mm adapter) or USB audio (USB-C).
            let wiredPorts: [AVAudioSession.Port] = [.headphones, .usbAudio]
            let bluetoothPorts: [AVAudioSession.Port] = [.bluetoothA2DP, .bluetoothLE, .bluetoothHFP]
            let headphones = outputs.contains { wiredPorts.contains($0.portType) } ? "wired"
                : outputs.contains { bluetoothPorts.contains($0.portType) } ? "bluetooth" : ""
            let script = """
                const port = location.port || (location.protocol === 'https:' ? '443' : '80');
                if (location.protocol === scheme + ':' && location.hostname === host && port === expectedPort) {
                    window.ipodSetCarPlayRoute?.(isCarPlay);
                    window.ipodSetHeadphones?.(headphones);
                }
                """
            deviceWebView?.callAsyncJavaScript(script, arguments: [
                "isCarPlay": isCarPlay, "headphones": headphones, "scheme": trustedScheme,
                "host": trustedHost, "expectedPort": String(trustedPort)
            ], in: nil, in: .page, completionHandler: nil)
        }

        /// True only for the main frame of the hosted page's own origin.
        func isTrusted(_ message: WKScriptMessage) -> Bool {
            guard message.frameInfo.isMainFrame else { return false }
            return isTrusted(origin: message.frameInfo.securityOrigin)
        }

        // Shake to Shuffle: let the iPod page read the motion sensors without a web prompt
        // (WKWebView otherwise denies DeviceMotionEvent.requestPermission()).
        func webView(_ webView: WKWebView, requestDeviceOrientationAndMotionPermissionFor origin: WKSecurityOrigin,
                     initiatedByFrame frame: WKFrameInfo, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(isTrusted(origin: origin) ? .grant : .deny)
        }

        func isTrusted(origin: WKSecurityOrigin) -> Bool {
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
            if message.name == Self.audioRouteHandlerName {
                sendAudioRoute()
                return
            }
            if message.name == Self.keepAwakeHandlerName {
                // Hold switch: keep the iPhone's screen from dimming and auto-locking while it's on.
                let on = ((message.body as? [String: Any])?["on"] as? Bool) ?? false
                DispatchQueue.main.async { UIApplication.shared.isIdleTimerDisabled = on }
                return
            }
            if message.name == Self.shareFileHandlerName {
                guard let d = message.body as? [String: Any], let text = d["text"] as? String else { return }
                let raw = (d["name"] as? String) ?? "iPod Backup.json"
                let name = raw.replacingOccurrences(of: "/", with: "-")
                shareFile(named: name, contents: text)
                return
            }
            if message.name == Self.volumeHandlerName {
                let d = message.body as? [String: Any] ?? [:]
                if let v = (d["set"] as? NSNumber)?.floatValue { setSystemVolume(v) }
                else { sendVolume(AVAudioSession.sharedInstance().outputVolume) }
                return
            }
            if message.name == Self.alarmHandlerName {
                guard let d = message.body as? [String: Any] else { return }
                if (d["action"] as? String) == "night" {
                    IPodAlarm.shared.nightMode = (d["on"] as? Bool) ?? false
                    return
                }
                if (d["action"] as? String) == "schedule" {
                    IPodAlarm.shared.schedule(hour: (d["hour"] as? NSNumber)?.intValue ?? 7,
                                              minute: (d["minute"] as? NSNumber)?.intValue ?? 0,
                                              repeats: (d["repeat"] as? Bool) ?? true,
                                              label: (d["label"] as? String) ?? "your music")
                } else {
                    IPodAlarm.shared.cancel()
                }
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
