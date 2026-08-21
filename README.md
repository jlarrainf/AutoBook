# AutoBook

Agente de descarga de libros desde **Anna's Archive** controlado por IA a través de **Claude Code** (terminal o app de escritorio) u **opencode**. Le das un título y la IA hace todo el circuito:

```
buscar → descargar → importar a Calibre (metadatos limpios) → convertir → enviar a tu Kindle/Kobo
```

- Funciona por la vía **gratuita** (`slow download`), sin donación ni API key.
- Usa una ventana de **Chrome real** (perfil dedicado) para superar **DDoS-Guard** sin captchas. **Nunca cierra tu navegador**: tu Chrome/Edge normal queda intacto.
- La integración con **Calibre** es opcional pero viene lista: autodetecta `calibredb`, tu biblioteca y tu Kindle/Kobo (por unidad **o MTP**, sin necesidad de letra de unidad).

> **Nota legal**: Anna's Archive indexa obras con derechos de autor. Usa esta herramienta solo con obras de dominio público, licencias abiertas (Creative Commons, etc.) o material que tengas derecho a descargar.

---

## Requisitos

| Requisito | Detalles |
| :--- | :--- |
| Windows | 10/11. |
| Python 3.10+ | [python.org](https://www.python.org/downloads/) — marca **"Add python.exe to PATH"** al instalar. |
| Google Chrome o Edge | Auto-detectados (Edge viene con Windows). |
| Claude Code **u** opencode | [Claude Code](https://claude.com/claude-code) (terminal o app de escritorio) u [opencode](https://opencode.ai). |
| Calibre *(opcional)* | [calibre-ebook.com](https://calibre-ebook.com/) — solo si quieres importar a la biblioteca y enviar al Kindle. |

---

## Instalación en cualquier PC

Dos caminos: **que lo instale la IA** (recomendado, no tocas JSON) o **manual**.

### Opción A — Que lo instale la IA (recomendada)

1. **Consigue el proyecto**: descarga el ZIP desde GitHub (botón verde **Code → Download ZIP**) o `git clone <url>`. Descomprime: queda una carpeta `AutoBook`.
2. **Abre tu IA en esa carpeta** y pega el prompt de abajo.

**Con la app de escritorio de Claude Code**: abre la app, selecciona la carpeta `AutoBook` como proyecto y pega este bloque completo (cópialo tal cual):

```text
Estás en la carpeta del proyecto AutoBook. Instálalo y regístralo como servidor MCP local (stdio) para Claude Code. Haz exactamente esto:

1. Si no existe la carpeta .venv, crea el entorno virtual e instala las dependencias:
   - python -m venv .venv
   - .venv\Scripts\python.exe -m pip install -r requirements.txt
2. Comprueba que el servidor arranca:
   - .venv\Scripts\python.exe -c "import autobook.server; print('OK')"
3. Obtén la ruta absoluta del python del venv y escríbela con doble backslash (\\). Puedes sacarla con PowerShell: (Resolve-Path .venv\Scripts\python.exe).Path
4. Crea el archivo .mcp.json en la raíz (si no existe) con este contenido, reemplazando C:\RUTA\ABSOLUTA\A\AutoBook por la ruta real:

   {
     "mcpServers": {
       "autobook": {
         "type": "stdio",
         "command": "C:\\RUTA\\ABSOLUTA\\A\\AutoBook\\.venv\\Scripts\\python.exe",
         "args": ["-m", "autobook.server"]
       }
     }
   }

5. Verifica que el JSON es válido y que .mcp.json está en la raíz.
6. Dime que cierre por completo la app (icono de la bandeja del sistema → Quit; no basta cerrar la ventana) y la abra de nuevo en esta carpeta.
7. Cuando la IA confirme el reinicio, acepta la aprobación de las tools MCP que pida la app y prueba con: "Usa la tool calibre_status para verificar la integración, y luego usa book_search para buscar 'El Principito' en español, formato epub."
```

**Con opencode**: no necesitas pegar nada extra. El prompt de arriba crea el venv (lo único que falta); el registro del MCP ya viene en `opencode.json` del proyecto. Abre opencode dentro de la carpeta `AutoBook`, reinícialo si hace falta y ejecuta `/mcp` para confirmar que `autobook` está conectado. Si ya instalaste con Claude Code, opencode también queda listo (comparten el mismo venv).

> En **`docs/instalacion-ai.md`** hay variantes de estos prompts y la explicación de qué es normal la primera vez.

### Opción B — Manual

**Automática (Windows):** doble clic en `install.bat` dentro de la carpeta. Crea el venv, instala dependencias y comprueba que el servidor arranca.

**Por línea de comandos** (PowerShell, dentro de la carpeta `AutoBook`):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$p = (Resolve-Path .\.venv\Scripts\python.exe).Path.Replace('\','\\')
[System.IO.File]::WriteAllText("$PWD\.mcp.json", '{"mcpServers":{"autobook":{"type":"stdio","command":"' + $p + '","args":["-m","autobook.server"]}}}')
```

Luego cierra del todo tu IA y vuelve a abrirla en esa carpeta. No hace falta `playwright install` ni descargar navegadores: se usa el Chrome/Edge instalado.

### Verificación

Dentro de la IA, pide:

> Usa la tool `calibre_status` y `check_mirrors` de autobook y dime qué ves.

Deberías ver la ruta de `calibredb`, tu biblioteca y si hay dispositivo conectado (si tienes Calibre), y qué mirrors de Anna's Archive están vivos.

> **⚠️ Confusión común**: la app de escritorio de **Claude Code** lee `.mcp.json` (como el CLI). La app de chat **Claude Desktop** es otra cosa: usa `%APPDATA%\Claude\claude_desktop_config.json` y **no** funciona para esto. Usa siempre **Claude Code**.

---

## ¿Desde cualquier carpeta o solo dentro del proyecto?

Depende de **dónde registres** el MCP, no del servidor en sí (autobook funciona igual desde cualquier carpeta: resuelve sus rutas contra su propia carpeta; los libros van a `<AutoBook>\downloads` salvo que lo cambies con `set_download_dir`).

- **Solo en la carpeta de AutoBook** (configuración por proyecto, la recomendada para empezar): el MCP se carga solo cuando abres Claude Code u opencode **dentro** de la carpeta `AutoBook`. Es lo que hace la instalación de arriba (`.mcp.json` para Claude Code, `opencode.json` para opencode).
- **Desde cualquier carpeta** (registro global/usuario): el MCP queda disponible aunque abras la IA en cualquier otro proyecto. Se registra a nivel global con **ruta absoluta**:

**Claude Code** — una sola línea (desde la carpeta de AutoBook):

```powershell
claude mcp add autobook --scope user -- "C:\ruta\absoluta\a\AutoBook\.venv\Scripts\python.exe" -m autobook.server
```

**opencode** — edita el archivo global `%USERPROFILE%\.config\opencode\opencode.json` y añade el bloque `mcp` (con la **ruta absoluta** del python del venv):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "autobook": {
      "type": "local",
      "command": ["C:\\ruta\\absoluta\\a\\AutoBook\\.venv\\Scripts\\python.exe", "-m", "autobook.server"]
    }
  }
}
```

Luego **reinicia** Claude Code u opencode.

---

## Flujo del MCP (guía para la IA)

Cuando el usuario pide un libro, el circuito correcto es:

### 1. Buscar y elegir bien

`book_search(query, language, format)` devuelve candidatos con `title`, `author`, `filesize`, `md5`, etc. **La elección del resultado importa**: prefiere títulos con mayúsculas correctas, autores limpios (idealmente formato `Apellido, Nombre`) y tamaño razonable (descarta resultados de pocos bytes). Los resultados con metadatos sucios (corchetes, minúsculas, contribuyentes extra) ensucian el nombre final en Calibre y en el dispositivo.

### 2. Lanzar el pipeline completo

```
book_download(md5, title, author, extension,
              series?, series_index?,     # para sagas: nombres "Book NN - Título"
              language?,                  # del resultado de búsqueda
              to_calibre=true,            # importar a Calibre
              to_device=true/false,       # enviar al Kindle/Kobo
              device_format?)             # por defecto azw3
```

- **Validación fail-fast**: si `to_calibre=true` y Calibre no está detectado, o `to_device=true` y no hay dispositivo conectado, la tool devuelve error **de inmediato** (sin descargar). La IA debe avisar al usuario (conectar el Kindle, instalar Calibre) o relanzar sin esas etapas.
- Para series: un `book_download` por volumen, **uno a la vez** (la cola gratis es por IP; en paralelo se enlentecen).

### 3. Polling hasta el final

`get_download_status(job_id)` en bucle (cada ~10 s) hasta `status: done` o `error`:

| status | stage | Significado |
| :--- | :--- | :--- |
| `queued` / `downloading` | `download` | Descarga en curso (1–10 min; cola por IP). |
| `importing` | `calibre` | Importando a Calibre con metadatos limpios. |
| `sending` | `device` | Incrustando metadatos, convirtiendo y copiando al dispositivo. |
| `done` | `done` | Todo listo: `dest` (archivo), `calibre_book_id`, `device_dest`. |
| `waiting_captcha` | — | El usuario debe resolver el CAPTCHA en la ventana del navegador. |
| `error` | `download` / `calibre` / `device` | Falló **esa etapa**; las previas se conservan. |

### 4. Reintentar solo la etapa fallida

- `stage=download` → relanzar `book_download` (o probar otro resultado).
- `stage=calibre` → `calibre_add(job_id=…)`.
- `stage=device` → `calibre_send_to_device(book_id=…)` cuando el dispositivo esté conectado.

### 5. Arreglo profundo de metadatos (rara vez necesario)

La importación ya normaliza autor/título/sorts. Si el usuario quiere enriquecer (sinopsis, editorial…) y está instalado el **MCP de calibre**: `calibre_get_book_details` → `calibre_fetch_metadata(apply)` → `calibre_embed_metadata`. Ver [docs/calibre.md](docs/calibre.md).

### Prompts de ejemplo del usuario

> "Descarga 'El Señor de los Anillos' en inglés, los tres libros como serie, y mándalos a mi Kindle."

> "Descarga 'Pedro Páramo' en español epub y guárdalo en mi biblioteca de Calibre."

> "¿Qué mirrors están vivos?" / "¿Está mi Kindle conectado?"

---

## Herramientas MCP disponibles

El servidor expone **50 herramientas** agrupadas en 7 categorías. Todas aceptan
lenguaje natural desde la IA (no hace falta nombrar la tool).

> **Estrategia de descarga**: el *slow download* de Anna's Archive es el método
> principal (gratis, sin API key). El fallback a **Z-Library** solo se usa como
> último recurso, cuando el slow download no da enlace o el link obtenido está
> caído/expirado.

### 1. Búsqueda y descarga (Anna's Archive)

| Tool | Descripción |
| :--- | :--- |
| `book_search(query, language, format, limit)` | Busca libros. Devuelve `title`, `author`, `language`, `extension`, `filesize` y **`md5`**. |
| `book_search_advanced(query, language, format, author, ...)` | Búsqueda avanzada combinando múltiples filtros en un solo query. |
| `book_download(md5, title, author, extension, series?, series_index?, language?, to_calibre?, to_device?, device_format?)` | Pipeline completo: descarga → (Calibre) → (dispositivo). Valida fail-fast y devuelve `job_id`. |
| `book_download_batch(books, to_calibre?, to_device?, device_format?)` | Cola múltiples descargas en lote (`books`: lista de `{md5, title, author, extension, ...}`). |

### 2. Control de descargas (jobs)

| Tool | Descripción |
| :--- | :--- |
| `get_download_status(job_id)` | Estado del pipeline: `queued/downloading/importing/sending/done/waiting_captcha/error/cancelled` + `stage` (`download/calibre/device/done`) y resultados por etapa. |
| `list_download_jobs(status?, limit?)` | Lista todos los jobs, opcionalmente filtrados por `status`. |
| `cancel_download_job(job_id)` | Cancela un job en curso o en cola (borra el `.part` parcial). |
| `retry_job(job_id)` | Reintenta un job que falló o fue cancelado (resetea estado y relanza). |
| `retry_failed_jobs(stage?)` | Reintenta todos los jobs en `error`; opcionalmente solo del `stage` indicado. |
| `set_download_dir(path)` | Cambia la carpeta de descargas en caliente (sin reiniciar). |
| `check_mirrors()` | Comprueba qué mirrors de Anna's Archive responden y devuelve el principal en uso. |
| `session_info()` | Estado de la sesión de navegador (Chrome vía CDP) y carpeta de descargas. |

### 3. Integración con Calibre (importar / enviar a dispositivo)

| Tool | Descripción |
| :--- | :--- |
| `calibre_status()` | Estado de la integración: `calibredb`, ruta de biblioteca, si la GUI está abierta y dispositivo detectado (unidad o MTP). |
| `calibre_add(job_id \| path, title?, author?, language?, series?, series_index?, identifier_md5?)` | Importa a Calibre con metadatos limpios y sin duplicados (reintento de la etapa `calibre`). Devuelve `book_id`. |
| `calibre_send_to_device(book_id \| path, format?)` | Incrusta metadatos, convierte (por defecto AZW3) y envía al Kindle/Kobo (reintento de la etapa `device`). |
| `calibre_list_devices()` | Lista dispositivos Kindle/Kobo detectados (USB + MTP). |
| `calibre_eject_device()` | Expulsa de forma segura un dispositivo conectado vía PowerShell. |

### 4. Exploración de la biblioteca

| Tool | Descripción |
| :--- | :--- |
| `calibre_search_books(title?, author?, series?, tag?, publisher?, format?, identifier?, has_cover?, has_formats?, query_string?, limit?, offset?)` | Búsqueda por campos estructurados (match parcial, case-insensitive) o query nativo de Calibre. |
| `calibre_get_book_details(book_id)` | Detalles completos: título, autores, serie, tags, editorial, idiomas, identificadores, rating, portada y formatos. |
| `calibre_list_authors(search?, min_books?, limit?, offset?, sort_by?)` | Autores con conteo de libros (filtra por nombre parcial y mínimo). |
| `calibre_list_series(search?, min_books?, limit?, offset?)` | Series con conteo de libros y rango de números (`#1–#N`). |
| `calibre_list_tags(search?, min_books?, limit?, offset?)` | Tags con conteo de libros. |
| `calibre_list_publishers(search?, min_books?, limit?, offset?)` | Editoriales con conteo de libros. |
| `calibre_library_stats()` | Estadísticas: total de libros, autores, series, tags, formatos y metadatos faltantes. |
| `calibre_find_missing_metadata(limit?)` | Libros con metadata incompleta: sin portada, idioma, tags, formatos o editorial. |
| `calibre_find_ghost_books(use_calibredb?, limit?, offset?)` | Libros en la DB cuya carpeta o archivos no existen en disco. |
| `calibre_find_orphan_files(use_calibredb?, limit?)` | Directorios/archivos en la biblioteca sin registro en la DB. |
| `calibre_find_orphan_links()` | Entradas huérfanas en tablas de enlace (book ID ya no existe). |

### 5. Limpieza y deduplicación

| Tool | Descripción |
| :--- | :--- |
| `calibre_find_duplicates(strategy?, limit?)` | Encuentra duplicados (`exact`/`isbn`/`fuzzy`). |
| `calibre_suggest_dedup_resolution(book_ids)` | Dado un grupo duplicado, sugiere cuál conservar (calidad: formato → portada → tamaño → fecha). |
| `calibre_find_author_variants(limit?)` | Grupos de autores que parecen la misma persona (casos, iniciales, acentos). |
| `calibre_merge_authors(canonical_id, variant_ids, dry_run?)` | Une variantes de autor al autor canónico. |
| `calibre_rename_author(author_id, new_name, new_sort?, dry_run?)` | Renombra un autor en la DB (incluye rename solo de mayúsculas/minúsculas). |
| `calibre_normalize_uppercase(item_type, limit?, dry_run?)` | Convierte TÍTULOS/TAGS/EDITORIALES/SERIES en MAYÚSCULAS a Title Case. |
| `calibre_find_compilation_coverage(author_id, min_compilation_kb?)` | Detecta qué obras individuales de un autor están cubiertas por sus recopilatorios. |
| `calibre_analyze_author(author_id)` | Análisis completo de un autor: variantes, duplicados, huecos en series y metadatos faltantes. |

### 6. Metadatos y mantenimiento

| Tool | Descripción |
| :--- | :--- |
| `calibre_fetch_metadata(book_ids, source?, apply?, dry_run?)` | Obtiene metadata desde Open Library o Google Books para los libros indicados. |
| `calibre_embed_metadata(book_ids?, only_formats?)` | Incrusta la metadata de la DB en los archivos (EPUB, AZW3, etc.). |
| `calibre_verify_file_integrity(book_ids?)` | Verifica que todos los archivos de formato referenciados existan en disco. |
| `calibre_bulk_set_metadata(updates, dry_run?)` | Aplica cambios de metadata a múltiples libros en una sola llamada. |
| `calibre_fix_author_sort(limit?, dry_run?)` | Sincroniza `books.author_sort` con los `sort` de los autores vinculados. |
| `calibre_fix_book_paths(book_ids?, batch_size?, offset?)` | Renombra directorios en disco para coincidir con author/title de la DB. |
| `calibre_fix_series_numbers(series_id, assignments, dry_run?)` | Corrige la numeración de una serie asignando índices específicos. |
| `calibre_cleanup_orphan_links(dry_run?)` | Elimina entradas huérfanas en tablas de enlace. |
| `calibre_backup_database(suffix?)` | Copia de seguridad completa de `metadata.db`. |
| `calibre_vacuum_database()` | Compacta la DB tras operaciones masivas (requiere Calibre cerrado). |
| `calibre_export_catalog(output_file?, fields?)` | Exporta el catálogo a CSV, XML, EPUB o MOBI. |
| `calibre_generate_report()` | Reporte integral: estadísticas, grupos de duplicados, ghost books y metadata faltante. |

### 7. Búsqueda full-text (FTS)

| Tool | Descripción |
| :--- | :--- |
| `calibre_fts_index(action?)` | Gestiona el índice full-text (reindex). |
| `calibre_fts_search(query, limit?)` | Búsqueda full-text dentro del contenido de los libros. |

---

## Configuración opcional

- `.env` (copia de `.env.example`): `DOWNLOAD_DIR`, `DEFAULT_LANGUAGE`, `DEFAULT_FORMAT`, `CALIBRE_LIBRARY`, `DEVICE_FORMAT`, `DEVICE_PATH`, etc.
- `config.yaml`: mirrors, idioma/formato por defecto, delays, CDP y bloque `calibre:`.

## Primera vez (qué es normal)

- La primera búsqueda o descarga abre una **ventana de Chrome/Edge** con un **perfil dedicado** (`.chrome-profile/`), separada de tu navegador normal. Es necesaria: DDoS-Guard se verifica solo ahí (~5–8 s). **No la cierres** durante una descarga; al terminar queda abierta a propósito (el tool nunca mata el navegador) y puedes cerrarla a mano.
- Windows Firewall puede pedir permiso para Chrome/puerto 9333: **permitir**.
- Los libros quedan en `downloads/<Autor>/<Título>.<ext>` (o `downloads/<Serie>/Book NN - <Título>.<ext>` si es serie).
- **Expulsa el Kindle de forma segura** antes de desconectarlo tras un envío.

## Estructura del proyecto

```
AutoBook/
├── README.md
├── opencode.json            # registro del MCP server (opencode)
├── install.bat              # instalador automático (Windows)
├── requirements.txt
├── .env.example             # DOWNLOAD_DIR, mirror, calibre…
├── config.yaml              # mirrors, idioma/formato, delays, CDP, calibre
├── LICENSE                  # MIT
├── docs/
│   ├── instalacion-ai.md    # ★ prompts listos para que la IA instale el proyecto
│   ├── calibre.md           # integración con Calibre y envío a Kindle/Kobo
│   ├── arquitectura.md      # componentes y flujo de datos
│   ├── anti-bot.md          # estrategia anti-detección (DDoS-Guard + Chrome/CDP)
│   └── uso-opencode.md      # prompts de ejemplo y buenas prácticas
└── autobook/
    ├── config.py            # carga config.yaml + .env (incluye bloques batch/jobs/calibre)
    ├── mirrors.py           # rotación y health check de mirrors
    ├── search.py            # búsqueda con curl_cffi + Chrome/CDP + parseo (básica y avanzada)
    ├── browser.py           # BrowserSession: lanza Chrome/Edge real (CDP) y lo conduce por Playwright; slow download + fallback Z-Library
    ├── downloader.py        # pipeline descarga -> Calibre -> dispositivo (jobs en segundo plano, cola, retry/cancel)
    ├── organize.py          # saneado de nombres, normalización de autores y sorts
    ├── calibre.py           # calibredb/ebook-convert: importar a biblioteca y enviar al dispositivo
    ├── calibre_mcp.py       # CalibreMCP: 38 tools de gestión de biblioteca (búsqueda, metadatos, limpieza, reportes)
    └── server.py            # FastMCP: expone las 50 tools (descarga + Calibre)
```

## Limitaciones conocidas

- La ruta gratis es **lenta** (~1 a 10 min por libro, cola por IP). Si algún día quieres la API key (donación ~US$5 → descargas rápidas sin cola), el diseño lo admite añadiendo un `Downloader` alternativo.
- Los mirrors caen y cambian de dominio seguido. `check_mirrors()` y la rotación en `mirrors.py` ayudan; revisa [open-slum.org](https://open-slum.org/) para la lista vigente.
- Selectores HTML marcados como volátiles: valídalos contra el sitio real la primera vez (ver `docs/uso-opencode.md`).
- El envío por MTP usa el Shell de Windows: el archivo puede tardar unos segundos en aparecer en el dispositivo.

## Extensión: usar un navegador distinto

Auto-detecta Chrome y luego Edge. Para forzar otro: `browser.binary` en `config.yaml` o `BROWSER_BINARY` en `.env`.
