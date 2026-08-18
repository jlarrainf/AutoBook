# Uso con opencode

Este documento explica cómo pedirle libros a la IA de opencode y cómo validar que todo funciona la primera vez.

## 1. Registro del MCP server

El proyecto ya incluye `opencode.json` con el registro:

```json
{
  "mcp": {
    "autobook": {
      "type": "local",
      "command": [".venv\\Scripts\\python.exe", "-m", "autobook.server"]
    }
  }
}
```

Notas:
- `command` usa el Python del venv del proyecto (`.venv\Scripts\python.exe`) **con `-m autobook.server`** (los imports son relativos, no vale ejecutar `server.py` directamente).
- La ruta es **relativa** a la carpeta del proyecto: abre opencode *dentro* de la carpeta AutoBook.
- La carpeta de descargas por defecto es `downloads/` dentro del proyecto. Para cambiarla, usa el tool `set_download_dir`, o crea un `.env` con `DOWNLOAD_DIR` (gana sobre `config.yaml`), o edita `config.yaml`.

Después de guardar `opencode.json`, reinicia opencode para que cargue el servidor MCP.

## 2. Qué verás (y qué es normal)

- La **primera** operación (búsqueda o descarga) abre una **ventana de Chrome/Edge** con un perfil dedicado (`.chrome-profile/`). Es necesaria: DDoS-Guard se verifica solo en ese navegador real con ventana (~5–8 s). **No la cierres** mientras uses AutoBook.
- Esa ventana **queda abierta** al terminar (el tool nunca mata el proceso del navegador, para no cerrarte tus pestañas). Puedes cerrarla tú a mano; la próxima vez se vuelve a abrir.

## 3. Validación inicial (una vez)

1. En opencode, pide:
   > "Usa la tool `check_mirrors` y dime qué mirrors de Anna's Archive están vivos."
2. Pide una búsqueda:
   > "Usa `book_search` para buscar 'Cien años de soledad' en español y formato epub. Muéstrame los resultados con su md5."
3. Haz una **descarga de prueba** de una obra de dominio público (por ejemplo una edición de *El Principito*):
   > "Descarga 'El Principito' en epub y en español, espera a que termine con `get_download_status` y dime dónde quedó."

**Si `book_search` devuelve vacío o títulos raros**, el DOM de Anna's Archive cambió. Ajusta los selectores en `autobook/search.py` (`_parse`) comparando con el HTML real: abre `https://annas-archive.gl/search?q=test&lang=es&ext=epub` en tu navegador e inspecciona.

## 4. Prompts de ejemplo

**Búsqueda + descarga en un paso:**
> "Descarga 'Cien años de soledad' de Gabriel García Márquez en epub y en español. Búscalo, elige el resultado correcto, descárgalo y dime dónde quedó guardado."

**Control explícito de idioma y formato:**
> "Busca 'La sombra del viento' en formato PDF, idioma español. Prefiero una edición reciente. Descarga la mejor opción y guárdala."

**Carpeta diferente:**
> "Cambia la carpeta de descargas a D:\Libros usando `set_download_dir` y luego descarga 'Metamorphosis' de Kafka en inglés, epub."

**Varios libros (uno a la vez, para respetar la cola):**
> "Descarga estos tres libros en epub español, uno tras otro, esperando que cada uno termine antes de empezar el siguiente: [títulos]."

**Diagnóstico de un fallo:**
> "El libro X no descargó. Revisa `get_download_status` del job y dime el error."

## 5. Flujo de polling (cómo lo maneja la IA)

`book_download` devuelve `job_id` inmediatamente. La IA debe llamar `get_download_status(job_id)` en bucle hasta ver `status: done` o `error`. Estados:

| status | Qué significa |
| :--- | :--- |
| `queued` | Esperando que el hilo arranque. |
| `downloading` | Descargando (puede tardar minutos; hay cola por IP). |
| `waiting_captcha` | DDoS-Guard no se autoverificó y pide verificación humana. |
| `done` | Listo; `dest` tiene la ruta del archivo. |
| `error` | Falló en todos los mirrors; `error` tiene el detalle. |

## 6. Buenas prácticas

- **Descargas secuenciales**: la cola de `slow_download` es por IP; lanzar varios libros a la vez solo los enlentece. Pide "uno tras otro".
- **Preferir ediciones verificadas**: si un resultado tiene tamaño sospechosamente pequeño para el formato, descártalo.
- **Idioma de resultado**: la tool ya filtra por `lang`, pero verifica que el `language` del resultado coincida con lo pedido (a veces el índice etiqueta mal).
- **No tocar la ventana del perfil dedicado**: si la cierras a mitad de una descarga, el job puede fallar. Al terminar puedes cerrarla sin problema.

## 7. Troubleshooting rápido

| Problema | Solución |
| :--- | :--- |
| El MCP no aparece en opencode | Reinicia opencode; revisa que `opencode.json` tenga JSON válido y que la ruta del venv exista. |
| `check_mirrors` da todo falso | Estás bloqueado o sin internet; revisa VPN/proxy. Los mirrors cambian seguido. |
| Búsqueda vacía | Selectores desactualizados → ajusta `autobook/search.py`; o el libro no existe en ese idioma/formato. |
| El job queda en `error` con "enlace slow_download no encontrado" | Ese registro no tiene descarga disponible; prueba otro resultado. |
| Descarga en `waiting_captcha` | Mira la ventana del navegador y resuelve el hCaptcha si apareció. |
| Todo tarda muchísimo | Normal: la cola gratis es lenta. Aumenta `slow_download_timeout_min` en `config.yaml` si se corta antes de terminar. |