#!/bin/bash
# Programa la actualización semanal (domingos a las 9:17). Ejecutar una sola vez:
#   bash automatizacion/instalar.sh
# Para quitarla:  bash automatizacion/instalar.sh --quitar
set -e
ETIQUETA="com.compras-bcn.actualizar"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"
CARPETA="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$CARPETA/automatizacion/actualizar_y_publicar.sh"

launchctl bootout "gui/$(id -u)/$ETIQUETA" 2>/dev/null || true
if [ "${1:-}" = "--quitar" ]; then
  rm -f "$PLIST"
  echo "Actualización semanal desactivada."
  exit 0
fi

chmod +x "$SCRIPT"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETIQUETA</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$SCRIPT</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>17</integer></dict>
  <key>StandardOutPath</key><string>$CARPETA/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$CARPETA/logs/launchd.log</string>
</dict>
</plist>
PLIST
mkdir -p "$CARPETA/logs"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Listo: se actualizará cada domingo a las 9:17. Si a esa hora la Mac está dormida, lo hará al despertar; si está apagada, el domingo siguiente."
echo "Para probarlo ahora:  launchctl kickstart gui/$(id -u)/$ETIQUETA"
echo "Registro:             $CARPETA/logs/actualizacion.log"
