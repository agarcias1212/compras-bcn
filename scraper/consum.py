"""Consum (tienda.consum.es). Verificado en el navegador el 13-11-2026.

- Búsqueda (JSON): /api/rest/V1.0/catalog/product?q=...&limit=40&offset=0&orderById=13&showProducts=true
- Producto por ID (JSON): /api/rest/V1.0/catalog/product/{id}
  priceData.prices[]: {id: PRICE u OFFER_PRICE, value{centAmount, centUnitAmount}}; priceData.unitPriceUnitType: "1 Kg",
  "100 Gr", "1 L", "100 Ml", "1 Dc", "1 U", "1 Lv". productData.description incluye el formato.
"""
import re
from urllib.parse import quote

from comun import get_json, a_float, describe_error, elegir, redondea, conteo

BASE = "https://tienda.consum.es"
BUSCAR = BASE + "/api/rest/V1.0/catalog/product?page=1&limit=40&offset=0&orderById=13&showProducts=true&q={q}"
PRODUCTO = BASE + "/api/rest/V1.0/catalog/product/{id}"

# unidad de Consum -> (unidad nuestra, gramos/mililitros que representa el número)
_UNIDADES = {"kg": ("kg", 1), "gr": ("kg", 0.001), "g": ("kg", 0.001), "l": ("L", 1), "ml": ("L", 0.001),
             "cl": ("L", 0.01), "dc": ("docena", 1)}


def _precio(pd):
    """Precio vigente más bajo (oferta si la hay) y su precio por unidad."""
    mejores = []
    for p in (pd.get("prices") or []):
        v = p.get("value") or {}
        if v.get("centAmount") is not None:
            mejores.append((a_float(v.get("centAmount")), a_float(v.get("centUnitAmount"))))
    return min(mejores) if mejores else (None, None)


def ficha(p, unidad):
    pd = p.get("priceData") or {}
    datos = p.get("productData") or {}
    nombre = datos.get("description") or datos.get("name")
    precio, por_unidad = _precio(pd)
    ref = None
    if unidad in ("ud", "lavado", "m"):
        n = conteo(nombre, unidad)
        ref = precio / n if (n and precio) else None
    else:
        m = re.match(r"\s*([\d.,]+)\s*([A-Za-z]+)", pd.get("unitPriceUnitType") or "")
        if m and por_unidad is not None:
            cantidad = float(m.group(1).replace(",", "."))
            base, factor = _UNIDADES.get(m.group(2).lower(), (None, None))
            if base == unidad:
                ref = por_unidad / (cantidad * factor)
    return {
        "product_id": str(p.get("id")),
        "name": nombre,
        "packaging": None,
        "price": precio,
        "ref_price": redondea(ref, unidad),
        "ref_unit": unidad if ref is not None else pd.get("unitPriceUnitType"),
        "url": datos.get("url"),
    }


def emparejar(productos, rebuscar=False):
    resultados, informe = {}, {}
    for prod in productos:
        unidad = prod["unit"]
        query = prod.get("queries", {}).get("consum")
        fijado = prod.get("pinned", {}).get("consum")
        if not query and not fijado:
            resultados[prod["id"]] = None
            informe[prod["id"]] = {"modo": "sin_consulta", "candidatos": []}
            continue
        if fijado and not rebuscar:
            try:
                f = ficha(get_json(PRODUCTO.format(id=fijado)), unidad)
            except Exception as e:
                f = None
                print(f"  Aviso: {prod['name']}: el ID {fijado} no responde ({describe_error(e)}); lo busco de nuevo.")
            if f and f["ref_price"] is not None:
                resultados[prod["id"]] = f
                informe[prod["id"]] = {"modo": "fijado", "candidatos": [f]}
                continue
        try:
            texto = " ".join(t for t in query.split() if not t.startswith("-"))
            items = get_json(BUSCAR.format(q=quote(texto))).get("products") or []
            elegido, candidatos = elegir(query, [ficha(x, unidad) for x in items], unidad)
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
