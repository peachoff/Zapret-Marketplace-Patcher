#!/bin/bash
set -euo pipefail

APP_NAME="ZMP"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-$(sed -n 's/^version = "\(.*\)"/v\1/p' "${SCRIPT_DIR}/../pyproject.toml" | head -1)}"
VERSION="${VERSION:-dev}"
DIST_DIR="${SCRIPT_DIR}/../dist"
BUILD_DIR="${SCRIPT_DIR}/../dist"

# AppImage directory structure
APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller output
cp -r "${BUILD_DIR}/${APP_NAME}/"* "${APPDIR}/usr/bin/"
chmod +x "${APPDIR}/usr/bin/${APP_NAME}"

# PyInstaller onedir output is dist/ZMP/ZMP (name matches the spec), so no
# renaming is needed.

# AppImage entry point
cat > "${APPDIR}/AppRun" << EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\$0")")"
export PATH="\${HERE}/usr/bin:\$PATH"
exec "\${HERE}/usr/bin/${APP_NAME}" "\$@"
EOF
chmod +x "${APPDIR}/AppRun"

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

# Icon: appimagetool requires <AppName>.png in the AppDir root.
ICON_SRC="${SCRIPT_DIR}/../src/zmp/icon.png"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "${APPDIR}/${APP_NAME}.png"
    cp "$ICON_SRC" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
else
    echo "WARNING: icon not found at ${ICON_SRC}" >&2
fi

# Download appimagetool if not present
APPIMAGETOOL="${SCRIPT_DIR}/appimagetool"
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
