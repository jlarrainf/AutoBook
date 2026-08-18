# Integración con Calibre y envío al dispositivo

AutoBook importa los libros descargados a tu biblioteca de Calibre y los envía a tu Kindle/Kobo cuando está conectado, todo en **un solo pipeline estructurado**. Usa `calibredb` y `ebook-convert` (vienen con Calibre); **no necesita ningún MCP adicional**.

## Requisitos

- [Calibre](https://calibre-ebook.com/) instalado (auto-detecta `calibredb.exe` y la biblioteca desde la config de Calibre).
- Para enviar al dispositivo: el lector conectado por USB (modo transferencia; funciona también si aparece como dispositivo portátil MTP en "Este equipo", sin letra de unidad).

## El pipeline (flujo principal)

Un solo llamado hace todo, con validación **fail-fast** antes de empezar:

```
book_search → book_download(md5, ..., to_calibre=true, to_device=true) → get_download_status (polling)
```

Etapas del job: `download → calibre → device`:

1. **download**: descarga el libro (y la portada ya viene dentro del archivo).
2. **calibre**: importa con `calibredb` fijando título, autor **normalizado** ("Tolkien, J.R.R." → "J. R. R. Tolkien"; "Autor; Distribuidor" → solo el autor), idioma, serie, índice e identificador `annas:<md5>`. Nunca crea duplicados (detecta por identificador o título/autor). Corrige `title_sort`/`author_sort` automáticamente.
3. **device**: incrusta los metadatos corregidos en el EPUB, convierte al formato destino (por defecto AZW3) y copia al dispositivo (unidad o MTP, a `documents/` en Kindle).

Validación previa: si `to_calibre=true` y Calibre no está detectado, o `to_device=true` y no hay dispositivo, `book_download` devuelve error **de inmediato** (no se pierde tiempo descargando).

### Estados (`get_download_status`)

| status | stage | Significado |
| :--- | :--- | :--- |
| `queued` / `downloading` | `download` | Descarga en curso (puede tardar minutos; cola por IP). |
| `importing` | `calibre` | Importando a Calibre. |
| `sending` | `device` | Convirtiendo y enviando al dispositivo. |
| `done` | `done` | Todo listo: `dest`, `calibre_book_id`, `device_dest`. |
| `waiting_captcha` | — | Resolver el CAPTCHA en la ventana del navegador. |
| `error` | `download` / `calibre` / `device` | Falló ESA etapa; mira `error`, `calibre_error` o `device_error`. Las etapas previas completadas se conservan. |

**Reintento por etapa** (sin repetir lo que ya funcionó):

- Falló `stage=calibre` → `calibre_add(job_id=…)`.
- Falló `stage=device` → `calibre_send_to_device(book_id=…)` (con el dispositivo ya conectado).

## Tools

| Tool | Qué hace |
| :--- | :--- |
| `calibre_status()` | Estado: calibredb encontrado, biblioteca, GUI de Calibre abierta, dispositivo detectado. |
| `calibre_add(job_id \| path)` | Importa a la biblioteca un libro descargado o un archivo local, con metadatos limpios. Devuelve `book_id` y `duplicated`. |
| `calibre_send_to_device(book_id \| path, format?)` | Envía al dispositivo (unidad o MTP), incrusta metadatos y convierte si hace falta (por defecto AZW3). Devuelve la ruta en el dispositivo. |

## Prompt de ejemplo

> Descarga "El Señor de los Anillos" en inglés, los tres libros como serie, y mándalos a mi Kindle.

La IA: busca → `book_download(..., series="The Lord of the Rings", series_index=N, to_calibre=true, to_device=true)` por volumen (uno a la vez) → polling → resultado. Si el Kindle no está conectado, el error sale al instante y puede reintentar el envío después con `calibre_send_to_device`.

## Arreglo profundo de metadatos (opcional, con el MCP de calibre)

AutoBook ya limpia lo básico al importar (autor, título, sorts, idioma, serie). Para enriquecer más (editorial, sinopsis, etc.) usa las tools del MCP de calibre si lo tienes instalado:

- `calibre_get_book_details(book_id)` — ver qué falta.
- `calibre_fetch_metadata(book_ids=[…], source="openlibrary", apply=true, dry_run=false)` — buscar en OpenLibrary/Google Books y aplicar.
- `calibre_set_book_metadata` / `calibre_bulk_set_metadata` — correcciones manuales.
- `calibre_embed_metadata(book_ids=[…])` — incrustar metadatos en el archivo.
- `calibre_find_missing_metadata()` — auditar la biblioteca entera.

Sin el MCP de calibre: pídele a la IA que use `calibredb set_metadata`, o arréglalo en la GUI de Calibre.

## Configuración (`config.yaml` / `.env`)

```yaml
calibre:
  enabled: true
  library_path: ""       # vacío = autodetectar
  calibredb: ""          # vacío = autodetectar
  device_format: azw3    # azw3, mobi, epub, pdf
  device_path: ""        # vacío = autodetectar Kindle/Kobo
```

Overrides en `.env`: `CALIBRE_LIBRARY`, `CALIBRE_DB`, `DEVICE_FORMAT`, `DEVICE_PATH`.

## Detección de dispositivos

- **Kindle**: unidad extraíble con carpeta `documents/`, o dispositivo portátil **MTP** visible en "Este equipo" (Kindle modernos que no se montan con letra de unidad) → copia a `documents/`.
- **Kobo**: unidad extraíble con carpeta `.kobo`, o MTP → copia a la raíz.
- **Manual**: `device_path` / `DEVICE_PATH` con la carpeta destino.
- El envío por MTP usa el Shell de Windows: es asíncrono y puede tardar unos segundos en aparecer el archivo en el dispositivo.

## Notas y solución de problemas

- **GUI de Calibre abierta**: `calibredb` normalmente funciona igual, pero si la base de datos está bloqueada, cierra la GUI y reintenta. Tras importar con la GUI abierta, puede que necesites refrescarla (F5) para ver el libro.
- **Expulsar el dispositivo**: usa "Expulsar de forma segura" antes de desconectar el Kindle.
- **Formato para Kindle**: por defecto AZW3 (buena tipografía, todos los Kindle modernos). `device_format: mobi` para Kindles muy viejos.
- **Duplicados**: `calibre_add` usa `--automerge=ignore` y detecta existentes por identificador `annas:<md5>` o título/autor; si ya existe devuelve el `book_id` existente con `duplicated: true`.
