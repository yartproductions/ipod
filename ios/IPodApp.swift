import SwiftUI
import AVFoundation

@main
struct IPodApp: App {
    /// The published GitHub Pages site. Only this origin may send haptic messages.
    static let hostedURL = URL(string: "https://yartproductions.github.io/ipod/")!

    init() {
        // Playback category so local music keeps playing with the silent switch on, and
        // (together with UIBackgroundModes = audio) can continue when the screen locks.
        // Background playback inside WKWebView still has to be confirmed on a physical iPhone.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
        try? AVAudioSession.sharedInstance().setActive(true)
    }

    var body: some Scene {
        WindowGroup {
            IPodWebView(hostedURL: Self.hostedURL)
                .ignoresSafeArea()
                .background(Color.black)
                .preferredColorScheme(.dark)
                .statusBarHidden(false)
        }
    }
}
