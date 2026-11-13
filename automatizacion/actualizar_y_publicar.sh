#!/bin/bash
# Actualiza los precios y los publica en GitHub. Lo ejecuta launchd cada semana
# (ver instalar.sh), pero también se puede lanzar a mano.
set -u
CARPETA="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$CARPETA/logs"
LOG="$CARPETA/logs/actualizacion.log"
exec >>"$LOG" 2>&1

avisar() {  # notificación en la Mac
  /usr/bin/osascript -e "display notification \"$1\" with title \"Compras BCN\"" >/dev/null 2>&1 || true
}

echo
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
cd "$CARPETA" || { avisar "No se pudo abrir la carpeta del proyecto"; exit 1; }

# Traer cambios de GitHub por si se editó algo desde otro sitio
git pull --rebase --autostash --quiet || echo "Aviso: git pull falló; se continúa."

if ! python3 scraper/actualizar.py; then
  avisar "Falló la actualización de precios. Revisa logs/actualizacion.log"
  exit 1
fi

python3 scraper/imagenes.py || echo "Aviso: fallo al descargar fotos; se continúa."

git add -A
if git diff --cached --quiet; then
  echo "Sin cambios que publicar."
  avisar "Precios revisados: sin cambios."
  exit 0
fi

git commit -m "Precios $(date '+%d-%m-%Y')" --quiet
if git push --quiet; then
  echo "Publicado en GitHub."
  avisar "Precios actualizados y publicados."
else
  echo "ERROR: git push falló."
  avisar "Precios actualizados, pero no se pudieron subir a GitHub. Revisa logs/actualizacion.log"
  exit 1
fi
