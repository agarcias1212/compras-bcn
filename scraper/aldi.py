"""Aldi (precios nacionales, Península). Verificado desde la Mac el 12-11-2026.

No hay buscador ni precio en la ficha de producto. Cada subcategoría
(https://www.aldi.es/productos/<cat>/<subcat>.html) trae en __NEXT_DATA__
todos sus productos con precio. Una petición por subcategoría.

Consulta en products.json:  "aldi": "despensa/arroz: arroz redondo -tarrina"
ID fijado:                   "aldi": "despensa/arroz/768700"

Aldi no publica en la web el precio de muchos frescos (carne de peso
variable, huevos...): esos productos quedan "sin precio en la web".
"""
import json
import re

from comun import get_text, a_float, describe_error, elegir, redondea, conteo

BASE = "https://www.aldi.es"
SUBCAT = BASE + "/productos/{sub}.html"
FICHA_WEB = BASE + "/producto/{slug}.html"

_cache = {}


def productos_de(sub):
    """Lista de productos (dicts de Algolia) de una subcategoría, con caché por ejecución."""
    if sub not in _cache:
        html = get_text(SUBCAT.format(sub=sub))
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        hits = {}

        def recorrer(o):
            if isinstance(o, dict):
                if isinstance(o.get("hits"), list):
                    for h in o["hits"]:
                        if isinstance(h, dict) and h.get("name") and h.get("objectID"):
                            hits[str(h["objectID"])] = h
                for v in o.values():
                    recorrer(v)
            elif isinstance(o, list):
                for v in o:
                    recorrer(v)

        if m:
            recorrer(json.loads(m.group(1)))
        _cache[sub] = list(hits.values())
    return _cache[sub]


_CANT = re.compile(r"(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l)\b", re.I)
_A_BASE = {"kg": ("kg", 1), "g": ("kg", 0.001), "l": ("L", 1), "ml": ("L", 0.001), "cl": ("L", 0.01)}


def cantidad(sales_unit):
    """'1 kg unidad' -> (1.0, 'kg'); 'pack de 2 x 125 g' -> (0.25, 'kg'); '6 x 1 l' -> (6.0, 'L')."""
    m = _CANT.search(sales_unit or "")
    if not m:
        return None, None
    n = int(m.group(1) or 1)
    valor = float(m.group(2).replace(",", "."))
    base, factor = _A_BASE[m.group(3).lower()]
    return n * valor * factor, base


def ficha(h, unidad):
    cp = h.get("currentPrice") or {}
    precio = a_float(cp.get("priceValue"))
    ref = None
    for b in cp.get("basePrice") or []:
        escala = (b.get("basePriceScale") or "").lower()
        if (escala, unidad) in (("kg", "kg"), ("l", "L")):
            ref = a_float(b.get("basePriceValue"))
    if precio is not None and unidad in ("ud", "lavado", "m"):
        n = conteo(h.get("salesUnit"), unidad) or conteo(h.get("name"), unidad)
        ref = precio / n if n else None
    if ref is None and precio is not None and unidad in ("kg", "L"):
        cant, base = cantidad(h.get("salesUnit"))
        if cant and base == unidad:
            ref = precio / cant
    slug = h.get("productSlug")
    return {
        "product_id": str(h["objectID"]),
        "name": h.get("name"),
        "packaging": h.get("salesUnit"),
        "price": precio,
        "ref_price": redondea(ref, unidad),
        "ref_unit": unidad,
        "url": FICHA_WEB.format(slug=slug) if slug else None,
    }


def emparejar(productos, rebuscar=False):
    resultados, informe = {}, {}
    for prod in productos:
        unidad = prod["unit"]
        consulta = prod.get("queries", {}).get("aldi")
        fijado = prod.get("pinned", {}).get("aldi")
        if not consulta and not fijado:
            resultados[prod["id"]] = None
            informe[prod["id"]] = {"modo": "sin_consulta", "candidatos": []}
            continue
        if fijado and not rebuscar:
            sub, _, oid = fijado.rpartition("/")
            try:
                h = next((x for x in productos_de(sub) if str(x["objectID"]) == oid), None)
            except Exception as e:
                h = None
                print(f"  Aviso: {prod['name']}: no pude leer {sub} ({describe_error(e)}).")
            f = ficha(h, unidad) if h else None
            if f and f["ref_price"] is not None:
                resultados[prod["id"]] = f
                informe[prod["id"]] = {"modo": "fijado", "candidatos": [f]}
                continue
            print(f"  Aviso: {prod['name']}: el producto {fijado} ya no aparece o no tiene precio; lo busco de nuevo.")
        if not consulta or ":" not in consulta:
            resultados[prod["id"]] = None
            informe[prod["id"]] = {"modo": "busqueda", "query": consulta, "candidatos": [], "elegido": None}
            continue
        sub, query = (x.strip() for x in consulta.split(":", 1))
        try:
            fichas = [ficha(h, unidad) for h in productos_de(sub)]
        except Exception as e:
            print(f"  Aviso: {prod['name']}: no pude leer {sub} ({describe_error(e)}).")
            fichas = []
        elegido, candidatos = elegir(query, fichas, unidad)
        resultados[prod["id"]] = elegido
        pin = f"{sub}/{elegido['product_id']}" if elegido else None
        informe[prod["id"]] = {
            "modo": "busqueda", "query": consulta, "candidatos": candidatos,
            "elegido": elegido["product_id"] if elegido else None,
            "nuevo_pin": pin if pin and pin != fijado else None,
        }
    return resultados, informe
