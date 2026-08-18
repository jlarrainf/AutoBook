# Arquitectura

## Visión general

AutoBook es un **servidor MCP local** escrito en Python que expone herramientas de búsqueda y descarga de libros a la IA de opencode. La IA es quien orquesta: interpreta tu petición en lenguaje natural, decide qué tools llamar y en qué orden, y te reporta el resultado.

No hay "agente" propio con LangChain/AutoGen porque **opencode ya es el agente**. Este diseño separa dos responsabilidades:

1. **Decidir** (opencode/LLM): qué libro, en qué idioma y formato, dónde guardarlo.
2. **Ejecutar** (AutoBook/MCP): navegar, parsear, descargar y organizar archivos.

## Componentes

| Componente | Archivo | Rol |
| :--- | :--- | :--- |
| **Config** | `autobook/config.py` | Carga `config.yaml` + `.env` (prioridad de `.env`). Expone `Config`, `BrowserConfig`, `BehaviorConfig`, `FileConfig`. |
| **Mirrors** | `autobook/mirrors.py` | Mantiene la lista de mirrors, `healthy()` sondea, `primary` es el primero sano. |
| **BrowserSession** | `autobook/browser.py` | Lanza **Chrome real** (o Edge si no hay Chrome) con `--remote-debugging-port` y un **perfil dedicado** (`.chrome-profile/`), lo conecta por **CDP** con Playwright (API async sobre un event-loop propio en un hilo) y expone operaciones de alto nivel: `goto_html`, `get_slow_download_href`, `run_download`. Autoverifica el challenge de DDoS-Guard. `close()` **nunca mata el proceso** del navegador (no cierra tus pestañas). |
| **Searcher** | `autobook/search.py` | HTTP directo con `curl_cffi` contra `/search` (rápido, normalmente 403 por DDoS-Guard) → cae a `goto_html` con el Edge. Parsea los resultados desde `div.js-aarecord-list-outer`. Devuelve `Book` con `md5`. |
| **DownloadManager** | `autobook/downloader.py` | Gestor de jobs en segundo plano. Por cada job: obtiene el href `/slow_download/…` del md5, navega, hace clic en "Download now", captura el download y lo guarda. Reintenta en el siguiente mirror si uno falla. |
| **Organize** | `autobook/organize.py` | Sanea nombres (caracteres ilegales de Windows), crea `downloads/<Autor>/<Título>.<ext>`, resuelve duplicados con sufijo. |
| **Server** | `autobook/server.py` | FastMCP. Expone `book_search`, `book_download`, `get_download_status`, `set_download_dir`, `check_mirrors`, `session_info`. |

## Flujo de datos

```
Petición: "Descarga 'Cien años de soledad' en epub español"
│
├─► book_search("Cien años de soledad", language="es", format="epub")
│     Searcher: GET {mirror}/search?q=...&lang=es&ext=epub   (curl_cffi, 8 s de timeout)
│     → si 403/DDoS-Guard: goto_html({mirror}/search?...) en el Edge real (CDP)
│       → DDoS-Guard se autoverifica (~7 s) → HTML parseado
│     → lista de Book {title, author, language, extension, filesize, year, md5, url}
│     La IA elige el resultado correcto (idioma + formato + mejor edición).
│
├─► book_download(md5, title, author, extension)
│     DownloadManager.submit() → job (hilo daemon) → devuelve job_id al instante
│       job: get_slow_download_href({mirror}/md5/{md5})  → href /slow_download/<md5>/0/0
│            → run_download(href):
│                navega al href → clic en <a> "Download now" (partner)
│                → expect_download → save_as → organize.build_destination(...)
│
├─► get_download_status(job_id)  [polling hasta "done"]
│
└─► done: archivo en downloads/<Autor>/<Título>.epub
```

## Decisiones de diseño

### Por qué Chrome/Edge real vía CDP (y no Camoufox/headless)
Se probaron varias vías contra la protección **DDoS-Guard** de `/search` (no es Cloudflare):
- **Camoufox** (Firefox stealth, headless y con ventana): el "auto-verify" del reto **siempre fallaba** → captcha hCaptcha manual en cada sesión.
- **Edge/Chrome lanzado por Playwright** (con/sin ventana, con parches anti-detección): auto-verify falla igual → la detección no es del fingerprint, es del **método de lanzamiento**.
- **Chrome/Edge real lanzado manualmente con `--remote-debugging-port` y conectado por CDP**: **pasa el reto solo**, sin captcha, incluso en perfil nuevo. `navigator.webdriver=false`.
- **Chrome/Edge real en `--headless=new` manual + CDP**: detectado → falla. El modo headless se nota aunque sea un navegador real.

Conclusión: el único camino fiable es **Chromium con ventana lanzado por el propio tool**. Una ventana queda abierta mientras corre el servidor; es parte del diseño. Por defecto se usa **Chrome** (aislado del Edge del usuario) y se **nunca mata** el proceso al terminar: eso evita cerrar pestañas de la sesión normal del usuario si por cualquier motivo la instancia se compartiera.

### Por qué Playwright async con event-loop propio
Las descargas corren en hilos de fondo y las tools de FastMCP se ejecutan en el threadpool. La API **sync** de Playwright no se puede usar desde un hilo distinto al que creó el navegador (`Cannot switch to a different thread`). `BrowserSession` crea un event-loop de asyncio en un hilo dedicado y ejecuta todas las operaciones ahí (`run_coroutine_threadsafe`). Así búsquedas y descargas conviven sin colisionar.

### Por qué arranque perezoso del navegador
`BrowserSession.start()` solo se llama en la primera operación (`goto_html`/`get_slow_download_href`/`run_download` se auto-inician). El Edge y su ventana no aparecen hasta que de verdad hacen falta.

### Por qué búsqueda con `curl_cffi` primero
Es barato y sin ventanas. Hoy DDoS-Guard lo bloquea siempre (403) y cae al Edge; si algún día se suaviza, la búsqueda vuelve a ser instantánea sin cambiar nada.

### Por qué perfil persistente de navegador
`.chrome-profile/` conserva las cookies de clearance de DDoS-Guard y aísla la sesión del tool de tu navegador normal. Aunque cada navegación del reto se autoverifica igual, con perfil la verificación suele ser más corta y no re-aparece en pestañas nuevas.

### Por qué no se mata el proceso al cerrar
`close()` solo desconecta Playwright. El proceso del navegador queda vivo (ventana del perfil dedicado, `about:blank`). Matarlo con `TerminateProcess` fue la causa de un bug real: cerraba las pestañas del navegador del usuario. Si quieres cerrarlo, cierra tú la ventana del perfil dedicado (no afecta a tu Chrome/Edge).

### Por qué jobs en segundo plano
La descarga gratis puede tardar minutos (cola por IP). Una tool MCP síncrona bloquearía la sesión de opencode. `book_download` devuelve un `job_id` inmediato y `get_download_status` hace polling.

### Por qué reintentar por mirror
Los dominios de Anna's Archive caen/son suspendidos constantemente (`.org` y `.se` cayeron, `.li` se perdió en 2026). Reintentar en el siguiente mirror es barato y mantiene la disponibilidad.

### Reto de mantenimiento: selectores volátiles
Anna's Archive cambia el DOM sin avisar. Los selectores viven en tres sitios:
- `autobook/search.py` → `RESULT_SELECTOR = "div.js-aarecord-list-outer"`, filas `div.border-b`, título = primer `a[href*='/md5/']` con texto, autor = primer `a[href^='/search?q=']`.
- `autobook/browser.py` → `SLOW_DOWNLOAD_SELECTOR = "a[href*='/slow_download/']"` y el clic `a:has-text('Download now')`.

Están concentrados para que ajustarlos sea rápido. Ver `docs/uso-opencode.md` → "Validación inicial".

## Extensiones futuras (sin reescribir)

- **API key (donación ~US$5)**: añadir un `FastDownloader` que use `GET /dyn/api/fast_download.json?md5=…&key=…` (devuelve `download_url` con TTL ~60 s). El MCP no cambia; solo se elige downloader según configuración.
- **Lotes**: un tool `download_list(lista_de_md5)` que encole varios jobs secuencialmente (respeta la cola por IP).
- **Catálogo local**: índice JSON de lo descargado para evitar duplicados.