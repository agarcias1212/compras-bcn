"""Prueba rápida: ¿Bonpreu y Aldi aceptan peticiones desde Python?

Uso: python3 scraper/probar_fuentes.py
"""
import json
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def pedir(url, accept="text/html,application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "es-ES,es;q=0.9,ca;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read().decode("utf-8", "replace")


def prueba(nombre, funcion):
    print(f"\n--- {nombre}")
    try:
        funcion()
    except Exception as e:
        codigo = getattr(e, "code", None)
        print(f"  FALLA: {'HTTP ' + str(codigo) if codigo else type(e).__name__ + ': ' + str(e)}")


def bonpreu_busqueda():
    s, html = pedir("https://www.compraonline.bonpreuesclat.cat/search?q=llet%20sencera")
    i = html.find("window.__INITIAL_STATE__=")
    print(f"  HTTP {s}, {len(html)} bytes, estado encontrado: {i >= 0}")
    if i < 0:
        return
    resto = html[i + 25:]
    estado = json.loads(resto[:resto.index("</script>")].strip().rstrip(";"))
    productos = list((estado["data"]["products"].get("productEntities") or {}).values())
    print(f"  {len(productos)} productos. Primeros:")
    for p in productos[:3]:
        print(f"   [{p['retailerProductId']}] {p['name']} - {p['price']['current']['amount']} € "
              f"({p['price']['unit']['current']['amount']} {p['price']['unit']['label']})")


def bonpreu_por_id():
    s, txt = pedir("https://www.compraonline.bonpreuesclat.cat/api/webproductpagews/v5/products/bop?retailerProductId=81177",
                   accept="application/json")
    p = json.loads(txt)["product"]
    print(f"  HTTP {s}: [{p['retailerProductId']}] {p['name']} - {p['price']['amount']} € "
          f"({p['unitPrice']['price']['amount']} {p['unitPrice']['unit']})")


def aldi_subcategoria():
    s, html = pedir("https://www.aldi.es/productos/despensa/arroz.html")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    print(f"  HTTP {s}, {len(html)} bytes, __NEXT_DATA__ encontrado: {bool(m)}")
    if not m:
        return
    hits = {}

    def recorrer(o):
        if isinstance(o, dict):
            if isinstance(o.get("hits"), list):
                for h in o["hits"]:
                    if isinstance(h, dict) and h.get("name"):
                        hits[h["objectID"]] = h
            for v in o.values():
                recorrer(v)
        elif isinstance(o, list):
            for v in o:
                recorrer(v)

    recorrer(json.loads(m.group(1)))
    print(f"  {len(hits)} productos. Primeros:")
    for h in list(hits.values())[:3]:
        print(f"   [{h['objectID']}] {h['name']} - {(h.get('currentPrice') or {}).get('priceValue')} € ({h.get('salesUnit')})")


prueba("Bonpreu: página de búsqueda", bonpreu_busqueda)
prueba("Bonpreu: producto por ID (API JSON)", bonpreu_por_id)
prueba("Aldi: página de subcategoría", aldi_subcategoria)
