# Estrategia anti-detección

Anna's Archive usa **DDoS-Guard** (no Cloudflare) delante de `/search` y de las páginas de descarga. Este documento resume qué nos detectan, por qué el enfoque actual funciona y qué hacer si algo cambia.

## Hallazgos (validados en agosto 2026)

La protección de `/search` es **DDoS-Guard**: un reto JS que "verifica tu navegador" (~7 s) y, si falla, muestra un captcha **hCaptcha** en un iframe. Se probaron estas vías:

| Vía | Resultado |
| :--- | :--- |
| `curl_cffi` (HTTP, impersona Chrome) | **403** siempre. El reto es JS, no TLS. |
| Camoufox (Firefox stealth) headless o con ventana | El auto-verify **siempre falla** → hCaptcha manual en cada sesión nueva. |
| Edge/Chrome lanzado por Playwright (`channel=msedge`), headless o con ventana, con parches (`--disable-blink-features=AutomationControlled`, `navigator.webdriver=false`, etc.) | Auto-verify **siempre falla**. |
| **Chrome/Edge real lanzado manualmente** (`chrome.exe --remote-debugging-port=9333 --user-data-dir=...`) + **Playwright connect_over_cdp** | **Pasa el reto solo**, sin captcha, incluso con perfil nuevo. `navigator.webdriver=false`. |
| Chrome/Edge real en `--headless=new` + CDP | **Detectado** → auto-verify falla. El modo headless se nota. |

**Conclusión**: la detección no es de fingerprint TLS ni de `navigator.webdriver`, es del **método de lanzamiento**. Un Chromium real con ventana lanzado como proceso normal (con debugging remoto, que no deja huella en la página) pasa el reto automáticamente. No hace falta ningún navegador stealth ni resolver captchas.

## Arquitectura resultante

```
opencode → FastMCP tool → BrowserSession
                             │ lanza: chrome.exe --remote-debugging-port=9333 --user-data-dir=.chrome-profile
                             │ conecta: Playwright async connect_over_cdp
                             ▼
                     Chrome/Edge REAL con ventana (perfil PROPIO)
                        · DDoS-Guard se autoverifica solo
                        · cookies de clearance persistidas
```

- Por defecto usa **Chrome** (detectado automáticamente); si no está, cae a **Edge**. Puedes forzarlo con `browser.binary` en `config.yaml` o `BROWSER_BINARY` en `.env`.
- Usa un **perfil dedicado** (`.chrome-profile/`): el navegador del tool es una instancia aparte y **no toca** tu Chrome/Edge normal.
- **El tool NUNCA mata el proceso del navegador.** Al terminar solo cierra la conexión Playwright. El cierre de la ventana del perfil dedicado (a mano, por ti) no afecta a tus pestañas. Esto es deliberado: si el proceso compartiera instancia con tu navegador, un `kill` te cerraría todas las pestañas (eso pasó con una versión anterior usando `proc.kill()` y se eliminó).

## Reglas de oro

1. **No uses** `requests`/`httpx`/`urllib` contra el sitio (TLS detectado). Para HTTP, solo `curl_cffi` con `impersonate="chrome"` — y asume que `/search` le dará 403 y caerá al navegador.
2. **Reutiliza** la misma sesión de navegador y el mismo perfil. No abras un navegador nuevo por libro (el tool ya lo hace: arranque perezoso, una sola instancia, y reutiliza el puerto si ya está vivo).
3. **No pongas `headless: true`** ni `HEADLESS=true`: el reto de DDoS-Guard falla y salta el captcha manual. El navegador debe ir con ventana.
4. **Respeta los tiempos**: si el sitio se pone lento o devuelve cola, no aceleres; aumenta los delays en `config.yaml`.
5. **Sin paralelismo**: una descarga a la vez. La IP paga caro el paralelismo.
6. **Concentra los selectores**: si cambia el DOM, ajusta `autobook/search.py` y `autobook/browser.py` en vez de meter parches dispersos.

## El reto de DDoS-Guard (qué hace el tool)

1. `BrowserSession._wait_ready()` espera mientras el título de la pestaña sea `DDoS-Guard…` o `Loading https://…` (fases del reto).
2. El Chromium real se verifica solo en ~5–8 s y el título cambia al real.
3. Si tras `challenge_timeout_s` (120 s por defecto) el título sigue siendo `DDoS-Guard…`, lanza `NeedsCaptchaError`: revisa la ventana abierta, puede haber un hCaptcha manual.

En la práctica el reto **siempre se resuelve solo**. El flujo de captcha manual es solo un seguro.

## Mantenimiento preventivo

- **Lista de mirrors**: consulta [open-slum.org](https://open-slum.org/) para ver cuáles están vivos; actualiza `config.yaml` o usa `check_mirrors` para diagnóstico.
- **Selectores volátiles** (donde viven):
  - `autobook/search.py` → `_parse()`: contenedor `div.js-aarecord-list-outer`, filas `div[class*='border-b']`, título = primer `a[href*='/md5/']` con texto, autor = primer `a[href^='/search?q=']`, idioma/formato/tamaño en la línea `Spanish [es] · EPUB · 0.5MB · 2022`.
  - `autobook/browser.py` → `SLOW_DOWNLOAD_SELECTOR = "a[href*='/slow_download/']"` y clic en `a:has-text('Download now')` (página "Download from partner website").
- Si un libro "no aparece" pero existe en la web normal: revisa que `lang`/`ext` estén bien, y que el mirror usado devuelva resultados (abre `{mirror}/search?q=...` en tu navegador para comparar). Algunos registros **no tienen descarga** (la página del md5 no muestra ninguna opción) → el job acaba en `error` con "enlace slow_download no encontrado".

## Plan B (si DDoS-Guard o el DOM se vuelven inmanejables)

1. **Donación mínima** (~US$5, tier "Bookworm") → API key → `fast_download.json` devuelve `download_url` firmado con TTL ~60 s, sin cola. Se implementa como un `Downloader` alternativo (ver `docs/arquitectura.md` → Extensiones).
2. **Revisar el método de lanzamiento**: si DDoS-Guard empieza a retar también al Chromium real con CDP, prueba `--remote-allow-origins=*` en los argumentos de lanzamiento de `browser.py`, o actualiza el navegador.
3. **Usar un MCP server existente** (`iosifache/annas-mcp`, ~1000★) que ya rota mirrors por SLUM; aunque para descargar igual requiere API key.

## Limitación ética/legal

Esto es una herramienta de automatización, no una garantía de acceso. Úsala con obras de dominio público, licencias abiertas o material que tengas derecho a descargar. No la uses para saltar protecciones en obras con derechos de autor.