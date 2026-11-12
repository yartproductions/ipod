# iPod

An iPod Classic–style music player: click wheel, clicker, haptics, menus. There are two ways to run it:

| | Web (Safari / Home Screen) | Native iOS wrapper (`ios/`) |
|---|---|---|
| Ad-free local music | ✅ | ✅ |
| Offline library (airplane mode), backup / restore | ✅ | partial (see Offline library) |
| Authorized YTMP3 download handoff | ✅ | ✅ |
| YouTube (official embed, **has ads**, off by default) | opt-in | opt-in |
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

## Offline library
Your songs are stored on the device as the actual audio files, so the iPod works in airplane mode.

- **Where songs come from:**
  - **Add Music:** import your own files.
  - **YTMP3 Download:** opens the provider only after you confirm that you own or have permission to save the video; import the finished MP3 with **Add Music**.
  - **Restore Backup:** brings back a library you backed up.
- **Storage:** IndexedDB database `ipod`, version 2. Each record holds the complete audio file plus artwork and details: title, artist, album, track, length, file type, size, a SHA-256 fingerprint, where it came from, and the date added. Upgrading from version 1 only adds lookup indexes; existing songs are kept and get their fingerprint filled in quietly in the background.
- **Duplicates:** importing or restoring the same audio twice is skipped by its SHA-256 fingerprint.
- **Settings → Library & Storage:**
  - songs saved, storage used and space available
  - **Keep Storage**, which asks the browser not to delete your data
  - **Back Up Library** and **Restore Backup**
  - **Delete Songs** (one at a time) and **Clear Library**
- **Offline launch:** a service worker (`sw.js`) caches the app's own files so it opens with no network. Online, it always fetches the latest version. It never touches YTMP3 or YouTube requests.
- **Offline behavior:** imported songs play normally with no network.

### Authorized YTMP3 downloads
- Paste a single YouTube video link under **YTMP3 Download**. Playlists are rejected.
- The converter opens only after **I Have Permission** is selected. Use it only for content you own, public-domain or suitably licensed content, or content you have explicit permission to download.
- The provider's supported browser interface opens in a separate tab. Its JSON conversion endpoint does not grant cross-origin browser access, so this static app does not claim it can fetch files directly.
- After the MP3 finishes, return to the iPod and choose **Import Download** or **Add Music**. The existing IndexedDB pipeline fingerprints and stores the complete Blob for offline playback.

### Backup and restore
- **Format:** **Back Up Library** writes `iPod-Library-YYYY-MM-DD.zip`. It's a plain, uncompressed ZIP containing:
  - `manifest.json` (format `ipod-library-backup`, version 1): every song's details and your YouTube saved items
  - `audio/<id>.<ext>`: the **original audio bytes**
  - `art/<id>.<ext>`: artwork
- **Memory:** the audio isn't copied in memory to build the ZIP, and fingerprints are computed in 4 MB chunks.
- **Saving it on iPhone:** press the center button, then **Save to Files**. Desktop browsers download it directly.
- **Restoring:** it checks the manifest and confirms every audio file is present **before** importing anything, verifies each file's checksum, skips songs you already have, and merges saved playlists.
- **Limits:** backups must be under 4 GB, and only ZIPs made by the iPod can be restored, not recompressed ones.

### Storage limitations
- **Browser storage can be removed.** IndexedDB survives restarts, but **iOS and browsers can delete website data**, for example when space is low or the site goes unused for weeks. **Keep Storage** asks the browser to protect it, but it isn't a guarantee. **Keep a backup.**
- **Each app has its own library.** Safari, the Home Screen web app and the native iOS wrapper store data separately.
- **The native iOS wrapper** (`ios/`) doesn't yet support the service worker (that needs app-bound domains), so it can't open with no network. Backup downloads there also aren't wired up. Use Safari or the Home Screen app for offline listening and backups.
- **Downloads don't continue in the background.** Keep the iPod open while saving songs; iOS may suspend the page otherwise.

## Haptics
`click()` and `press()` call `triggerHaptic(kind)`, where `kind` is `selection`, `confirm` or `success`:
1. **Native wrapper:** posts to `window.webkit.messageHandlers.ipodHaptics`, and the Swift side plays `UISelectionFeedbackGenerator`, `UIImpactFeedbackGenerator(.medium)` or `UINotificationFeedbackGenerator(.success)`.
2. **Browsers with `navigator.vibrate`** (e.g. Android Chrome): a short vibration.
3. **iPhone Safari / Home Screen:** no haptics. Safari offers no supported haptics API, and the old hidden-switch hack has been removed.

**Customize in Settings:** **Haptic Strength** (Light / Medium / Strong / Max) and **Haptic Feel** (Crisp / Click / Soft / Thud). Each change plays a sample tap, and **Test Haptic** plays a double tap. The page sends `{kind, intensity, sharpness, count}` to the native app, which plays it with **Core Haptics**. That's stronger and more tunable than the standard system tick, and it falls back to `UIImpactFeedbackGenerator` if Core Haptics isn't available. On Android, the vibration length follows the strength setting.

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

## YouTube (optional, has ads)
YouTube is **off by default** because its official player can show ads, and the app doesn't block or hide them. To turn it on, go to **Settings → YouTube (Has Ads) → On**. A **YouTube (Has Ads)** entry then appears on the main menu.
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
- YTMP3 link validation, authorization gating, and local import persistence

Tests do not convert or download third-party media. Real haptics, iOS background audio, and lock-screen behavior require a physical iPhone.

## Maintenance
`apply_patch.py` applies the haptic bridge change to an older `index.html`. It's idempotent, and safe to rerun on the current file.
