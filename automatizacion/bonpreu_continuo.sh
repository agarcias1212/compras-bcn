#!/bin/bash
# Rellena Bonpreu poco a poco: cada ciclo consulta 3 productos (su límite).
# La espera entre ciclos se adapta: empieza en 20 min, se duplica si Bonpreu bloquea
# (hasta 120) y se reduce a la mitad cuando responde bien (mínimo 20).
#
# Uso (desde la carpeta del proyecto, con la Mac enchufada):
#   caffeinate -i bash automatizacion/bonpreu_continuo.sh            (20 min, 3 productos)
#   caffeinate -i bash automatizacion/bonpreu_continuo.sh 5 4        (5 min, 4 productos por ciclo)
# Para pararlo: Ctrl+C
set -u
CARPETA="$(cd "$(dirname "$0")/.." && pwd)"
cd "$CARPETA" || exit 1
ESPERA_MIN=${1:-20}; ESPERA_MAX=120;
export BONPREU_MAX=${2:-3}
ESPERA=$ESPERA_MIN
MAX_CICLOS=120

estado() {  # imprime: productos_con_precio total consultados_en_este_ciclo
  python3 - <<'PY'
import json
P = json.load(open("products.json"))["products"]
R = json.load(open("prices.json"))["products"]
con = sum(1 for p in P if ((R.get(p["id"]) or {}).get("stores") or {}).get("bonpreu"))
try:
    inf = json.load(open("informes/bonpreu.json"))
    hechos = sum(1 for v in inf.values() if v.get("modo") not in ("omitido",))
except Exception:
    hechos = 0
print(con, len(P), hechos)
PY
}

for ciclo in $(seq 1 $MAX_CICLOS); do
  echo
  echo "===== Ciclo $ciclo · $(date '+%d/%m %H:%M') ====="
  python3 scraper/actualizar.py bonpreu 2>&1 | grep -vE "^- .*(omitido|se conserva)|^$|^=== bonpreu"
  python3 scraper/imagenes.py 2>&1 | grep -E "^bonpreu" || true
  read -r CON TOTAL HECHOS < <(estado)
  echo "Bonpreu: $CON de $TOTAL productos con precio (este ciclo respondió en $HECHOS)."
  git add -A && git commit -q -m "Bonpreu: $CON/$TOTAL ($(date '+%d-%m %H:%M'))" && git push -q && echo "Publicado." || echo "(sin cambios que publicar)"
  if [ "$CON" -ge "$TOTAL" ]; then echo "Bonpreu completo."; break; fi
  if [ "$HECHOS" -ge 1 ]; then
    ESPERA=$(( ESPERA / 2 )); [ $ESPERA -lt $ESPERA_MIN ] && ESPERA=$ESPERA_MIN
  else
    ESPERA=$(( ESPERA * 2 )); [ $ESPERA -gt $ESPERA_MAX ] && ESPERA=$ESPERA_MAX
    echo "Bonpreu bloqueado: alargo la espera."
  fi
  echo "Siguiente ciclo en $ESPERA min, a las $(date -v+${ESPERA}M '+%H:%M'). Ctrl+C para parar."
  sleep $((ESPERA * 60))
done
