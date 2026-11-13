"""Descarga una miniatura de cada producto elegido en cada súper y la guarda en img/<súper>/.

Uso: python3 scraper/imagenes.py            # solo las que faltan
     python3 scraper/imagenes.py --todas    # vuelve a bajarlas todas

Guarda la ruta en prices.json (campo "image") para que la app la muestre y la tenga sin conexión.
Si un súper rechaza 2 descargas seguidas, se deja de intentar con él en esta ejecución.
"""
import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from comun import UA, get_json, describe_error  # noqa: E402
import aldi  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
EXT = {"image/webp": "webp", "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/avif": "avif"}
MAX_BONPREU = 2  # Bonpreu bloquea a partir de unas pocas peticiones


def url_mercadona(pid, entrada):
    p = get_json(f"https://tienda.mercadona.es/api/products/{pid}/?lang=es&wh=bcn1")
    fotos = p.get("photos") or []
    base = (fotos[0].get("thumbnail") if fotos else None) or p.get("thumbnail")
    return base.split("?")[0] + "?fit=crop&h=160&w=160&fm=webp&q=70" if base else None


_aldi_por_id = None


def url_aldi(pid, entrada, producto):
    pin = producto.get("pinned", {}).get("aldi") or ""
    sub = pin.rpartition("/")[0]
    if not sub:
        consulta = producto.get("queries", {}).get("aldi") or ""
        sub = consulta.split(":", 1)[0].strip()
    for h in aldi.productos_de(sub) if sub else []:
        if str(h.get("objectID")) == str(pid):
            assets = h.get("assets") or []
            return assets[0]["url"] + "?bfc=on&wid=160&fmt=webp-alpha" if assets else None
    return None


def url_consum(pid, entrada):
    p = get_json(f"https://tienda.consum.es/api/rest/V1.0/catalog/product/{pid}")
    return (p.get("productData") or {}).get("imageURL")


def url_dia(pid, entrada):
    return f"https://www.dia.es/product_images/{pid}/{pid}_ISO_0_ES.jpg?imwidth=176"


def url_bonpreu(pid, entrada):
    p = get_json(f"https://www.compraonline.bonpreuesclat.cat/api/webproductpagews/v5/products/bop?retailerProductId={pid}")["product"]
    src = (p.get("image") or {}).get("src")
    return src.replace("300x300", "150x150").rsplit(".", 1)[0] + ".webp" if src else None


def descargar(url, destino_sin_ext):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/webp,image/jpeg,image/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        datos = r.read()
    if not tipo.startswith("image/") or len(datos) < 200:
        raise RuntimeError(f"no es una imagen ({tipo}, {len(datos)} bytes)")
    ruta = destino_sin_ext.with_suffix("." + EXT.get(tipo, "img"))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    return ruta, len(datos)


def main(argv):
    todas = "--todas" in argv
    productos = {p["id"]: p for p in json.loads((RAIZ / "products.json").read_text())["products"]}
    ruta_precios = RAIZ / "prices.json"
    precios = json.loads(ruta_precios.read_text())
    resumen = {}
    fallos_seguidos = {}
    bonpreu_hechas = 0
    for pid_app, entrada in precios["products"].items():
        for super_, dato in (entrada.get("stores") or {}).items():
            if not dato or not dato.get("product_id"):
                continue
            r = resumen.setdefault(super_, {"ok": 0, "fallo": 0, "omitida": 0, "kb": 0.0, "errores": []})
            if dato.get("image") and (RAIZ / dato["image"]).exists() and not todas:
                r["omitida"] += 1
                continue
            if fallos_seguidos.get(super_, 0) >= 2:
                r["fallo"] += 1
                continue
            if super_ == "bonpreu":
                if bonpreu_hechas >= MAX_BONPREU:
                    r["omitida"] += 1
                    continue
                bonpreu_hechas += 1
            pid = dato["product_id"]
            try:
                if super_ == "aldi":
                    url = url_aldi(pid, dato, productos.get(pid_app, {}))
                else:
                    url = {"mercadona": url_mercadona, "consum": url_consum, "dia": url_dia,
                           "bonpreu": url_bonpreu}[super_](pid, dato)
                if not url:
                    raise RuntimeError("sin URL de imagen")
                ruta, peso = descargar(url, RAIZ / "img" / super_ / str(pid))
                dato["image"] = str(ruta.relative_to(RAIZ))
                r["ok"] += 1
                r["kb"] += peso / 1024
                fallos_seguidos[super_] = 0
            except Exception as e:
                r["fallo"] += 1
                fallos_seguidos[super_] = fallos_seguidos.get(super_, 0) + 1
                if len(r["errores"]) < 3:
                    r["errores"].append(f"{pid_app}: {describe_error(e)}")
                if fallos_seguidos[super_] == 2:
                    print(f"  {super_}: 2 fallos seguidos, se deja de intentar en esta ejecución.", flush=True)
            time.sleep(0.3)
    ruta_precios.write_text(json.dumps(precios, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== Fotos ===")
    total = 0.0
    for s, r in resumen.items():
        total += r["kb"]
        media = r["kb"] / r["ok"] if r["ok"] else 0
        print(f"{s:10} descargadas {r['ok']:3}  fallidas {r['fallo']:3}  ya estaban/omitidas {r['omitida']:3}  "
              f"{r['kb']:7.0f} KB (media {media:.1f} KB)")
        for e in r["errores"]:
            print(f"           error: {e}")
    print(f"Total descargado: {total/1024:.2f} MB")


if __name__ == "__main__":
    main(sys.argv)
