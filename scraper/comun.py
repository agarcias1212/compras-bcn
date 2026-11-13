"""Utilidades compartidas por las fuentes de precios."""
import json
import re
import time
import unicodedata
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
STOPWORDS = {"de", "del", "la", "el", "los", "las", "y", "con", "en", "d", "i"}


def get_text(url, pausa=0.4, reintentos=3, cabeceras=None):
    return _pedir(url, pausa, reintentos, {"Accept": "text/html", **(cabeceras or {})}, json_=False)


def get_json(url, pausa=0.4, reintentos=3, cabeceras=None):
    return _pedir(url, pausa, reintentos, {"Accept": "application/json", **(cabeceras or {})}, json_=True)


def _pedir(url, pausa, reintentos, cabeceras, json_):
    for intento in range(reintentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,ca;q=0.8", **cabeceras})
            with urllib.request.urlopen(req, timeout=30) as r:
                datos = json.load(r) if json_ else r.read().decode("utf-8", "replace")
            time.sleep(pausa)
            return datos
        except Exception as e:
            codigo = getattr(e, "code", None)
            if intento == reintentos - 1 or (codigo and 400 <= codigo < 500 and codigo != 429):
                raise
            time.sleep(2 * (intento + 1))


def describe_error(e):
    codigo = getattr(e, "code", None)
    return f"HTTP {codigo}" if codigo else f"{type(e).__name__}: {e}"


def normaliza(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else " " for c in t)


def singular(w):
    """Plural simple: 'pechugas' -> 'pechuga', 'huevos' -> 'huevo'. Se aplica igual a consulta y nombre."""
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def palabras(texto):
    return [singular(w) for w in normaliza(texto).split() if w not in STOPWORDS]


def puntuacion(query, nombre):
    """Fracción de palabras de la consulta presentes en el nombre (1.0 = todas).

    Las palabras con "-" delante son exclusiones: si aparecen, la puntuación es 0.
    Ej.: "carne picada vacuno -cerdo".
    """
    terminos = query.split()
    excluir = [w for t in terminos if t.startswith("-") for w in palabras(t[1:])]
    incluir = palabras(" ".join(t for t in terminos if not t.startswith("-")))
    n = set(palabras(nombre))
    if any(w in n for w in excluir):
        return 0.0
    return sum(1 for w in incluir if w in n) / len(incluir) if incluir else 0.0


def a_float(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def elegir(query, fichas, unidad):
    """Elige entre fichas {name, ref_price, ref_unit, price, ...}.

    El más barato por unidad de referencia entre los que contienen todas las
    palabras de la consulta (sin las excluidas). Devuelve (elegido, candidatos).
    """
    puntuadas = [(puntuacion(query, f["name"] or ""), f) for f in fichas]
    puntuadas = [(s, f) for s, f in puntuadas if s > 0]
    completas = sorted(
        (f for s, f in puntuadas if s == 1.0 and f["ref_unit"] == unidad and f["ref_price"] is not None),
        key=lambda f: (f["ref_price"], f["price"] or 0),
    )
    if completas:
        return completas[0], completas[:5]
    # sin precio comparable: enseñar las mejores coincidencias para revisar
    return None, [f for s, f in sorted(puntuadas, key=lambda x: -x[0])[:5]]


def redondea(valor, unidad):
    """2 decimales para kg/L/docena; 3 para precios por unidad o lavado (céntimos)."""
    if valor is None:
        return None
    return round(valor, 3 if unidad in ("ud", "lavado") else 2)


_CONTEO = {
    "ud": re.compile(r"(\d+)\s*(?:unidades|unitats|uds?\.?|u)\b", re.I),
    "lavado": re.compile(r"(\d+)\s*(?:lavados|dosis|rentats|renta(?:des)?|lv)\b", re.I),
}


def conteo(texto, unidad):
    """Número de unidades o lavados escrito en un texto ('pack de 100 unidades', 'de 66 dosis')."""
    patron = _CONTEO.get(unidad)
    m = patron.search(texto or "") if patron else None
    return int(m.group(1)) if m else None
