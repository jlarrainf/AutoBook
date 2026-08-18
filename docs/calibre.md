# Integración con Calibre y envío al dispositivo

AutoBook puede importar los libros descargados a tu biblioteca de Calibre, y enviarlos a tu Kindle/Kobo cuando está conectado. Usa `calibredb` y `ebook-convert` (vienen con Calibre); **no necesita ningún MCP adicional**.

## Requisitos

- [Calibre](https://calibre-ebook.com/) instalado (auto-detecta `calibredb.exe` y la biblioteca desde la config de Calibre).
- Para enviar al dispositivo: el lector conectado por USB en **modo transferencia de archivos** (montado como unidad).

## Tools

| Tool | Qué hace |
| :--- | :--- |
| `calibre_status()` | Estado: calibredb encontrado, ruta de la biblioteca, GUI de Calibre abierta, dispositivo montado. |
| `calibre_add(job_id \| path)` | Importa a la biblioteca un libro descargado (por `job_id` de `book_download`) o un archivo local. Fija título, autor, idioma, serie, número de serie, identificador `annas:<md5>` y portada (capturada de la página del libro). Devuelve `book_id` y `duplicated`. |
| `calibre_send_to_device(book_id \| path, format?)` | Envía el libro al dispositivo montado. Convierte al formato destino si hace falta (por defecto MOBI). Devuelve la ruta en el dispositivo. |

## Flujo completo (prompt)

> Descarga "Pedro Páramo" en español epub, añádelo a mi biblioteca de Calibre, revisa y arregla sus metadatos si hace falta, y mándalo a mi Kindle.

La IA hará:

1. `book_search` → `book_download` → `get_download_status` (esperar a `done`).
2. `calibre_add(job_id=…)` → obtiene `book_id`.
3. Revisar metadatos (con el MCP de calibre si está instalado): `calibre_get_book_details(book_id)`; si el autor trae basura (p. ej. "Juan Rulfo; OverDrive, Inc"), `calibre_set_book_metadata(book_id, authors="Rulfo, Juan")` y `calibre_fix_book_paths(book_ids=[…])`.
4. `calibre_send_to_device(book_id=…)` → convierte a MOBI y copia a `documents/` en el Kindle.

## Arreglo profundo de metadatos (opcional, con el MCP de calibre)

AutoBook fija los metadatos **básicos** al importar (los que vienen de Anna's Archive). Para enriquecer (portada si falta, editorial, sinopsis, corregir autores/series) usa las tools del MCP de calibre si lo tienes instalado:

- `calibre_get_book_details(book_id)` — ver qué falta.
- `calibre_fetch_metadata(book_ids=[…], source="openlibrary", apply=true, dry_run=false)` — buscar en OpenLibrary/Google Books y aplicar.
- `calibre_set_book_metadata` / `calibre_bulk_set_metadata` — correcciones manuales.
- `calibre_embed_metadata(book_ids=[…])` — incrustar los metadatos en el archivo (recomendado antes de enviar al dispositivo).
- `calibre_find_missing_metadata()` — auditar la biblioteca entera.

Sin el MCP de calibre también puedes pedirle a la IA que use `calibredb set_metadata` directamente, o arreglarlo en la GUI de Calibre.

## Duplicados

- `calibre_add` nunca crea duplicados: usa `--automerge=ignore` y detecta libros existentes por identificador `annas:<md5>` o por título/autor. Si ya existe, devuelve el `book_id` existente con `duplicated: true`.

## Configuración (`config.yaml` / `.env`)

```yaml
calibre:
  enabled: true
  library_path: ""       # vacío = autodetectar
  calibredb: ""          # vacío = autodetectar
  auto_import: false     # true = importar solo, tras cada descarga
  device_format: mobi    # mobi, azw3, epub, pdf
  device_path: ""        # vacío = autodetectar Kindle/Kobo montado
```

Overrides en `.env`: `CALIBRE_LIBRARY`, `CALIBRE_DB`, `CALIBRE_AUTO_IMPORT`, `DEVICE_FORMAT`, `DEVICE_PATH`.

## Detección de dispositivos

- **Kindle**: unidad extraíble con carpeta `documents/` → copia ahí.
- **Kobo**: unidad extraíble con carpeta `.kobo` → copia a la raíz.
- **Manual**: `device_path` / `DEVICE_PATH` con la carpeta destino.
- Si el dispositivo está conectado pero **no montado** (solo carga), `calibre_send_to_device` da error: cambia el modo USB a transferencia de archivos.

## Notas y solución de problemas

- **GUI de Calibre abierta**: `calibredb` normalmente funciona igual, pero si la base de datos está bloqueada, cierra la GUI y reintenta. Tras importar con la GUI abierta, puede que necesites refrescarla (F5) para ver el libro.
- **Portada**: se captura de la página del md5 durante la descarga (se guarda en `downloads/.covers/`). Si el EPUB ya trae portada incrustada, Calibre usa esa.
- **Expulsar el dispositivo**: usa "Expulsar de forma segura" antes de desconectar el Kindle.
- **MOBI en Kindle**: es el formato por defecto por compatibilidad universal. Los Kindle modernos también leen AZW3 (`device_format: azw3`, mejor tipografía).
