"""Bonpreu Esclat (plataforma Ocado). Verificado desde la Mac el 12-11-2026.

- Producto por ID: GET /api/webproductpagews/v5/products/bop?retailerProductId={id}  (JSON)
- Búsqueda: GET /search?q=...  (HTML con window.__INITIAL_STATE__; ~30 productos)
"""
import http.cookiejar
import json
import time
import urllib.request
from urllib.parse import quote

from comun import UA, get_json, get_text, a_float, describe_error, elegir, redondea, conteo

BASE = "https://www.compraonline.bonpreuesclat.cat"
PRODUCTO = BASE + "/api/webproductpagews/v5/products/bop?retailerProductId={id}"
BUSCAR = BASE + "/search?q={q}"
FICHA_WEB = BASE + "/products/x/{id}"   # redirige a la ficha correcta

# etiqueta de precio unitario -> (unidad nuestra, factor)
CONVERSION = {
    ("fop.price.per.litre", "L"): 1,
    ("fop.price.per.kg", "kg"): 1,
    ("fop.price.per.dozen", "docena"): 1,
    ("fop.price.per.item", "docena"): 12,
    ("fop.price.per.unit", "docena"): 12,
}


def _ficha(pid, nombre, precio, ref, etiqueta, unidad):
    precio = a_float(precio)
    if unidad in ("ud", "lavado", "m"):
        # Bonpreu redondea el precio por unidad a 2 decimales (0,01 €/servilleta) o lo da por litro
        # (detergente): se calcula con el número de unidades o dosis del nombre.
        n = conteo(nombre, unidad)
        factor, ref = (1, precio / n) if (n and precio) else (None, None)
    else:
        factor = CONVERSION.get((etiqueta, unidad))
        ref = a_float(ref)
    return {
        "product_id": str(pid),
        "name": nombre,
        "packaging": None,
        "price": precio,
        "ref_price": redondea(ref * factor, unidad) if (ref is not None and factor) else None,
        "ref_unit": unidad if factor else etiqueta,
        "url": FICHA_WEB.format(id=pid),
    }


PAUSA = 8          # segundos entre peticiones: Bonpreu bloquea un rato a quien hace muchas seguidas
ESPERA_BLOQUEO = 90  # si nos bloquea (error HTTP o búsqueda vacía), se espera esto y se reintenta una vez

# Sesión con cookies, como un navegador, para todas las peticiones a Bonpreu.
_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_sesion_iniciada = False
MAX_PETICIONES = 3      # Bonpreu bloquea a partir de ~4 peticiones seguidas: 3 por ejecución, en rotación
_peticiones = 0
FALLOS_PARA_PARAR = 3   # tras 3 fallos seguidos se da Bonpreu por bloqueado en esta ejecución
_fallos_seguidos = 0
bloqueado = False


class Bloqueado(Exception):
    pass


class SinRespuesta(Exception):
    pass


class Agotado(Exception):
    """Se alcanzó MAX_PETICIONES en esta ejecución."""


def _pedir(url, accept):
    global _sesion_iniciada, _peticiones
    if _peticiones >= MAX_PETICIONES:
        raise Agotado()
    _peticiones += 1
    cab = {"User-Agent": UA, "Accept": accept, "Accept-Language": "ca-ES,ca;q=0.9,es;q=0.8"}
    try:
        with _opener.open(urllib.request.Request(url, headers=cab), timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    finally:
        time.sleep(PAUSA)


def _intento(funcion):
    try:
        r = funcion()
        return r, (None if r else "respuesta vacía")
    except Agotado:
        raise
    except Exception as e:
        return None, describe_error(e)


def _con_reintento(funcion, descripcion):
    """Ejecuta funcion(). Si falla, espera ESPERA_BLOQUEO y reintenta una vez (solo la primera vez
    que falla en la ejecución). Tras FALLOS_PARA_PARAR fallos seguidos, lanza Bloqueado."""
    global _fallos_seguidos, bloqueado
    if bloqueado:
        raise Bloqueado()
    r, motivo = _intento(funcion)
    if r:
        _fallos_seguidos = 0
        return r
    _fallos_seguidos += 1
    print(f"  {descripcion}: {motivo}.", flush=True)
    if _fallos_seguidos >= 1:
        bloqueado = True
        print("  Bonpreu no responde: se deja para otra ejecución y se conservan sus últimos precios.", flush=True)
        raise Bloqueado()
    return r


def leer_por_id(pid, unidad):
    try:
        txt = _con_reintento(lambda: _pedir(PRODUCTO.format(id=pid), "application/json"), f"ID {pid}")
        p = json.loads(txt)["product"]
        up = p.get("unitPrice") or {}
        f = _ficha(p["retailerProductId"], p.get("name"), (p.get("price") or {}).get("amount"),
                   (up.get("price") or {}).get("amount"), up.get("unit"), unidad)
        f["packaging"] = p.get("packSizeDescription")
        return f, None
    except (Bloqueado, Agotado):
        raise
    except Exception as e:
        return None, describe_error(e)


def _entidades(texto):
    html = _pedir(BUSCAR.format(q=quote(texto)), "text/html")
    i = html.find("window.__INITIAL_STATE__=")
    if i < 0:
        return []
    resto = html[i + 25:]
    estado = json.loads(resto[:resto.index("</script>")].strip().rstrip(";"))
    return list((estado.get("data", {}).get("products", {}).get("productEntities") or {}).values())


def buscar(query, unidad):
    texto = " ".join(t for t in query.split() if not t.startswith("-"))
    entidades = _con_reintento(lambda: _entidades(texto), f"búsqueda '{texto}'")
    if not entidades:
        # Una búsqueda vacía en Bonpreu casi siempre es el límite de peticiones, no que no exista.
        raise SinRespuesta(texto)
    fichas = []
    for p in entidades:
        pr = p.get("price") or {}
        un = pr.get("unit") or {}
        fichas.append(_ficha(p["retailerProductId"], p.get("name"), (pr.get("current") or {}).get("amount"),
                             (un.get("current") or {}).get("amount"), un.get("label"), unidad))
    return fichas


def _antiguedad(prod, previos):
    """Clave de orden: primero sin precio (fijados antes que por buscar), luego el precio más antiguo."""
    entrada = ((previos or {}).get("products", {}).get(prod["id"]) or {}).get("stores", {}).get("bonpreu")
    if not entrada:
        return (0, 0 if prod.get("pinned", {}).get("bonpreu") else 1, "")
    return (1, 0, entrada.get("fetched") or "")


def emparejar(productos, rebuscar=False, previos=None):
    """Consulta como mucho MAX_PETICIONES productos, empezando por los más desactualizados.
    Los demás quedan 'omitido' y actualizar.py conserva su precio anterior."""
    resultados, informe = {}, {}
    for prod in productos:
        informe[prod["id"]] = {"modo": "omitido", "candidatos": []}
    for prod in sorted(productos, key=lambda p: _antiguedad(p, previos)):
        if bloqueado or _peticiones >= MAX_PETICIONES:
            break
        try:
            _emparejar_uno(prod, rebuscar, resultados, informe)
        except (Bloqueado, Agotado):
            informe[prod["id"]] = {"modo": "omitido", "candidatos": []}
            break
    hechos = sum(1 for i in informe.values() if i["modo"] != "omitido")
    print(f"  Bonpreu: {hechos} producto(s) consultado(s) en esta ejecución (máximo {MAX_PETICIONES}, en rotación).", flush=True)
    return resultados, informe


def _emparejar_uno(prod, rebuscar, resultados, informe):
    if True:
        unidad = prod["unit"]
        query = prod.get("queries", {}).get("bonpreu")
        fijado = prod.get("pinned", {}).get("bonpreu")
        if not query and not fijado:
            resultados[prod["id"]] = None
            informe[prod["id"]] = {"modo": "sin_consulta", "candidatos": []}
            return
        if fijado and not rebuscar:
            f, error = leer_por_id(fijado, unidad)
            if f:
                resultados[prod["id"]] = f
                informe[prod["id"]] = {"modo": "fijado", "candidatos": [f]}
                return
            print(f"  Aviso: {prod['name']}: el ID {fijado} no respondió ({error}); se conserva el precio anterior.")
            informe[prod["id"]] = {"modo": "omitido", "candidatos": []}
            return
        try:
            elegido, candidatos = elegir(query, buscar(query, unidad), unidad)
        except (Bloqueado, Agotado):
            raise
        except SinRespuesta:
            print(f"  {prod['name']}: Bonpreu no devolvió resultados; se conserva el precio anterior.", flush=True)
            informe[prod["id"]] = {"modo": "omitido", "candidatos": []}
            return
        except Exception as e:
            print(f"  Aviso: {prod['name']}: búsqueda fallida ({describe_error(e)}).")
            elegido, candidatos = None, []
        resultados[prod["id"]] = elegido
        informe[prod["id"]] = {
            "modo": "busqueda", "query": query, "candidatos": candidatos,
            "elegido": elegido["product_id"] if elegido else None,
            "nuevo_pin": elegido["product_id"] if elegido and elegido["product_id"] != fijado else None,
        }
