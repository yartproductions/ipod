#!/bin/bash
# Double-click in Finder: generates the Xcode project for the iPod wrapper and opens it.
set -euo pipefail
cd "$(dirname "$0")"
echo "▶ iPod — setting up the Xcode project in $(pwd)"

if ! xcode-select -p >/dev/null 2>&1; then
  echo "✖ Xcode command line tools aren't set up. Open Xcode once, accept the license, then run this again."
  read -n 1 -s -r -p "Press any key to close."; exit 1
fi

XG="$(command -v xcodegen || true)"
if [ -z "$XG" ] && command -v brew >/dev/null 2>&1; then
  echo "▶ Installing XcodeGen with Homebrew…"
  brew install xcodegen
  XG="$(command -v xcodegen)"
fi
if [ -z "$XG" ]; then
  echo "▶ Downloading XcodeGen (no Homebrew found)…"
  TMP="$(mktemp -d)"
  curl -fsSL https://github.com/yonaskolb/XcodeGen/releases/latest/download/xcodegen.zip -o "$TMP/xcodegen.zip"
  unzip -q "$TMP/xcodegen.zip" -d "$TMP"
  XG="$(find "$TMP" -type f -name xcodegen -perm -u+x | head -n 1)"
  [ -n "$XG" ] || { echo "✖ Couldn't find the XcodeGen binary in the download."; exit 1; }
fi

echo "▶ Generating IPod.xcodeproj…"
"$XG" generate --spec project.yml
echo "✔ Done. Opening Xcode…"
open IPod.xcodeproj
cat <<'EOF'

Next, in Xcode:
  1. Click "IPod" in the left sidebar → Signing & Capabilities → Team: pick your Apple ID
     (Xcode ▸ Settings ▸ Accounts to add it if it isn't listed).
  2. Plug in your iPhone, unlock it, and choose it from the device menu at the top.
  3. Press ▶ Run. On the iPhone: Settings ▸ Privacy & Security ▸ Developer Mode → On (first time only),
     then Settings ▸ General ▸ VPN & Device Management → trust your developer profile.
EOF
read -n 1 -s -r -p "Press any key to close this window."
