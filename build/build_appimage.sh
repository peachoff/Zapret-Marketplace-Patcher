#!/bin/bash
set -euo pipefail

APP_NAME="ZMP"
VERSION="${1:-dev}"
DIST_DIR="$(pwd)/../dist"
BUILD_DIR="$(pwd)/../dist"

# AppImage directory structure
APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller output
cp -r "${BUILD_DIR}/${APP_NAME}/"* "${APPDIR}/usr/bin/"
chmod +x "${APPDIR}/usr/bin/${APP_NAME}"

# Find the actual executable name
EXE_NAME=$(find "${APPDIR}/usr/bin" -maxdepth 1 -type f -executable | head -1)
if [ -z "$EXE_NAME" ]; then
    EXE_NAME="${APPDIR}/usr/bin/ZMP"
fi
mv "$EXE_NAME" "${APPDIR}/usr/bin/${APP_NAME}"

# Desktop entry
cat > "${APPDIR}/${APP_NAME}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=ZMP
Comment=Zapret Marketplace Patcher
Exec=ZMP
Icon=ZMP
Categories=Utility;
Terminal=false
EOF

cp "${APPDIR}/${APP_NAME}.desktop" "${APPDIR}/usr/share/applications/${APP_NAME}.desktop"

# Icon
cp "$(pwd)/../src/zmp/icon.ico" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/ZMP.png" 2>/dev/null || true

# Download appimagetool if not present
APPIMAGETOOL="$(pwd)/appimagetool"
if [ ! -f "$APPIMAGETOOL" ]; then
    curl -fsSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# Build AppImage
OUTPUT="${DIST_DIR}/${APP_NAME}-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$APPIMAGETOOL" "${APPDIR}" "${OUTPUT}" --no-appstream 2>/dev/null || \
    APPIMAGETOOL_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "${APPDIR}" "${OUTPUT}" --no-appstream

echo "AppImage created: ${OUTPUT}"
