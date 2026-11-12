# Proyecto "Compras Barcelona": contexto para migrar a otra cuenta de Claude

Fecha de este resumen: 12-11-2026.
Pega este archivo al inicio de la nueva conversación o súbelo al proyecto.

## 1. Objetivo
Una app para Alejandro y su esposa (ambos con iPhone) que permita:
1. **Buscar un producto** y ver su precio en **Aldi, Bonpreu Esclat y Mercadona** (Barcelona), para saber dónde conviene o si da igual.
2. **Elegir un supermercado** y ver la lista de lo que conviene comprar ahí frente a los otros dos.

Ejemplo dado por el usuario: la leche cuesta lo mismo en los tres, pero la canela en polvo es más barata en Aldi que en Mercadona.

## 2. Decisiones tomadas
- **No existe una base de datos abierta fiable** con los tres supermercados. Se extraerán los precios **web por web**.
- **Precio al Plato** (github.com/precio-al-plato): descartado como base. Solo cubre Alcampo, Carrefour y Mercadona, no publica un dataset descargable y su licencia es ambigua (texto CC BY-NC-ND 4.0 frente a insignia MIT). Solo sirve de inspiración.
- **Formato:** web app estática que se abre desde Safari y se añade a la pantalla de inicio del iPhone. No es app nativa y no pasa por la App Store.
- **Alojamiento:** GitHub Pages (gratis, repositorio público; no habrá datos personales). Alternativa privada: Cloudflare Pages con Cloudflare Access. El usuario aceptó GitHub Pages. Se puede añadir `<meta name="robots" content="noindex">`, que reduce la indexación pero no es seguridad real.
- **Datos:** un archivo `prices.json` dentro del repositorio.
- **Actualización:** un script en la Mac del usuario consulta los 3 supermercados, actualiza el JSON y hace push a GitHub (manual o programado, p. ej. semanal). Solo corre si la Mac está encendida y con internet.
- Oracle Cloud no hace falta.

## 3. Canasta inicial
Pedida por el usuario: leche, huevos, arroz, azúcar, sal, ternera, pollo, cerdo.
Ideas adicionales mencionadas: canela en polvo, pasta, aceite de oliva, yogures, fruta. Objetivo: 30 a 40 productos habituales.
La app debe comparar por **precio por kg o litro** (no por precio del envase).

## 4. Cómo se obtienen los precios (verificado el 12-11-2026)
**Importante:** desde el entorno cloud de Claude, `curl` a estas webs es bloqueado (403 del proxy). Funcionó usando el **navegador integrado** de Claude en el ordenador del usuario, con los permisos de sitio concedidos. Un script en la Mac del usuario sí podrá acceder a las webs.

### Mercadona: API JSON pública (no oficial, sin login)
- Categorías: `https://tienda.mercadona.es/api/categories/?lang=es&wh=bcn1`
- Subcategoría con productos: `https://tienda.mercadona.es/api/categories/{id}/?lang=es&wh=bcn1`
- `wh=bcn1` es el almacén de Barcelona.
- Campos útiles: `display_name`, `price_instructions.unit_price`, `price_instructions.reference_price`, `price_instructions.reference_format`.
- IDs vistos: 6 = Huevos, leche y mantequilla; 13 = Arroz, legumbres y pasta; 12 = Aceite, especias y salsas; 3 = Carne. Subcategorías: 77 = Huevos, 72 = Leche y bebidas vegetales, 118 = Arroz.
- Librería de referencia: `mercapy` (MIT), github.com/jtayped/mercapy. Hay scrapers de pago en Apify. La API puede cambiar sin aviso.

### Bonpreu Esclat: sin API, se lee la web de la tienda online
- Búsqueda: `https://www.compraonline.bonpreuesclat.cat/search?q=llet+sencera`
- Los resultados muestran precio y precio por litro o kg en el texto de la página (hay que parsear el HTML renderizado, probablemente con navegador headless).
- Alternativa de pago: actor de Apify `kaidev/bonpreuesclat-cat-scrapper` (unos 10 $ por 1.000 productos).
- Los precios online pueden diferir de los de la tienda física.

### Aldi: precios en la web, sin tienda online
- Categorías en `https://www.aldi.es/productos/...`, p. ej. `/productos/lacteos-y-huevos/leche-y-bebidas-vegetales.html` y `/productos.html` como índice.
- Cada producto muestra nombre, precio, unidad y precio por kg o litro.
- Los precios son **nacionales**, no por tienda. El buscador `aldi.es/buscar.html` da 404; hay que navegar por categorías.
- La página de huevos no mostró precios en el texto extraído; falta revisarla.
- Alternativa de pago: Apify `blackfalcondata/aldi-scraper` (declara cubrir España; no verificado).

## 5. Precios verificados (12-11-2026)
| Producto | Mercadona | Bonpreu | Aldi |
|---|---|---|---|
| Leche entera 1 L | 0,96 € (Hacendado) | 0,96 € (Bonpreu) | 0,96 € (Milsani) |
| Leche semidesnatada 1 L | 0,83 € | pendiente | 0,83 € |
| Leche desnatada 1 L | 0,81 € | pendiente | 0,81 € |
| Huevos L (docena) | 3,05 € | pendiente | pendiente |
| Arroz redondo | 1,15 €/kg | pendiente | pendiente |

Otros datos de Mercadona: arroz largo Hacendado 1,20 €/kg; huevos XL 4,30 € la docena.
Pendiente de comprobar en los tres: azúcar, sal, ternera, pollo, cerdo, canela en polvo, aceite de oliva, pasta, yogures.

## 6. Limitaciones y riesgos
- Mercadona usa una API no oficial.
- Los términos de uso de las webs pueden restringir el scraping automático; para uso personal y pocas lecturas semanales el riesgo es bajo.
- No hay fuente de histórico de precios; habrá que guardar las capturas en el repositorio.
- Hay que emparejar productos equivalentes entre cadenas (marca blanca frente a marca blanca, mismo formato) y normalizar por €/kg o €/L.

## 7. Próximos pasos propuestos
1. Definir la lista final de productos y, para cada uno, el equivalente en cada cadena. Un archivo `products.json` con una consulta o ID por supermercado.
2. Escribir el script (Python o Node) que lea las tres fuentes y genere `prices.json` con fecha de captura.
3. Construir la web app estática (HTML/JS, pensada para móvil) con dos vistas: buscar producto y ver los tres precios, y elegir supermercado y ver qué comprar ahí, qué conviene en otro y qué da igual.
4. Crear el repositorio, activar GitHub Pages y probar en iPhone con "Añadir a pantalla de inicio".
5. Programar la actualización semanal (launchd o cron en la Mac) con commit y push automáticos.

## 8. Notas sobre el usuario
- Idioma: español. Prefiere respuestas en español.
- Ingeniero informático; cómodo con scripts y GitHub.
- Trabaja desde una Mac. La carpeta del proyecto es `Documents/Compras Barcelona`.
