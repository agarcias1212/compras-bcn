"""Actualiza prices.json a partir de products.json.

Uso (desde la carpeta del proyecto):
    python3 scraper/actualizar.py                 # las tres cadenas
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
import consum  # noqa: E402
import dia  # noqa: E402
import bonpreu  # noqa: E402
import mercadona  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTES = {"mercadona": mercadona, "bonpreu": bonpreu, "aldi": aldi, "dia": dia, "consum": consum}
POR_DEFECTO = ["mercadona", "aldi", "consum", "bonpreu"]   # Dia bloquea scripts (403): se actualiza desde el navegador   # Bonpreu al final: es el más lento


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
            continue   # no consultado en esta ejecución: se conserva el precio anterior
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


def aplicar_manuales(precios, productos, ruta):
    """precios_manuales.json: {"bonpreu": {"azucar": {"nombre": ..., "precio": 0.90, "precio_unidad": 0.90, "fecha": "2026-11-12"}}}
    Se usa el manual si la cadena no tiene precio o si el manual es más reciente."""
    manuales = cargar(ruta, {})
    unidades = {p["id"]: p["unit"] for p in productos}
    aplicados = 0
    for cadena, por_producto in manuales.items():
        if cadena.startswith("_"):
            continue
        for pid, m in (por_producto or {}).items():
            if pid not in unidades or not m or m.get("precio_unidad") is None:
                continue
            entrada = precios["products"].setdefault(pid, {"stores": {}})
            actual = entrada.setdefault("stores", {}).get(cadena)
            fecha = str(m.get("fecha") or "")
            if actual and (actual.get("fetched") or "")[:10] > fecha:
                continue
            entrada["stores"][cadena] = {
                "product_id": None, "name": m.get("nombre"), "packaging": m.get("envase"),
                "price": m.get("precio"), "ref_price": m["precio_unidad"], "ref_unit": unidades[pid],
                "url": None, "fetched": fecha, "manual": True,
            }
            aplicados += 1
    return aplicados


def main(argv):
    rebuscar = "--rebuscar" in argv
    # Bonpreu va despacio (8 s entre peticiones) y, si bloquea, se conservan sus precios anteriores.
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
        if cadena == "bonpreu":
            resultados, informe = fuente.emparejar(productos, rebuscar=rebuscar, previos=precios)
        else:
            resultados, informe = fuente.emparejar(productos, rebuscar=rebuscar)
        for prod in productos:
            entrada = precios["products"].setdefault(prod["id"], {})
            entrada.update({"name": prod["name"], "unit": prod["unit"]})
            if prod["id"] not in resultados and informe.get(prod["id"], {}).get("modo") == "omitido":
                continue   # la cadena no respondió: se conserva el precio anterior (con su fecha)
            r = resultados.get(prod["id"])
            previo = entrada.setdefault("stores", {}).get(cadena) or {}
            nuevo = dict(r, fetched=ahora) if r else None
            if nuevo and previo.get("image") and previo.get("product_id") == nuevo.get("product_id"):
                nuevo["image"] = previo["image"]   # misma ficha: se conserva su foto
            entrada["stores"][cadena] = nuevo
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

    n = aplicar_manuales(precios, productos, RAIZ / "precios_manuales.json")
    if n:
        guardar(RAIZ / "prices.json", precios)
        print(f"Precios manuales aplicados: {n}.")
    if pins_nuevos:
        print(f"\nproducts.json: {pins_nuevos} producto(s) fijado(s) por ID.")
    print(f"prices.json actualizado ({len(precios['products'])} productos).")


if __name__ == "__main__":
    main(sys.argv)
