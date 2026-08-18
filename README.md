# AutoBook

Agente de descarga de libros desde **Anna's Archive** controlado por IA a través de **opencode** o **Claude Code** (terminal o **app de escritorio**). Le das un título (y opcionalmente idioma/formato) y la IA busca, filtra, descarga y guarda el libro organizado en tu PC.

Funciona por la vía **gratuita** (`slow download`), sin donación ni API key. Usa una ventana de **Chrome real** (tu navegador, lanzado con debugging remoto y un perfil dedicado) para superar automáticamente la protección **DDoS-Guard** sin captchas. El tool **nunca cierra tu navegador**: tu Chrome/Edge normal queda intacto.

> **Nota legal**: Anna's Archive indexa obras con derechos de autor. Usa esta herramienta solo con obras de dominio público, licencias abiertas (Creative Commons, etc.) o material que tengas derecho a descargar.

## Cómo funciona

```
Tú (opencode / Claude Code) ──► IA ──► MCP tools ──► autobook (Python)
                                   │                  ├── book_search  → GET /search (curl_cffi + Chrome vía CDP)
                                   │                  ├── book_download → slow_download (Chrome vía CDP)
                                   │                  └── get_download_status → polling
                                   ▼
                        <DOWNLOAD_DIR>/<Serie>/Book NN - <Título>.epub
```

- **Búsqueda**: primero HTTP directo con `curl_cffi` (impersona Chrome). Como DDoS-Guard lo bloquea, cae a una pestaña del navegador real, que se verifica solo (~7 s) y devuelve el HTML.
- **Descarga**: sigue el enlace `/slow_download/…` en el navegador real, hace clic en "Download now" del partner y captura el archivo.
- **Organización**: por defecto `downloads/<Autor>/<Título>.<ext>`; si indicas `series` (opcionalmente `series_index`) guarda `downloads/<Serie>/Book NN - <Título>.<ext>` con nombres coherentes para todos los volúmenes.

## Requisitos

- Windows
- Python 3.10+ ([python.org](https://www.python.org/downloads/), marcar **"Add python.exe to PATH"**)
- **Google Chrome** (por defecto) o **Microsoft Edge** como respaldo (auto-detectados).
- [Claude Code](https://claude.com/claude-code) (terminal o **app de escritorio**) **o** [opencode](https://opencode.ai).

---

## Instalación fácil en otra PC — Claude Code (app de escritorio)

La forma más rápida: **descargar, abrir la app en la carpeta y pegar un prompt**. La propia IA instala, configura y verifica todo.

### Paso 1 — Consigue el proyecto

Descarga el ZIP desde el repo en GitHub (botón verde **Code → Download ZIP**) o clona con `git clone <url>`. Descomprime y queda una carpeta llamada `AutoBook`.

### Paso 2 — Abre Claude Code en la carpeta y pega este prompt

Abre la **app de escritorio de Claude Code**, selecciona la carpeta `AutoBook` como proyecto y pega:

> Estás en la carpeta del proyecto AutoBook. Instálalo y regístralo como servidor MCP local (stdio) para Claude Code. Haz exactamente esto:
>
> 1. Si no existe la carpeta `.venv`, crea el entorno virtual e instala las dependencias:
>    - `python -m venv .venv`
>    - `.venv\Scripts\python.exe -m pip install -r requirements.txt`
> 2. Comprueba que el servidor arranca:
>    - `.venv\Scripts\python.exe -c "import autobook.server; print('OK')"`
> 3. Obtén la ruta **absoluta** del python del venv y escríbela con doble backslash `\\`. Puedes sacarla con PowerShell: `(Resolve-Path .venv\Scripts\python.exe).Path`.
> 4. Crea el archivo `.mcp.json` en la raíz (si no existe) con este contenido, reemplazando `C:\RUTA\ABSOLUTA\A\AutoBook` por la ruta real:
>
>    ```json
>    {
>      "mcpServers": {
>        "autobook": {
>          "type": "stdio",
>          "command": "C:\\RUTA\\ABSOLUTA\\A\\AutoBook\\.venv\\Scripts\\python.exe",
>          "args": ["-m", "autobook.server"]
>        }
>      }
>    }
>    ```
>
> 5. Verifica que el JSON es válido y que `.mcp.json` está en la raíz.
> 6. Dime que **cierre por completo** la app (icono de la bandeja del sistema → Quit; no basta cerrar la ventana) y la abra de nuevo en esta carpeta.
> 7. Cuando la IA confirme el reinicio, acepta la aprobación de las tools MCP que pida la app y prueba con: *"Usa la tool book_search para buscar 'El Principito' en español, formato epub, y descárgalo esperando a que termine."*

### Paso 3 — Verificar (opcional)

En la app, ejecuta `/mcp` (o revisa el menú de herramientas MCP): debe aparecer `autobook` conectado.

### Alternativa sin IA — comando PowerShell

Si no quieres que lo haga la IA, abre PowerShell **en la carpeta de AutoBook** y pega:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$p = (Resolve-Path .\.venv\Scripts\python.exe).Path.Replace('\','\\')
[System.IO.File]::WriteAllText("$PWD\.mcp.json", '{"mcpServers":{"autobook":{"type":"stdio","command":"' + $p + '","args":["-m","autobook.server"]}}}')
```

Luego cierra del todo la app de Claude Code y vuelve a abrirla en esa carpeta.

> **⚠️ Confusión común**: la app de escritorio de **Claude Code** lee `.mcp.json` (como el CLI). La app de chat **Claude Desktop** es otra cosa: usa el archivo `%APPDATA%\Claude\claude_desktop_config.json` y **no** funciona para esto. Usa siempre **Claude Code**.

---

## Instalación con opencode

1. Descarga el proyecto y descomprime.
2. **Doble clic en `install.bat`** (o el comando manual de abajo).
3. Abre opencode en la carpeta de AutoBook. El MCP ya viene registrado en `opencode.json`; **reinicia opencode** y ejecuta `/mcp` para confirmar que `autobook` está conectado.

> En **`docs/instalacion-ai.md`** hay prompts listos para que la propia IA haga la instalación tanto en opencode como en Claude Code (terminal o app de escritorio), paso a paso y sin que la persona tenga que tocar JSON.

## Instalación manual (cualquier herramienta)

```powershell
cd C:\ruta\a\AutoBook
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No hace falta `playwright install` ni descargar navegadores: se usa el Chrome/Edge instalado.

## Registro manual del MCP

- **opencode**: ya viene registrado en `opencode.json` (comando relativo `.venv\Scripts\python.exe -m autobook.server`).
- **Claude Code** (terminal o app de escritorio): crea `.mcp.json` en la raíz con la **ruta absoluta** del python del venv:

  ```json
  {
    "mcpServers": {
      "autobook": {
        "type": "stdio",
        "command": "C:\\ruta\\absoluta\\a\\AutoBook\\.venv\\Scripts\\python.exe",
        "args": ["-m", "autobook.server"]
      }
    }
  }
  ```

  (El prompt de arriba genera este archivo automáticamente.)

**Primera vez**: la primera búsqueda o descarga abre una **ventana de Chrome/Edge** con un **perfil dedicado** (`.chrome-profile/`), separada de tu navegador normal. Es normal y necesaria. Queda **abierta a propósito** al terminar (el tool nunca mata el proceso del navegador); ciérrala a mano cuando quieras. Windows Firewall puede pedir permiso para Chrome/puerto 9333: permitir.

## Configuración opcional

- `.env` (copia de `.env.example`): `DOWNLOAD_DIR` (carpeta de libros), `DEFAULT_LANGUAGE`, `DEFAULT_FORMAT`, `BROWSER_BINARY`, etc.
- `config.yaml`: mirrors, idioma/formato por defecto, delays y tiempos.

## Herramientas MCP disponibles

| Tool | Descripción |
| :--- | :--- |
| `book_search(query, language, format, limit)` | Busca y devuelve resultados con título, autor, idioma, formato, tamaño y **md5**. |
| `book_download(md5, title, author, extension, series, series_index)` | Inicia la descarga en segundo plano; devuelve `job_id`. Con `series` (y `series_index`) guarda con nombres coherentes por volumen. |
| `get_download_status(job_id)` | Consulta progreso/estado (`queued` / `downloading` / `waiting_captcha` / `done` / `error`). |
| `set_download_dir(path)` | Cambia la carpeta de descargas en caliente. |
| `check_mirrors()` | Comprueba qué mirrors están vivos. |
| `session_info()` | Estado del navegador y carpeta de descargas. |

## Estructura del proyecto

```
AutoBook/
├── README.md
├── opencode.json            # registro del MCP server (opencode)
├── install.bat              # instalador automático (Windows)
├── requirements.txt
├── .env.example             # DOWNLOAD_DIR, mirror…
├── config.yaml              # mirrors, idioma/formato, delays, CDP
├── LICENSE                  # MIT
├── docs/
│   ├── instalacion-ai.md    # ★ prompts listos para que la IA instale el proyecto
│   ├── arquitectura.md      # componentes y flujo de datos
│   ├── anti-bot.md          # estrategia anti-detección (DDoS-Guard + Chrome/CDP)
│   └── uso-opencode.md      # prompts de ejemplo y buenas prácticas
└── autobook/
    ├── config.py            # carga config.yaml + .env
    ├── mirrors.py           # rotación y health check de mirrors
    ├── search.py            # búsqueda con curl_cffi + Chrome/CDP + parseo
    ├── browser.py           # BrowserSession: lanza Chrome/Edge real (CDP) y lo conduce por Playwright
    ├── downloader.py        # slow_download + jobs en segundo plano
    ├── organize.py          # saneado de nombres y rutas
    └── server.py            # FastMCP: expone las tools
```

## Limitaciones conocidas

- La ruta gratis es **lenta** (~1 a 10 min por libro, cola por IP). Si algún día quieres la API key (donación ~US$5 → descargas rápidas sin cola), el diseño lo admite añadiendo un `Downloader` alternativo.
- Los mirrors caen y cambian de dominio seguido. `check_mirrors()` y la rotación en `mirrors.py` ayudan; revisa [open-slum.org](https://open-slum.org/) para la lista vigente.
- Selectores HTML marcados como volátiles: valídalos contra el sitio real la primera vez (ver `docs/uso-opencode.md`).

## Extensión: usar un navegador distinto

Auto-detecta Chrome y luego Edge. Para forzar otro: `browser.binary` en `config.yaml` o `BROWSER_BINARY` en `.env`.
