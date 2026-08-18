# Instalación automática pidiéndosela a la IA

La forma más fácil de usar AutoBook en una PC nueva: **copiar la carpeta, ejecutar `install.bat` una vez y luego pegarle el prompt correspondiente a Claude Code o a opencode**. La propia IA se encarga de configurar el MCP, verificar que funciona y quedarse lista para descargar libros.

Si ya ejecutaste `install.bat`, puedes saltarte los pasos 1–2 de cada prompt (solo pide "verifica que el venv ya está instalado").

---

## Requisitos previos (en la PC destino)

| Requisito | Cómo conseguirlo |
| :--- | :--- |
| Windows | Cualquier versión reciente (10/11). |
| Python 3.10+ | [python.org/downloads](https://www.python.org/downloads/) — al instalar, **marcar "Add python.exe to PATH"**. |
| Google Chrome (o Edge) | Instalado por defecto en Windows (Edge) o descargado (Chrome). Se auto-detecta. |
| opencode **o** Claude Code | Ver abajo según el que use la persona. |

> Para saber qué Python tienes: abre PowerShell y escribe `python --version`. Si no funciona, instala Python y repite.

---

## Instalación en 3 pasos (para cualquier PC)

1. **Descarga y descomprime** el proyecto (zip del release, o `git clone …`). Queda una carpeta `AutoBook`.
2. **Doble clic en `install.bat`** dentro de la carpeta. Crea el entorno virtual, instala dependencias y comprueba que el servidor arranca.
3. Abre **Claude Code** (terminal o **app de escritorio**, abriendo la carpeta como proyecto) u **opencode** *dentro de esa carpeta* y pega el prompt correspondiente (abajo).

> Si usas la **app de escritorio de Claude Code**, usa el prompt de la sección de abajo: crea `.mcp.json` en la raíz y al final hay que **cerrar la app por completo** (bandeja del sistema → Quit) y abrirla de nuevo. Recuerda: Claude Code lee `.mcp.json`; la app de chat **Claude Desktop** no sirve para esto (usa otro archivo de configuración).

---

## Prompt para Claude Code (terminal o app de escritorio)

Abre Claude Code en la carpeta de AutoBook (terminal → `cd C:\ruta\a\AutoBook` → `claude`) y pega esto:

> Estás en la carpeta del proyecto AutoBook. Instálalo y regístralo como servidor MCP para Claude Code siguiendo estos pasos exactos:
>
> 1. Si no existe la carpeta `.venv`, crea el entorno virtual e instala las dependencias:
>    - `python -m venv .venv`
>    - `.venv\Scripts\python.exe -m pip install -r requirements.txt`
> 2. Comprueba que el servidor importa correctamente con:
>    - `.venv\Scripts\python.exe -c "import autobook.server; print('OK')"`
> 3. Si no existe `.mcp.json` en la raíz, créalo con el siguiente contenido (reemplaza `C:\RUTA\ABSOLUTA\A\AutoBook` por la ruta real de esta carpeta, usando doble backslash `\\`):
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
> 4. Confirma la ruta absoluta real del python del venv (puedes usar `Resolve-Path .venv\Scripts\python.exe` en PowerShell).
> 5. Dime que **reinicie Claude Code** y que ejecute `/mcp` para verificar que `autobook` aparece conectado.
> 6. Al reiniciar, que pruebe con: *"Usa la tool book_search para buscar 'El Principito' en español, formato epub, y descárgalo esperando a que termine."*

Notas:
- La primera vez Claude Code pedirá **aprobar** el proyecto y las tools MCP: hay que aceptar.
- No hace falta `playwright install` ni descargar ningún navegador: se usa el Chrome/Edge instalado.

---

## Prompt para opencode

Abre opencode en la carpeta de AutoBook (`cd C:\ruta\a\AutoBook` → `opencode`) y pega esto:

> Estás en la carpeta del proyecto AutoBook. Instálalo y regístralo como servidor MCP para opencode siguiendo estos pasos:
>
> 1. Si no existe la carpeta `.venv`, crea el entorno virtual e instala las dependencias:
>    - `python -m venv .venv`
>    - `.venv\Scripts\python.exe -m pip install -r requirements.txt`
> 2. Comprueba que el servidor importa correctamente con:
>    - `.venv\Scripts\python.exe -c "import autobook.server; print('OK')"`
> 3. Verifica que `opencode.json` existe en la raíz y que registra el MCP `autobook` con `".venv\\Scripts\\python.exe"` y `-m autobook.server`. Si no existe, créalo.
> 4. Dime que **reinicie opencode** (para que cargue el MCP) y que ejecute `/mcp` para verificar que `autobook` aparece conectado.
> 5. Al reiniciar, que pruebe con: *"Usa la tool book_search para buscar 'El Principito' en español, formato epub, y descárgalo esperando a que termine."*

---

## Qué es normal la primera vez

- La primera búsqueda o descarga abre una **ventana de Chrome/Edge** con un **perfil dedicado** (`.chrome-profile/`), separada del navegador normal. Es necesaria: DDoS-Guard se verifica solo ahí (~5–8 s) sin captcha.
- Esa ventana **queda abierta a propósito** al terminar (el tool nunca mata el proceso del navegador, para no cerrar las pestañas del usuario). Se puede cerrar a mano sin problema.
- Windows Firewall puede preguntar por Chrome/puerto 9333: **permitir**.
- Los libros quedan en `downloads/<Serie>/…` (o `<Autor>/…` si no es serie), dentro de la carpeta de AutoBook.

---

## Uso diario (una vez instalado)

Frases que entiende la IA, tanto en opencode como en Claude Code:

| Pedido | Qué hace la IA |
| :--- | :--- |
| "Descarga *Cien años de soledad* en epub y español." | Busca, elige el mejor resultado, descarga y guarda. |
| "Descarga la serie de libros X en epub e inglés, uno tras otro." | Descarga cada volumen con nombres coherentes (`Book 01 - …`, `Book 02 - …`). |
| "Guárdalo en D:\Libros." | Usa `set_download_dir` (o el `DOWNLOAD_DIR` del `.env`). |
| "¿Qué mirrors están vivos?" | Usa `check_mirrors`. |