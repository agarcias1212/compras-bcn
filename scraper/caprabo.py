"""Caprabo (www.capraboacasa.com). Verificado en el navegador y desde la Mac el 16-11-2026.

Su robots.txt no permite usar el buscador (/search/results/?q=), pero sí las páginas de
categoría y de producto. Así que, como con Aldi, cada producto se busca dentro de su
categoría (20 productos por página, ?pageNumber=1, 2...).

Consulta en products.json:  "caprabo": "2059806-alimentacion/2059988-aceite-vinagre-sal-harina-y-pan-rallado/2059992-aceite-de-girasol: aceite girasol"
  (varias categorías separadas por " | " antes de los dos puntos)
ID fijado:                   "caprabo": "175703"  (se busca en sus categorías; si no está, en su ficha)

Precio por kg/L/docena: el "1 KILO A 1,99 €" de la tarjeta; si no lo trae (packs de 1 kg o 1 L,
productos al peso), se calcula con la cantidad del nombre ("garrafa 5 litros", "compra mínima 1 kg").
Precio por unidad/rollo/lavado/metro: con el número del nombre ("caja 25 sobres"), más preciso.
"""
import html as _html
import re
import time

from comun import get_text, a_float, describe_error, elegir, redondea, conteo

BASE = "https://www.capraboacasa.com"
CATEGORIA = BASE + "/es/supermercado/{cat}/"
FICHA_WEB = BASE + "/es/productdetail/{id}-p/"
IMAGEN = BASE + "/images/{id}.jpg"
PAUSA = 1.0
MAX_PAGINAS = 6

_cache = {}

_CANT = re.compile(r"(?:(\d+)\s*(?:x|uds?\.?\s*x)\s*)?(\d+(?:[.,]\d+)?)\s*(kg|kilos?|gr?|ml|cl|l|litros?)\b", re.I)
_A_BASE = {"kg": ("kg", 1), "kilo": ("kg", 1), "kilos": ("kg", 1), "g": ("kg", 0.001), "gr": ("kg", 0.001),
           "l": ("L", 1), "litro": ("L", 1), "litros": ("L", 1), "ml": ("L", 0.001), "cl": ("L", 0.01)}
_ETIQUETA = {"KILO": "kg", "LITRO": "L", "DOCENA": "docena", "UNIDAD": "ud", "ROLLO": "ud",
             "LAVADO": "lavado", "DOSIS": "lavado", "METRO": "m"}


def cantidad(nombre):
    """'garrafa 5 litros' -> (5.0, 'L'); 'pack 4x125 g' -> (0.5, 'kg'). La última cantidad del nombre."""
    ms = list(_CANT.finditer(nombre or ""))
    if not ms:
        return None, None
    m = ms[-1]
    n = int(m.group(1) or 1)
    valor = float(m.group(2).replace(",", "."))
    base, factor = _A_BASE[m.group(3).lower()]
    return n * valor * factor, base


def docenas(nombre):
    t = (nombre or "").lower()
    if re.search(r"(1/2|media)\s*docena", t):
        return 0.5
    m = re.search(r"(\d+)\s*docenas?", t)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)\s*(?:uds?|unidades|huevos)\b", t)
    return int(m.group(1)) / 12 if m else None


def _num(s):
    return a_float((s or "").replace(".", "").replace(",", ".")) if s else None


def ficha(pid, nombre, precio, cantidad_txt, unidad):
    """cantidad_txt: '1 KILO A 1,99 €' (o None)."""
    ref = None
    etiqueta = None
    if cantidad_txt:
        m = re.search(r"1\s+([A-ZÁÉÍÓÚ]+)\s+A\s+([\d.,]+)", cantidad_txt.upper())
        if m:
            etiqueta = _ETIQUETA.get(m.group(1))
            if etiqueta == unidad:
                ref = _num(m.group(2))
    if precio is not None:
        if unidad in ("ud", "lavado", "m"):
            n = conteo(nombre, unidad)
            if n:
                ref = precio / n
        elif unidad == "docena" and ref is None:
            d = docenas(nombre)
            if d:
                ref = precio / d
        elif unidad in ("kg", "L") and ref is None:
            cant, base = cantidad(nombre)
            if cant and base == unidad:
                ref = precio / cant
    return {
        "product_id": str(pid),
        "name": nombre,
        "packaging": None,
        "price": precio,
        "ref_price": redondea(ref, unidad),
        "ref_unit": unidad if ref is not None else (etiqueta or None),
        "url": FICHA_WEB.format(id=pid),
        "image_url": IMAGEN.format(id=pid),
    }


def _tarjetas(html):
    """[(id, nombre, precio, cantidad_txt)] de una página de categoría."""
    html = re.sub(r"\s+", " ", html)
    out = []
    for parte in html.split('class="product-title product-title-resp"')[1:]:
        m_id = re.search(r"productdetail/(\d+)-", parte)
        m_nom = re.search(r'product-title-link"[^>]*>([^<]+)<', parte)
        precios = re.findall(r'class="price-offer-now">\s*([\d.,]+)\s*<', parte)
        m_q = re.search(r'class="quantity-text">([^<]+)<', parte)
        if not (m_id and m_nom and precios):
            continue   # sin precio: agotado o no disponible
        out.append((m_id.group(1), _html.unescape(m_nom.group(1)).strip(), _num(precios[0]),
                    m_q.group(1).strip() if m_q else None))
    return out


def productos_de(cat):
    """Todas las tarjetas de una categoría (con sus páginas), con caché por ejecución."""
    cat = cat.strip().strip("/")
    if cat not in _cache:
        todas, vistos = [], set()
        for pagina in range(MAX_PAGINAS):
            url = CATEGORIA.format(cat=cat) + (f"?pageNumber={pagina}" if pagina else "")
            html = get_text(url)
            time.sleep(PAUSA)
            nuevas = [t for t in _tarjetas(html) if t[0] not in vistos]
            todas += nuevas
            vistos.update(t[0] for t in nuevas)
            if not nuevas or f"pageNumber={pagina + 1}" not in html:
                break
        _cache[cat] = todas
    return _cache[cat]


def leer_ficha(pid, unidad):
    html = re.sub(r"\s+", " ", get_text(FICHA_WEB.format(id=pid)))
    time.sleep(PAUSA)
    m_nom = re.search(r'class="description-title">([^<]+)<', html)
    i = html.find('class="description-title"')
    resto = html[i:] if i >= 0 else html
    m_pr = re.search(r'itemprop="price" class="offer-now">\s*([\d.,]+)', resto)
    m_q = re.search(r'class="quantity-text">([^<]+)<', resto)
    if not (m_nom and m_pr):
        return None
    return ficha(pid, _html.unescape(m_nom.group(1)).strip(), _num(m_pr.group(1)),
                 m_q.group(1).strip() if m_q else None, unidad)


def _categorias(consulta):
    cats, _, query = (consulta or "").partition(":")
    return [c.strip() for c in cats.split("|") if c.strip()], query.strip()


def emparejar(productos, rebuscar=False):
    resultados, informe = {}, {}
    for prod in productos:
        unidad = prod["unit"]
        consulta = prod.get("queries", {}).get("caprabo")
        fijado = prod.get("pinned", {}).get("caprabo")
        if not consulta and not fijado:
            resultados[prod["id"]] = None
            informe[prod["id"]] = {"modo": "sin_consulta", "candidatos": []}
            continue
        cats, query = _categorias(consulta)
        try:
            fichas = [ficha(*t, unidad) for c in cats for t in productos_de(c)]
        except Exception as e:
            print(f"  Aviso: {prod['name']}: no pude leer su categoría ({describe_error(e)}); se conserva el precio anterior.")
            informe[prod["id"]] = {"modo": "omitido", "candidatos": []}
            continue
        if fijado and not rebuscar:
            f = next((f for f in fichas if f["product_id"] == str(fijado)), None)
            if not f:
                try:
                    f = leer_ficha(fijado, unidad)
                except Exception as e:
                    print(f"  Aviso: {prod['name']}: el ID {fijado} no respondió ({describe_error(e)}); se conserva el precio anterior.")
                    informe[prod["id"]] = {"modo": "omitido", "candidatos": []}
                    continue
            if f and f["ref_price"] is not None:
                resultados[prod["id"]] = f
                informe[prod["id"]] = {"modo": "fijado", "candidatos": [f]}
                continue
            print(f"  Aviso: {prod['name']}: el producto {fijado} ya no aparece o no tiene precio; lo busco de nuevo.")
        if not query:
            resultados[prod["id"]] = None
            informe[prod["id"]] = {"modo": "busqueda", "query": consulta, "candidatos": [], "elegido": None}
            continue
        vistos, unicas = set(), []
        for f in fichas:
            if f["product_id"] not in vistos:
                vistos.add(f["product_id"])
                unicas.append(f)
        elegido, candidatos = elegir(query, unicas, unidad)
        resultados[prod["id"]] = elegido
        informe[prod["id"]] = {
            "modo": "busqueda", "query": consulta, "candidatos": candidatos,
            "elegido": elegido["product_id"] if elegido else None,
            "nuevo_pin": elegido["product_id"] if elegido and elegido["product_id"] != fijado else None,
        }
    return resultados, informe
