"""Mercadona: APIs JSON de tienda.mercadona.es (no oficiales).

Flujo:
1. Producto con ID fijado ('pinned') -> se lee directo por ID. Es lo normal y es rápido.
2. Producto sin fijar (recién añadido) -> se busca, se elige el más barato por kg/L/docena
   y actualizar.py guarda su ID en products.json para las siguientes veces.

Endpoints (verificados el 12-11-2026, código postal 08012 = almacén bcn1):
- Producto: https://tienda.mercadona.es/api/products/{id}/?lang=es&wh=bcn1
- Buscador: https://tornillos.mercadona.es/search?q=...&lang=es&wh=bcn1
  (funciona en el navegador, pero puede rechazar scripts; si falla se usa el catálogo)
- Catálogo: https://tienda.mercadona.es/api/categories/ (recorre ~150 páginas, 1-2 min)
"""
from urllib.parse import quote

from comun import get_json, puntuacion, a_float, describe_error, redondea, conteo, al_inicio

WH = "bcn1"
API = "https://tienda.mercadona.es/api"
PRODUCTO = API + "/products/{id}/?lang=es&wh=" + WH
BUSCAR = "https://tornillos.mercadona.es/search?q={q}&lang=es&wh=" + WH
CABECERAS = {"Origin": "https://tienda.mercadona.es", "Referer": "https://tienda.mercadona.es/"}

CONVERSION = {
    ("l", "L"): 1,
    ("kg", "kg"): 1,
    ("dc", "docena"): 1, ("dz", "docena"): 1, ("docena", "docena"): 1,
    ("ud", "docena"): 12,
    ("100 g", "kg"): 10, ("100g", "kg"): 10, ("100 ml", "L"): 10, ("100ml", "L"): 10,
    ("ud", "ud"): 1,
    ("lv", "lavado"): 1,
    ("m", "m"): 1,
}

_catalogo = None      # caché del catálogo completo (solo si hace falta)
_buscador_ok = True   # se apaga tras el primer fallo para no insistir


def ficha(p, unidad):
    pi = p.get("price_instructions") or {}
    fmt = pi.get("reference_format") or ""
    factor = CONVERSION.get((fmt.lower(), unidad))
    ref = a_float(pi.get("reference_price"))
    if not factor and unidad in ("ud", "lavado", "m"):
        n = conteo(p.get("display_name"), unidad) or conteo(p.get("packaging"), unidad)
        precio = a_float(pi.get("unit_price"))
        if n and precio:
            ref, factor = precio / n, 1
    return {
        "product_id": str(p["id"]),
        "name": p.get("display_name"),
        "packaging": p.get("packaging"),
        "price": a_float(pi.get("unit_price")),
        "ref_price": redondea(ref * factor, unidad) if (ref is not None and factor) else None,
        "ref_unit": unidad if factor else fmt,
        "url": p.get("share_url"),
    }


def catalogo():
    global _catalogo
    if _catalogo is None:
        print("  Recorriendo el catálogo completo (1-2 min)...", flush=True)
        raiz = get_json(f"{API}/categories/?lang=es&wh={WH}")
        productos = {}
        for cat in raiz.get("results", []):
            for sub in cat.get("categories", []):
                datos = get_json(f"{API}/categories/{sub['id']}/?lang=es&wh={WH}")
                for hoja in datos.get("categories", []):
                    for p in hoja.get("products", []):
                        productos[str(p["id"])] = p
        _catalogo = list(productos.values())
        print(f"  {len(_catalogo)} productos en el catálogo", flush=True)
    return _catalogo


def buscar(query):
    """Candidatos para una consulta: buscador si responde; si no, catálogo."""
    global _buscador_ok
    if _buscador_ok:
        texto = " ".join(t for t in query.split() if not t.startswith("-"))
        try:
            return get_json(BUSCAR.format(q=quote(texto)), cabeceras=CABECERAS).get("hits", [])
        except Exception as e:
            _buscador_ok = False
            print(f"  Aviso: el buscador no responde a scripts ({describe_error(e)}); uso el catálogo.", flush=True)
    return catalogo()


def leer_por_id(pid, unidad):
    try:
        return ficha(get_json(PRODUCTO.format(id=pid)), unidad), None
    except Exception as e:
        return None, describe_error(e)


def elegir(prod, query):
    unidad = prod["unit"]
    puntuados = [(puntuacion(query, h.get("display_name", "")), h) for h in buscar(query)]
    puntuados = [(s, ficha(h, unidad)) for s, h in puntuados if s > 0]
    completos = sorted(
        (f for s, f in puntuados if s == 1.0 and f["ref_unit"] == unidad and f["ref_price"] is not None
         and al_inicio(query, f["name"] or "")),
        key=lambda f: (f["ref_price"], f["price"] or 0),
    )
    elegido = completos[0] if completos else None
    candidatos = completos[:5] if completos else [f for s, f in sorted(puntuados, key=lambda x: -x[0])[:5]]
    return elegido, candidatos


def emparejar(productos, rebuscar=False):
    """Devuelve (resultados, informe). informe[id]['nuevo_pin'] indica un ID a guardar."""
    resultados, informe = {}, {}
    for prod in productos:
        unidad = prod["unit"]
        query = prod.get("queries", {}).get("mercadona", prod["name"])
        fijado = prod.get("pinned", {}).get("mercadona")
        if fijado and not rebuscar:
            f, error = leer_por_id(fijado, unidad)
            if f:
                resultados[prod["id"]] = f
                informe[prod["id"]] = {"modo": "fijado", "candidatos": [f]}
                continue
            print(f"  Aviso: {prod['name']}: el ID {fijado} ya no responde ({error}); lo busco de nuevo.")
        try:
            elegido, candidatos = elegir(prod, query)
        except Exception as e:
            print(f"  Aviso: {prod['name']}: {describe_error(e)}; se conserva el precio anterior.")
            informe[prod["id"]] = {"modo": "omitido", "candidatos": []}
            continue
        resultados[prod["id"]] = elegido
        informe[prod["id"]] = {
            "modo": "busqueda", "query": query, "candidatos": candidatos,
            "elegido": elegido["product_id"] if elegido else None,
            "nuevo_pin": elegido["product_id"] if elegido and elegido["product_id"] != fijado else None,
        }
    return resultados, informe
