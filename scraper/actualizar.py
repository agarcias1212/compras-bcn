"""Actualiza prices.json a partir de products.json.

Uso (desde la carpeta del proyecto):
    python3 scraper/actualizar.py                 # Mercadona y Aldi (Bonpreu, a mano)
    python3 scraper/actualizar.py mercadona       # solo una
    python3 scraper/actualizar.py --rebuscar      # ignora los IDs fijados y vuelve a elegir el más barato

Los productos sin ID fijado se buscan y el ID elegido se guarda en products.json ('pinned').
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import aldi  # noqa: E402
import bonpreu  # noqa: E402
import mercadona  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTES = {"mercadona": mercadona, "bonpreu": bonpreu, "aldi": aldi}
POR_DEFECTO = ["mercadona", "aldi"]


def cargar(ruta, defecto):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else defecto


def guardar(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def linea(c):
    return f"[{c['product_id']}] {c['name']} {c['packaging'] or ''} - {c['price']} € ({c['ref_price']} €/{c['ref_unit']})"


def imprimir_informe(cadena, productos, informe):
    print(f"\n=== {cadena} ===")
    for prod in productos:
        inf = informe[prod["id"]]
        cands = inf["candidatos"]
        if inf["modo"] == "fijado":
            print(f"- {prod['name']}: {linea(cands[0])}")
            continue
        if inf["modo"] == "omitido":
            print(f"- {prod['name']}: omitido (se conserva el precio anterior)")
            continue
        if inf["modo"] == "sin_consulta":
            print(f"- {prod['name']}: sin consulta para esta cadena")
            continue
        if not inf["elegido"]:
            motivo = "candidatos sin precio en la web" if cands else "sin resultados"
            print(f"- {prod['name']} ('{inf['query']}'): SIN PRECIO COMPARABLE ({motivo})")
        else:
            print(f"- {prod['name']} ('{inf['query']}'): elegido y fijado")
        for c in cands:
            print(f"   {'*' if c['product_id'] == inf['elegido'] else ' '} {linea(c)}")


def main(argv):
    rebuscar = "--rebuscar" in argv
    # Bonpreu se deja fuera por defecto: bloquea las peticiones automáticas.
    # Se puede lanzar a mano con: python3 scraper/actualizar.py bonpreu
    elegidas = [a for a in argv[1:] if not a.startswith("--")] or POR_DEFECTO
    ruta_maestra = RAIZ / "products.json"
    maestra = cargar(ruta_maestra, {"products": []})
    productos = maestra["products"]
    precios = cargar(RAIZ / "prices.json", {"products": {}})
    ahora = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    pins_nuevos = 0

    for cadena in elegidas:
        fuente = FUENTES[cadena]
        print(f"Leyendo {cadena}...", flush=True)
        resultados, informe = fuente.emparejar(productos, rebuscar=rebuscar)
        for prod in productos:
            entrada = precios["products"].setdefault(prod["id"], {})
            entrada.update({"name": prod["name"], "unit": prod["unit"]})
            if prod["id"] not in resultados and informe.get(prod["id"], {}).get("modo") == "omitido":
                continue   # la cadena no respondió: se conserva el precio anterior (con su fecha)
            r = resultados.get(prod["id"])
            entrada.setdefault("stores", {})[cadena] = dict(r, fetched=ahora) if r else None
            nuevo = informe[prod["id"]].get("nuevo_pin")
            if nuevo:
                prod.setdefault("pinned", {})[cadena] = nuevo
                pins_nuevos += 1
        guardar(RAIZ / "informes" / f"{cadena}.json", informe)
        imprimir_informe(cadena, productos, informe)
        # Guardar tras cada súper: si se interrumpe, no se pierde lo ya leído.
        if pins_nuevos:
            guardar(ruta_maestra, maestra)
        ids = {p["id"] for p in productos}
        precios["products"] = {k: v for k, v in precios["products"].items() if k in ids}
        precios["updated"] = ahora
        guardar(RAIZ / "prices.json", precios)
        guardar(RAIZ / "historico" / f"{ahora[:10]}.json", precios)
        print(f"  Guardado ({cadena}).", flush=True)

    if pins_nuevos:
        print(f"\nproducts.json: {pins_nuevos} producto(s) fijado(s) por ID.")
    print(f"prices.json actualizado ({len(precios['products'])} productos).")


if __name__ == "__main__":
    main(sys.argv)
