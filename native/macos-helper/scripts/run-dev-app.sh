#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PACKAGE_DIR/.build/arm64-apple-macosx/debug"
APP_DIR="$BUILD_DIR/GlanceHelper.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
EXECUTABLE="$MACOS_DIR/GlanceHelper"

swift build --package-path "$PACKAGE_DIR" --product GlanceHelper

mkdir -p "$MACOS_DIR"
cp "$BUILD_DIR/GlanceHelper" "$EXECUTABLE"
chmod +x "$EXECUTABLE"

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>GlanceHelper</string>
  <key>CFBundleIdentifier</key>
  <string>dev.glance.GlanceHelper</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>GlanceHelper</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSCameraUsageDescription</key>
  <string>Glance uses the camera through the Python Core for local eye tracking.</string>
  <key>NSInputMonitoringUsageDescription</key>
  <string>Glance uses Space and Esc globally for click and pause controls.</string>
</dict>
</plist>
PLIST

if command -v codesign >/dev/null 2>&1; then
  codesign --force --sign - "$APP_DIR" >/dev/null 2>&1 || true
fi

exec "$EXECUTABLE"
