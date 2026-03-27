# Detector de Oportunidades de Compra de Autos

**Fecha:** 2026-03-27
**Estado:** Aprobado

## Objetivo

Sistema que scrapea las principales páginas de publicaciones de autos en Argentina, calcula precios de referencia (mediana) por modelo/año/km, y detecta autos publicados por debajo del mercado con al menos USD 1.000 de diferencia. Los resultados se muestran en un dashboard web local.

## Parámetros del negocio

- **Región:** Buenos Aires (CABA + Provincia), otras provincias si la oportunidad es muy buena
- **Antigüedad:** Hasta 10 años (2016+)
- **Precio máximo de compra:** Sin límite
- **Definición de oportunidad:** Precio < mediana del mercado Y diferencia >= USD 1.000
- **Precios:** Se muestran en ARS y USD, oportunidad se calcula en USD
- **Notificaciones:** No por ahora, solo dashboard

## Arquitectura

```
MercadoLibre API ──┐
Autocosmos scraper ─┼──> Normalizador ──> SQLite DB ──> Análisis ──> Streamlit Dashboard
DeMotores scraper ──┤
OLX scraper ────────┘
```

### Stack

- **Python** (scraping, análisis, dashboard)
- **MercadoLibre API** pública para ML
- **BeautifulSoup + requests** para scraping del resto
- **SQLite** para almacenamiento local
- **Streamlit** para dashboard web
- **dolarapi.com** para tipo de cambio USD/ARS (dólar blue)

### Estructura de carpetas

```
Autos/oportunidades/
├── scrapers/
│   ├── mercadolibre.py
│   ├── autocosmos.py
│   ├── demotores.py
│   └── olx.py
├── core/
│   ├── normalizer.py
│   ├── analyzer.py
│   └── exchange_rate.py
├── db/
│   └── database.py
├── dashboard/
│   └── app.py
├── run_scraper.py
├── requirements.txt
└── autos.db (generado)
```

## Modelo de datos

### Tabla `listings` (publicaciones)

| Campo | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | ID interno autoincremental |
| source | TEXT | "mercadolibre", "autocosmos", "demotores", "olx" |
| source_id | TEXT | ID de la publicación en la fuente |
| url | TEXT | Link a la publicación |
| brand | TEXT | Marca |
| model | TEXT | Modelo |
| version | TEXT | Versión/trim |
| year | INTEGER | Año |
| km | INTEGER | Kilómetros |
| price_ars | REAL | Precio en ARS |
| price_usd | REAL | Precio en USD |
| currency_original | TEXT | Moneda original |
| location | TEXT | Ubicación |
| category | TEXT | "alta", "media", "baja" |
| transmission | TEXT | "manual", "automática" |
| fuel | TEXT | "nafta", "diesel", "gnc", "híbrido", "eléctrico" |
| image_url | TEXT | URL imagen principal |
| scraped_at | DATETIME | Fecha/hora del scraping |

**Deduplicación:** Clave única `source + source_id`.

### Tabla `market_reference` (análisis)

| Campo | Tipo | Descripción |
|---|---|---|
| brand | TEXT | Marca |
| model | TEXT | Modelo |
| year | INTEGER | Año |
| median_price_usd | REAL | Mediana |
| sample_count | INTEGER | Cantidad de publicaciones |
| min_price_usd | REAL | Precio mínimo |
| max_price_usd | REAL | Precio máximo |
| updated_at | DATETIME | Última actualización |

### Categorización

- **Alta gama:** mediana > USD 30.000
- **Media:** mediana entre USD 10.000 y USD 30.000
- **Baja:** mediana < USD 10.000

## Dashboard

### Vista principal: Oportunidades

Tabla ordenada por mayor diferencia (mejor oportunidad primero):
- Imagen, Marca/Modelo/Año, Km, Precio (ARS + USD), Mediana mercado, Ganancia potencial (USD), Ubicación, Fuente (link), Categoría

### Filtros (sidebar)

- Categoría (alta/media/baja)
- Marca y Modelo (dropdowns encadenados)
- Rango de año (slider 2016-2026)
- Rango de km (slider)
- Rango de precio USD (slider)
- Ganancia mínima (slider, default USD 1.000)
- Ubicación (Buenos Aires / Otras)
- Fuente

### Métricas superiores (cards)

- Total publicaciones relevadas
- Oportunidades detectadas
- Mejor oportunidad (mayor diferencia)
- Fecha último scraping

### Vista secundaria: Análisis de mercado

- Precio mediano por modelo/año
- Histograma de precios para modelo seleccionado
- Publicaciones por fuente

## Scraping

### MercadoLibre

- API pública `api.mercadolibre.com`
- Categoría "Autos y Camionetas", filtro Buenos Aires + CABA, año 2016+
- Paginación de a 50 resultados
- Sin autenticación para búsquedas públicas

### Autocosmos, DeMotores, OLX

- BeautifulSoup + requests
- Headers de navegador, User-Agent rotativo
- Rate limiting con pausas entre requests
- Retry con backoff exponencial

### Tipo de cambio

- API pública `dolarapi.com` (dólar blue)
- Se obtiene al inicio de cada corrida

### Ejecución

- `python run_scraper.py` manual o con cron (semanal inicialmente)
- Corre cada scraper en secuencia, si uno falla los demás siguen
- Log en consola del progreso

## Evolución futura (fuera de alcance actual)

- Notificaciones (email, WhatsApp, Telegram)
- Despliegue en servidor (acceso desde cualquier dispositivo)
- Captación de clientes compradores/vendedores
- Historial de precios y tendencias
