# iPod

An iPod Classic–style music player: click wheel, clicker, haptics, menus. There are two ways to run it:

| | Web (Safari / Home Screen) | Native iOS wrapper (`ios/`) |
|---|---|---|
| Ad-free local music | ✅ | ✅ |
| Ad-free streaming (Audius) — the default | ✅ | ✅ |
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

## Audius (Ad-Free) — default streaming source
Main menu → **Audius (Ad-Free)**:
- **Trending**: this week's top tracks.
- **Genres**: trending by genre.
- **Top Playlists**.
- **Search Songs** and **Search Playlists**.
- **Saved**: songs and playlists you save.
- **Recently Played**.
- **Save Now Playing** appears while an Audius track is playing.

How it works:
- [Audius](https://audius.co) is a free streaming service where artists upload their own music and choose to make it streamable.
- The app uses Audius's public read-only REST API (`https://api.audius.co/v1`), which needs no key, and identifies itself with `app_name=iPodClassicWeb`.
- Tracks stream as plain audio through the same `<audio>` player as local files. There are **no ads to block**: Audius doesn't insert ads into API streams.
- The wheel, Now Playing, scrubbing, volume, shuffle, repeat and lock-screen controls work exactly as they do for local music.
- Artist names stay on screen, and Now Playing credits Audius, as Audius's API guidelines ask.

**Catalog limitations:**
- **Mostly independent and emerging artists.** Electronic, hip-hop, lo-fi and similar genres are strong. Most major-label releases and mainstream hits are **not** on Audius, so many popular songs won't be found.
- **Free-to-stream tracks only.** Tracks that need a purchase, a follow or a tip (gated), or that are unlisted or deleted, are hidden. A playlist may show fewer songs than it has on audius.co.
- **The catalog changes constantly.** Artists can remove or gate tracks at any time. If a track fails to stream, the player shows "Unavailable — skipping…" and moves on.
- **Rate limits.** Unauthenticated requests share Audius's public limits. A free Audius API key raises them (not wired in yet).
- **No personal account.** Saved and Recently Played live in this browser only. There's no Audius login, so your audius.co favorites and playlists aren't synced.
- **Needs a connection.** Streams don't download for offline play. Use Ad-Free Local Music for offline listening.

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
- Audius, against a local stand-in for its API (same JSON shape, real MP3 streams): trending with paging, gated tracks hidden, playback with artwork and lock-screen info, auto-advance, next and previous, broken streams skipped, song and playlist search, saving, Recently Played, genres, and YouTube staying hidden by default

They don't call the live Audius service (this test environment can't reach it), so check the live catalog on a device. They also can't verify real Taptic output, iOS background audio, the lock screen, or anything in the Swift code. Those need a physical iPhone; see the checklist in the pull request.

## Maintenance
`apply_patch.py` applies the haptic bridge change to an older `index.html`. It's idempotent, and safe to rerun on the current file.
