# iPod

An iPod Classic–style music player for the web: click wheel, clicker, haptics, menus. It plays your own music files and controls YouTube through YouTube's official embedded player.

## Install on iPhone
1. Open the site in **Safari**.
2. Tap **Share → Add to Home Screen**.
3. Launch it from the home screen. It opens full screen like an app.

## Controls
- **Spin the wheel** to scroll. In Now Playing, spinning changes the volume.
- **Center button** selects. In Now Playing it switches to scrubbing.
- **MENU** goes back. **⏮ / ⏭** change tracks. **⏯** plays and pauses.

## YouTube
- **Paste Link** takes any YouTube or YouTube Music video or playlist link. It needs no setup.
- **Search** needs a free YouTube Data API key:
  1. Go to https://console.cloud.google.com/ and create a project.
  2. Under **APIs & Services → Library**, enable **YouTube Data API v3**.
  3. Under **APIs & Services → Credentials**, create an **API key**.
  4. Restrict the key: under Application restrictions, choose **Websites** and add `https://yartproductions.github.io/*`. Under API restrictions, choose **YouTube Data API v3**.
  5. On the iPod, go to **YouTube → YouTube Key** and paste the key.

The free quota allows about 100 searches a day.

## Notes
- YouTube's rules require the video to stay visible while it plays. It pauses when you go back to the menus and resumes when you return to Now Playing.
- Background playback and lock-screen playback of YouTube aren't possible on the web.
- On iPhone, haptics need iOS 18 or newer.
