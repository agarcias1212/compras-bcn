"""Dia (dia.es). Verificado en el navegador el 13-11-2026.

- Búsqueda (JSON): https://www.dia.es/api/v1/search-back/search/reduced?q=...&page=1
  Cada resultado trae object_id, display_name, url y prices{price, price_per_unit, measure_unit}.
  measure_unit: LITRO, KILO, DOCENA, UNIDAD, LAVADO.
- No hay API por ID: un producto fijado se busca por su código (q=<object_id>) y se localiza en los resultados.
- Usa por defecto el código postal 28041; Dia suele tener el mismo precio en toda España.
"""
from urllib.parse import quote

from comun import get_json, a_float, describe_error, elegir, redondea, conteo

BASE = "https://www.dia.es"
BUSCAR = BASE + "/api/v1/search-back/search/reduced?q={q}&page=1"
CONVERSION = {("LITRO", "L"): 1, ("KILO", "kg"): 1, ("DOCENA", "docena"): 1, ("UNIDAD", "docena"): 12}


def ficha(item, unidad):
    pr = item.get("prices") or {}
    precio = a_float(pr.get("price"))
    medida = (pr.get("measure_unit") or "").upper()
    ref = None
    if unidad in ("ud", "lavado"):
        n = conteo(item.get("display_name"), unidad)
        ref = precio / n if (n and precio) else None
    else:
        factor = CONVERSION.get((medida, unidad))
        base = a_float(pr.get("price_per_unit"))
        ref = base * factor if (factor and base is not None) else None
    return {
        "product_id": str(item.get("object_id")),
        "name": item.get("display_name"),
        "packaging": None,
        "price": precio,
        "ref_price": redondea(ref, unidad),
        "ref_unit": unidad if ref is not None else medida,
        "url": BASE + item["url"] if item.get("url") else None,
    }


def buscar(texto):
    return get_json(BUSCAR.format(q=quote(texto))).get("search_items") or []


def emparejar(productos, rebuscar=False):
    resultados, informe = {}, {}
    for prod in productos:
        unidad = prod["unit"]
        query = prod.get("queries", {}).get("dia")
        fijado = prod.get("pinned", {}).get("dia")
        if not query and not fijado:
            resultados[prod["id"]] = None
            informe[prod["id"]] = {"modo": "sin_consulta", "candidatos": []}
            continue
        if fijado and not rebuscar:
            try:
                item = next((x for x in buscar(fijado) if str(x.get("object_id")) == str(fijado)), None)
            except Exception as e:
                item = None
                print(f"  Aviso: {prod['name']}: {describe_error(e)}")
            if item:
                f = ficha(item, unidad)
                resultados[prod["id"]] = f
                informe[prod["id"]] = {"modo": "fijado", "candidatos": [f]}
                continue
            print(f"  Aviso: {prod['name']}: el producto {fijado} ya no aparece; lo busco de nuevo.")
        try:
            texto = " ".join(t for t in query.split() if not t.startswith("-"))
            elegido, candidatos = elegir(query, [ficha(x, unidad) for x in buscar(texto)], unidad)
        except Exception as e:
            print(f"  Aviso: {prod['name']}: búsqueda fallida ({describe_error(e)}).")
            elegido, candidatos = None, []
        resultados[prod["id"]] = elegido
        informe[prod["id"]] = {
            "modo": "busqueda", "query": query, "candidatos": candidatos,
            "elegido": elegido["product_id"] if elegido else None,
            "nuevo_pin": elegido["product_id"] if elegido and elegido["product_id"] != fijado else None,
        }
    return resultados, informe
