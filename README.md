# AutoBook

Agente de descarga de libros desde **Anna's Archive** controlado por IA a través de **opencode** o **Claude Code** (terminal o **app de escritorio**). Le das un título (y opcionalmente idioma/formato) y la IA busca, filtra, descarga y guarda el libro organizado en tu PC.

Funciona por la vía **gratuita** (`slow download`), sin donación ni API key. Usa una ventana de **Chrome real** (tu navegador, lanzado con debugging remoto y un perfil dedicado) para superar automáticamente la protección **DDoS-Guard** sin captchas. El tool **nunca cierra tu navegador**: tu Chrome/Edge normal queda intacto.

Opcionalmente se integra con **Calibre**: importa el libro descargado a tu biblioteca (con metadatos y portada), y lo envía a tu **Kindle/Kobo** cuando está conectado (convirtiendo el formato si hace falta). Ver [docs/calibre.md](docs/calibre.md).

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
- **Descarga**: sigue el enlace `/slow_download/…` en el navegador real, hace clic en "Download now" del partner y captura el archivo. También captura la portada de la ficha del libro.
- **Organización**: por defecto `downloads/<Autor>/<Título>.<ext>`; si indicas `series` (opcionalmente `series_index`) guarda `downloads/<Serie>/Book NN - <Título>.<ext>` con nombres coherentes para todos los volúmenes.
- **Calibre (opcional)**: `calibre_add` importa el libro a la biblioteca con `calibredb` (metadatos + portada + identificador, sin duplicados) y `calibre_send_to_device` lo convierte y copia al Kindle/Kobo montado.

## Requisitos

- Windows
- Python 3.10+ ([python.org](https://www.python.org/downloads/), marcar **"Add python.exe to PATH"**)
- **Google Chrome** (por defecto) o **Microsoft Edge** como respaldo (auto-detectados).
- [Claude Code](https://claude.com/claude-code) (terminal o **app de escritorio**) **o** [opencode](https://opencode.ai).
- Opcional para la integración con biblioteca/dispositivo: [Calibre](https://calibre-ebook.com/) instalado.

---

## Instalación fácil en otra PC — Claude Code (app de escritorio) o opencode

La forma más rápida: **descargar, abrir la IA en la carpeta y pegar un prompt**. La propia IA instala, configura y verifica todo. El mismo venv sirve para Claude Code **y** para opencode: si instalas para uno, el otro también queda listo.

### Paso 1 — Consigue el proyecto

Descarga el ZIP desde el repo en GitHub (botón verde **Code → Download ZIP**) o clona con `git clone <url>`. Descomprime y queda una carpeta llamada `AutoBook`.

### Paso 2 — Abre Claude Code en la carpeta y pega este prompt

Abre la **app de escritorio de Claude Code**, selecciona la carpeta `AutoBook` como proyecto y pega el bloque completo de abajo (cópialo tal cual):

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
7. Cuando la IA confirme el reinicio, acepta la aprobación de las tools MCP que pida la app y prueba con: "Usa la tool book_search para buscar 'El Principito' en español, formato epub, y descárgalo esperando a que termine."
```

> **¿Usas opencode en vez de Claude Code? No necesitas pegar nada extra.** El prompt de arriba crea el venv (lo único que falta); el registro del MCP ya viene en `opencode.json` del proyecto. Abre opencode dentro de la carpeta `AutoBook`, reinícialo si hace falta y ejecuta `/mcp` para confirmar que `autobook` está conectado. Si ya instalaste con Claude Code, opencode también queda listo (comparten el mismo venv).

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

## ¿Desde cualquier carpeta o solo dentro del proyecto?

Depende de **dónde registres** el MCP, no del servidor en sí (autobook funciona igual desde cualquier carpeta: resuelve sus rutas contra su propia carpeta; los libros van a `<AutoBook>\downloads` salvo que lo cambies con `set_download_dir`).

- **Solo en la carpeta de AutoBook** (configuración por proyecto, la recomendada para empezar): el MCP se carga solo cuando abres Claude Code u opencode **dentro** de la carpeta `AutoBook`. Es lo que hacen los pasos de arriba (`.mcp.json` para Claude Code, `opencode.json` para opencode).
- **Desde cualquier carpeta** (registro global/usuario): el MCP queda disponible aunque abras la IA en cualquier otro proyecto. Es lo mismo, pero registrado a nivel global con **ruta absoluta**.

### Registrarlo global (desde cualquier carpeta)

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

Luego **reinicia** Claude Code u opencode. Nota: si abres la IA fuera de la carpeta de AutoBook, `install.bat` no es necesario (el venv vive dentro de AutoBook), pero la primera vez hay que haber creado el venv.

---

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
| `book_download(md5, title, author, extension, series, series_index)` | Inicia la descarga en segundo plano; devuelve `job_id`. Con `series` (y `series_index`) guarda con nombres coherentes por volumen. Captura la portada. |
| `get_download_status(job_id)` | Consulta progreso/estado (`queued` / `downloading` / `waiting_captcha` / `done` / `error`), portada y resultado de auto-import a Calibre. |
| `set_download_dir(path)` | Cambia la carpeta de descargas en caliente. |
| `check_mirrors()` | Comprueba qué mirrors están vivos. |
| `session_info()` | Estado del navegador y carpeta de descargas. |
| `calibre_status()` | Estado de la integración: calibredb, biblioteca, GUI abierta, dispositivo montado. |
| `calibre_add(job_id \| path)` | Importa el libro a la biblioteca de Calibre con metadatos/portada; devuelve `book_id` (ver [docs/calibre.md](docs/calibre.md)). |
| `calibre_send_to_device(book_id \| path, format?)` | Envía el libro al Kindle/Kobo montado, convirtiendo si hace falta (por defecto MOBI). |

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
│   ├── calibre.md           # integración con Calibre y envío a Kindle/Kobo
│   ├── arquitectura.md      # componentes y flujo de datos
│   ├── anti-bot.md          # estrategia anti-detección (DDoS-Guard + Chrome/CDP)
│   └── uso-opencode.md      # prompts de ejemplo y buenas prácticas
└── autobook/
    ├── config.py            # carga config.yaml + .env
    ├── mirrors.py           # rotación y health check de mirrors
    ├── search.py            # búsqueda con curl_cffi + Chrome/CDP + parseo
    ├── browser.py           # BrowserSession: lanza Chrome/Edge real (CDP) y lo conduce por Playwright
    ├── downloader.py        # slow_download + jobs en segundo plano + portada + auto-import
    ├── organize.py          # saneado de nombres y rutas
    ├── calibre.py           # calibredb/ebook-convert: importar a biblioteca y enviar al dispositivo
    └── server.py            # FastMCP: expone las tools
```

## Limitaciones conocidas

- La ruta gratis es **lenta** (~1 a 10 min por libro, cola por IP). Si algún día quieres la API key (donación ~US$5 → descargas rápidas sin cola), el diseño lo admite añadiendo un `Downloader` alternativo.
- Los mirrors caen y cambian de dominio seguido. `check_mirrors()` y la rotación en `mirrors.py` ayudan; revisa [open-slum.org](https://open-slum.org/) para la lista vigente.
- Selectores HTML marcados como volátiles: valídalos contra el sitio real la primera vez (ver `docs/uso-opencode.md`).

## Extensión: usar un navegador distinto

Auto-detecta Chrome y luego Edge. Para forzar otro: `browser.binary` en `config.yaml` o `BROWSER_BINARY` en `.env`.
