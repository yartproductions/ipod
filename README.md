# iPod

An iPod Classic–style music player: click wheel, clicker, haptics, menus. There are two ways to run it:

| | Web (Safari / Home Screen) | Native iOS wrapper (`ios/`) |
|---|---|---|
| Ad-free local music | ✅ | ✅ |
| YouTube (official embed) | ✅ | ✅ |
| Click-wheel haptics on iPhone | ❌ not supported by Safari | ✅ via Taptic Engine (needs a physical iPhone to confirm) |
| Local music with the screen locked | Not guaranteed on iOS | Intended (`UIBackgroundModes: audio`); confirm on a device |
| YouTube with the screen locked | ❌ | ❌ (YouTube's player rules) |

Live site: https://yartproductions.github.io/ipod/

## Ad-Free Local Music
Main menu → **Ad-Free Local Music** (or **Add Music**) and pick audio files from your phone.
- It reads ID3 tags (title, artist, album, track number, cover art) from MP3s. Other formats fall back to the file name.
- The library is stored in the browser (IndexedDB) and survives a reload. Clearing website data, or iOS evicting storage, removes it.
- It supports Artists, Albums, Songs, Shuffle, and Repeat (Off / One / All).
- Lock-screen and Control Center show the song title, artist, artwork and position (Media Session API).
- Local files play with no third-party ads.
- **Background playback in Safari or the Home Screen app is not guaranteed on iOS.** iOS may pause a web page when the screen locks or you switch apps. The native wrapper is the intended way to get reliable background audio, and it still needs testing on a device.

## Haptics
`click()` and `press()` call `triggerHaptic(kind)`, where `kind` is `selection`, `confirm` or `success`:
1. **Native wrapper:** posts to `window.webkit.messageHandlers.ipodHaptics`, and the Swift side plays `UISelectionFeedbackGenerator`, `UIImpactFeedbackGenerator(.medium)` or `UINotificationFeedbackGenerator(.success)`.
2. **Browsers with `navigator.vibrate`** (e.g. Android Chrome): a short vibration.
3. **iPhone Safari / Home Screen:** no haptics. Safari offers no supported haptics API, and the old hidden-switch hack has been removed.

Haptics fired during the same input event collapse into one (strongest wins), and wheel ticks are throttled to one per 35 ms. Settings → About shows which mode is active (`Native`, `Vibrate` or `None`).

## Native iOS wrapper (`ios/`)
A SwiftUI app that loads the GitHub Pages site in a `WKWebView` and handles haptic messages. It needs a Mac with Xcode 15+.

```sh
brew install xcodegen
cd ios
xcodegen generate
open IPod.xcodeproj
```
In Xcode, choose your team under **Signing & Capabilities**, connect your iPhone, and press Run. A free Apple ID works for installing on your own phone, but such builds expire after 7 days.

- `IPodApp.swift`: app entry point. Sets the audio session to `.playback` and holds the hosted URL.
- `IPodWebView.swift`: the web view and haptics message handler. It only accepts messages from the **main frame** of the hosted origin (`https://yartproductions.github.io`). Messages from other sites or embedded frames, such as the YouTube player, are ignored.
- `project.yml`: XcodeGen spec (iOS 16+, portrait, background audio mode).

## YouTube
- **Paste Link** takes any YouTube or YouTube Music video or playlist link.
- **Search** needs a free YouTube Data API key:
  1. In Google Cloud Console, create a project.
  2. Enable **YouTube Data API v3**.
  3. Create an **API key**.
  4. Restrict it to the website `https://yartproductions.github.io/*` and to that API.
  5. Paste it into **YouTube → YouTube Key**.
- Videos play through YouTube's official embedded player. **Ads are not blocked or skipped.** YouTube decides whether ads appear (YouTube Premium affects this, not this app).
- The video has to stay visible while it plays. It pauses when you go back to the menus and resumes when you return to Now Playing.
- Starting local music cancels any pending YouTube load, so a video can't start on its own while you're in local mode.

## Tests
```sh
pip install playwright        # plus a Chrome/Chromium; set CHROME=/path/to/chrome if needed
python3 tests/e2e.py
```
These are headless Chrome tests, using generated tagged MP3s in `tests/fixtures/` and a stand-in for YouTube's player script. They cover:
- menu navigation and wheel scrolling
- haptic messages to a mocked native bridge, coalescing, and the Haptics Off setting
- the `navigator.vibrate` fallback
- import with ID3 tags and art, and persistence across reloads
- auto-advance, next, Repeat Off / All, and Shuffle
- Media Session metadata
- Paste Link, and pausing the video when hidden
- the race where a queued YouTube load must not autoplay after local music starts

They can't verify real Taptic output, iOS background audio, the lock screen, or anything in the Swift code. Those need a physical iPhone; see the checklist in the pull request.

## Maintenance
`apply_patch.py` applies the haptic bridge change to an older `index.html`. It's idempotent, and safe to rerun on the current file.
