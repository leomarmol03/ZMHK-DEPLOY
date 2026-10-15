# ZMHK 2 · Telegram en Google Colab

Reescritura independiente en Python del despliegue antiguo de Z-Mirror. Ya no depende
de la imagen `dawn001/z_mirror`, de binarios renombrados ni de descargar una rama remota
al iniciar. No es una actualización completa del motor antiguo: el alcance cambió,
como se detalla abajo. Python **3.10+**; CPU suficiente, no necesita GPU.

## Primero: cambia las credenciales antiguas

El repositorio tenía credenciales en un archivo versionado. Se eliminó de la versión
actual, **no del historial**. Antes de ejecutar:

- Revoca el token de Telegram con BotFather y genera uno nuevo.
- Revoca el token de GitHub que se usaba en la URL del upstream.
- Cambia la contraseña del usuario de MongoDB y revisa sus accesos.
- Revisa las credenciales de la aplicación Telegram expuestas (API ID/hash) en
  `my.telegram.org`. La versión nueva no las necesita.

No vuelvas a subir `config.env`, sesiones, cookies ni `rcl.conf`. Los secretos de
Colab son preferibles a escribir tokens en celdas. No publiques salidas con secretos.

## Ejecutar en Colab

[![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/leomarmol03/ZMHK-DEPLOY/blob/arena/44c5e389-zmhk-deploy/ZMHK-Colab.ipynb)

1. Pulsa **Abrir en Colab** en el enlace anterior.
2. Elige un entorno **CPU** y ejecuta las celdas en orden.
3. En la primera celda deja **GitHub** seleccionado: descarga automáticamente el
   código de la rama `arena/44c5e389-zmhk-deploy`, sin necesitar archivos de Arena.
4. En el panel **Secretos** (llave), añade `BOT_TOKEN` y `OWNER_ID` y permite el acceso
   del notebook. Si no los añades, se pedirán mediante entrada oculta.
5. Omite la celda de rclone si no usarás `/mirror`.
6. Ejecuta la última celda y envía `/start` al bot desde la cuenta del dueño.
7. Para detenerlo, interrumpe la última celda. No ejecutes dos instancias con el mismo token.

Si prefieres trabajar sin clonar GitHub o el repositorio es privado, descarga el
notebook y súbelo a Colab mediante **Archivo → Subir notebook**. Selecciona **ZIP**
en la primera celda y sube `ZMHK-Colab.zip`, generado con el comando siguiente.
No introduzcas credenciales de GitHub en el notebook ni en URLs.

El notebook instala un entorno virtual separado: no altera los paquetes de Python
que Colab utiliza. Instala `ffmpeg` y `rclone` con apt. Necesita acceso a internet y
permiso para instalar paquetes en el runtime de Colab.

**Colab no garantiza disponibilidad continua**: puede desconectar o terminar el
runtime; sus discos temporales se pierden al reiniciarlo. Este proyecto no incluye
trucos de keep-alive ni evita los límites o las políticas de Colab. No requiere
Drive, túneles, webhook ni puertos públicos. El notebook no monta Drive automáticamente.

### Si solo tienes el repositorio

Desde esta revisión puedes crear el ZIP localmente:

```bash
python tools/package_colab.py
```

Genera `artifacts/ZMHK-Colab.zip`, con los archivos permitidos únicamente; no empaqueta
archivos privados aunque estén presentes. No uses el ZIP de la rama antigua, porque
no contiene el código nuevo. También puedes ejecutar el bot directamente con los
pasos locales siguientes.

## Comandos y alcance

Solo el dueño (`OWNER_ID`) y los IDs de `AUTHORIZED_USERS` pueden ejecutar comandos.
La autorización se comprueba por usuario, no por chat; las respuestas se envían al
chat donde se hizo la petición. Usa un chat privado para contenido sensible.

| Comando | Función |
| --- | --- |
| `/start`, `/help` | Ayuda |
| `/leech URL` | Descargar un enlace HTTP/HTTPS directo y enviarlo a Telegram |
| `/ytdl URL` | Descargar un único video con yt-dlp y enviarlo a Telegram |
| `/mirror URL` | Descargar un enlace directo y copiarlo al destino rclone |
| `/leech` o `/mirror` respondiendo a un archivo | Procesar un documento, video o audio de Telegram |
| `/status` | Consultar si hay una transferencia activa |
| `/cancel` | Cancelar tu tarea; el dueño también puede cancelar otras |

- Una transferencia a la vez; no hay cola persistente ni reanudación tras reinicios.
- Bot API público: descarga desde Telegram hasta **20 MB**; envío con margen de
  seguridad hasta **49 MB**. Los enlaces HTTP para rclone admiten hasta el límite
  `MAX_DOWNLOAD_MB`. No se prometen subidas de 2/4 GB.
- `/ytdl` selecciona un formato único de video (prioriza MP4); no descarga playlists
  ni sortea DRM, restricciones de cuenta o bloqueos de proveedores. Algunos sitios
  pueden requerir componentes adicionales y no funcionar en Colab.
- Enlaces HTTP directos: usa la última parte de la URL como nombre. No inicia sesión
  en páginas ni convierte páginas HTML en archivos multimedia.
- Archivos temporales aislados por tarea; se borran al terminar, fallar o cancelar
  normalmente. Un apagado forzado del runtime no garantiza ejecutar esa limpieza.
- URLs HTTP(S) públicas, comprobación DNS inicial y en cada redirección HTTP, límites
  de bytes/tiempo, y subprocesos sin shell. No es un proxy endurecido frente a DNS
  rebinding o redirecciones internas de extractores yt-dlp: no lo abras a extraños.
- **No migrado:** torrents/magnets, selección web, MongoDB, RSS, sesiones MTProto,
  cuentas de servicio Drive, división de archivos ni configuración del bot antiguo.
  Para copiar a Drive se usa opcionalmente rclone. Configuraciones antiguas de
  `UPSTREAM_*`, `TELEGRAM_API`, `TELEGRAM_HASH`, `DATABASE_URL` y `BASE_URL` no se usan.

Descarga únicamente contenido que tengas derecho a usar y respeta las condiciones
del proveedor del servicio y de Colab.

## Instalación local

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp config.env.example config.env
# Edita config.env con tus credenciales NUEVAS.
bash start.sh
```

### Configuración

| Variable | Obligatoria / valor predeterminado |
| --- | --- |
| `BOT_TOKEN` | Obligatoria; token nuevo de BotFather |
| `OWNER_ID` | Obligatoria; ID numérico positivo del dueño |
| `AUTHORIZED_USERS` | Opcional; otros IDs separados por comas |
| `DOWNLOAD_DIR` | `downloads` |
| `MAX_DOWNLOAD_MB` | `45` MiB; entre 1 y 2048 |
| `TASK_TIMEOUT` | `1800` segundos; entre 10 y 86400, incluye envío |
| `RCLONE_DESTINATION` | Vacío; ejemplo `drive:Bot` para activar `/mirror` |
| `RCLONE_CONFIG` | Opcional; ruta absoluta al archivo de configuración rclone |

Las variables del entorno tienen prioridad sobre `config.env`. La versión nueva
**no lee configuraciones desde una base de datos ni una URL remota**.

### rclone opcional

Instala rclone y configura un remoto con `rclone config` fuera del notebook, o usa
una configuración ya existente. En Colab ejecuta la celda opcional para subir
`rcl.conf` al almacenamiento temporal del runtime; no se incluye en el ZIP ni en Git.
Establece `RCLONE_DESTINATION=drive:Bot` (sustituye `drive` por tu remoto). Crea la
carpeta de destino y comprueba sus permisos. El archivo contiene credenciales:
no compartas el runtime mientras esté cargado.

### Docker (alternativa, no se usa en Colab)

```bash
docker build -t zmhk .
docker run --rm --env-file config.env zmhk
```

Para usar rclone, monta su configuración con permisos de lectura para el usuario
no privilegiado del contenedor y pasa `RCLONE_CONFIG`. `docker compose up --build`
incluye un montaje de `./rcl.conf` a la ruta estándar de rclone: crea el archivo antes
de usar Compose o elimina ese montaje si no usarás `/mirror`.

## Actualización y pruebas

No hay autoactualizador que borre `.git` o haga `git reset --hard`.
Actualiza manualmente la revisión elegida con `git pull --ff-only` e instala sus
requisitos. Las versiones directas están fijadas en `requirements.txt`.
Para actualizar yt-dlp revisa la versión disponible, cambia el requisito, reinstala
y vuelve a probar: los extractores cambian con frecuencia.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Pruebas locales con HTTP y Telegram simulados; CI configurada para Python
3.10/3.12/3.13. No validan por sí solas la conexión real a Telegram, proveedores de
video o Drive. Es necesario probar eso con credenciales nuevas en Colab.

Se conserva la licencia GPL del proyecto original; consulta `LICENSE`.
