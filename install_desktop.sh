#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"

echo "=== Instalando SubtitlesOnScreen en Ubuntu ==="

# 1. Ensure directories exist
mkdir -p ~/.local/share/applications
mkdir -p ~/.local/share/icons/hicolor/256x256/apps
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
mkdir -p ~/.local/bin

# 2. Copy icons
cp "$APP_DIR/assets/icon.png" ~/.local/share/icons/hicolor/256x256/apps/subtitlesonscreen.png
cp "$APP_DIR/assets/icon.svg" ~/.local/share/icons/hicolor/scalable/apps/subtitlesonscreen.svg
echo "✔ Iconos instalados en ~/.local/share/icons"

# 3. Create CLI launcher script
cat << EOF > ~/.local/bin/subtitlesonscreen
#!/usr/bin/env bash
exec /usr/bin/python3 "$APP_DIR/main.py" "\$@"
EOF
chmod +x ~/.local/bin/subtitlesonscreen
echo "✔ Comando 'subtitlesonscreen' instalado en ~/.local/bin"

# 4. Create desktop entry with correct absolute paths
cat << EOF > ~/.local/share/applications/subtitlesonscreen.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Subtitles on Screen
GenericName=Subtitle Overlay Player
Comment=Muestra subtítulos flotantes sobre cualquier ventana en pantalla con modo Click-Through
Exec=/usr/bin/python3 $APP_DIR/main.py %f
Icon=subtitlesonscreen
Terminal=false
Categories=AudioVideo;Player;Utility;
MimeType=application/x-subrip;text/vtt;text/x-ssa;text/x-ass;
Keywords=subtitles;overlay;captions;srt;vtt;video;transcription;
StartupNotify=true
StartupWMClass=subtitlesonscreen
EOF
chmod +x ~/.local/share/applications/subtitlesonscreen.desktop
echo "✔ Acceso directo de escritorio instalado en ~/.local/share/applications"

# 5. Update desktop database if available
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database ~/.local/share/applications || true
fi

echo "=================================================="
echo "¡Instalación completada con éxito!"
echo "Ahora puedes:"
echo "  1. Buscar 'Subtitles on Screen' en el menú de aplicaciones de Ubuntu."
echo "  2. Ejecutar desde cualquier terminal: subtitlesonscreen"
echo "  3. O ejecutar directamente: python3 $APP_DIR/main.py"
echo "=================================================="
