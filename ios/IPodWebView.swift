import SwiftUI
import WebKit
import UIKit

// Root view of the native wrapper. Loads the hosted iPod page in a WKWebView and turns
// `window.webkit.messageHandlers.ipodHaptics.postMessage(kind)` calls into Taptic Engine feedback.
// Only the top-level page from the trusted origin (hostedURL's scheme + host) can trigger haptics;
// messages from other origins or from embedded frames (e.g. the YouTube player) are ignored.
struct IPodWebView: UIViewRepresentable {
    let hostedURL: URL

    func makeCoordinator() -> Coordinator { Coordinator(trustedURL: hostedURL) }

    func makeUIView(context: Context) -> WKWebView {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: Coordinator.handlerName)

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
        webView.load(URLRequest(url: hostedURL, cachePolicy: .reloadRevalidatingCacheData))   // always pick up the latest site
        context.coordinator.prepare()
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) {
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.handlerName)
    }

    final class Coordinator: NSObject, WKScriptMessageHandler {
        static let handlerName = "ipodHaptics"

        private let trustedScheme: String
        private let trustedHost: String
        private let trustedPort: Int
        private let selection = UISelectionFeedbackGenerator()
        private let impact = UIImpactFeedbackGenerator(style: .medium)
        private let notification = UINotificationFeedbackGenerator()

        init(trustedURL: URL) {
            trustedScheme = (trustedURL.scheme ?? "https").lowercased()
            trustedHost = (trustedURL.host ?? "").lowercased()
            trustedPort = trustedURL.port ?? (trustedScheme == "https" ? 443 : 80)
        }

        func prepare() {
            selection.prepare(); impact.prepare(); notification.prepare()
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
            guard message.name == Self.handlerName,
                  isTrusted(message),
                  let kind = message.body as? String else { return }
            DispatchQueue.main.async {
                switch kind {
                case "selection": self.selection.selectionChanged(); self.selection.prepare()
                case "confirm":   self.impact.impactOccurred();      self.impact.prepare()
                case "success":   self.notification.notificationOccurred(.success); self.notification.prepare()
                default:          self.selection.selectionChanged(); self.selection.prepare()
                }
            }
        }
    }
}
