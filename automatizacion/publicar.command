#!/bin/bash
# Doble clic en Finder: baja las fotos que falten y publica los cambios en GitHub.
cd "$(dirname "$0")/.." || exit 1
python3 scraper/imagenes.py && git add -A && git commit -m "Actualización $(date '+%d-%m-%Y %H:%M')" && git push && echo && echo "✅ Publicado." || echo "❌ Algo falló: revisa los mensajes de arriba."
echo; read -n 1 -s -r -p "Pulsa una tecla para cerrar."
