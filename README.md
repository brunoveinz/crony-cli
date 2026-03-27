# Crony

Crony es un gestor local de cron jobs multiplataforma (macOS, Linux, Windows) sin dependencia de `crontab` ni `Task Scheduler`.

## Idiomas / Languages

Crony is now multilingual! By default, Crony runs in **English**. To use Spanish, set the `CRONY_LANG` environment variable:

```bash
# English (default)
crony list

# Spanish
CRONY_LANG=es crony list
```

Supported languages: `en` (English), `es` (Spanish)

---

## Arquitectura

- **Demonio**: motor en segundo plano con APScheduler (`crony.daemon`).
- **Base de datos**: SQLite `~/.crony/jobs.db` con tabla `jobs` y `job_runs`.
- **CLI**: comandos con Typer + Rich en `crony.cli`.

## Instalación (desarrollo)

```bash
python -m pip install -e .
```

## Uso

### Vista de estado (ejecuta `crony` sin argumentos)
```bash
$ crony

Crony

  daemon    detenido
  tareas     1 activas, 0 pausadas

Comandos:
  crony start                        iniciar daemon
  crony stop                         detener daemon
  crony status                       estado daemon
  crony list                         listar tareas
  crony add <nombre> <cron> <cmd>    agregar tarea
  crony config                       configuracion
  crony --help                       ayuda completa
```

### Demonio

Iniciar demonio:
```bash
crony start
```

Estado:
```bash
crony status
```

Detener:
```bash
crony stop
```

Mostrar ayuda general:
```bash
crony --help
```

Agregar tarea manual:
```bash
crony add "backup" "0 3 * * *" "echo hi"
```

Importar desde archivo:
```bash
crony import crony.yml
# ó
crony import crony.json
```

Listar:
```bash
crony list
```

Muestra tabla con ID, nombre, cron, comando, estado, última ejecución, resultado (ok/error), duración.

Ver tareas programadas:
```bash
crony tasks
```

Muestra resumen total/activas/inactivas y tabla con próximas ejecuciones.

Logs:
```bash
crony logs 1
```

Pausar:
```bash
crony pause 1
```

Reanudar:
```bash
crony resume 1
```

Quitar:
```bash
crony remove 1
```

## Formato de archivo de configuración

Crea un archivo `crony.yml` o `crony.json` en tu proyecto para definir servicios:

### YAML (crony.yml)
```yaml
version: 1
services:
  pipeline:
    cron: "0 */2 * * *"
    cmd: "docker compose run --rm pipeline python scraper.py"
    enabled: true
  enrich:
    cron: "30 1 * * *"
    cmd: "docker compose run --rm pipeline python enricher.py"
  outreach:
    cron: "15 8 * * 1-5"
    cmd: "docker compose run --rm pipeline python outreach.py"
```

### JSON (crony.json)
```json
{
  "version": 1,
  "services": {
    "pipeline": {
      "cron": "0 */2 * * *",
      "cmd": "docker compose run --rm pipeline python scraper.py",
      "enabled": true
    },
    "enrich": {
      "cron": "30 1 * * *",
      "cmd": "docker compose run --rm pipeline python enricher.py"
    }
  }
}
```

Luego importa:
```bash
crony import crony.yml
crony --start
```
Agregar tarea:
```bash
crony add "backup" "0 3 * * *" "echo hi"
```

Listar:
```bash
crony list
```

Logs:
```bash
crony logs 1
```

Pausar:
```bash
crony pause 1
```

Reanudar:
```bash
crony resume 1
```

Quitar:
```bash
crony remove 1
```

## Para usuarios de proyectos

Si un proyecto incluye un archivo `crony.yml` o `crony.json`, puedes automatizarlo fácilmente:

1. Instala crony: `pipx install crony` (o `pip install crony`)
2. Ve al directorio del proyecto
3. Importa las tareas: `crony import crony.yml`
4. **Configura email (opcional)**: `crony config email --email tu@email.com --password tu-password`
5. Inicia el demonio: `crony --start`
6. Lista las tareas: `crony list`
7. Ve los logs: `crony logs <id>`

### Ejemplo rápido para desarrolladores:

```bash
# Configurar Gmail para notificaciones
crony config

# Importar jobs del proyecto
crony import crony.yml

# Iniciar y verificar
crony --start
crony list
crony config show
```

Ejemplo de `crony.yml` para un proyecto con Docker:

```yaml
version: 1
services:
  pipeline:
    cron: "0 */2 * * *"
    cmd: "docker compose run --rm pipeline python scraper.py"
  enrich:
    cron: "30 1 * * *"
    cmd: "docker compose run --rm pipeline python enricher.py"
  outreach:
    cron: "15 8 * * 1-5"
    cmd: "docker compose run --rm pipeline python outreach.py"
```

## Notificaciones por Email

Crony puede enviarte notificaciones por email cuando tus jobs se ejecuten. Configura SMTP en `crony.yml`:

### Configuración básica (Gmail):
```yaml
version: 1
notifications:
  email:
    enabled: true
    smtp:
      server: "smtp.gmail.com"
      port: 587
      username: "tuemail@gmail.com"
      password: "tu-app-password"
      use_tls: true
    recipients:
      - "tuemail@gmail.com"

services:
  scraper:
    cron: "0 9 * * *"
    cmd: "docker compose up"
    notify:
      on_success: true
      on_failure: true
      include_logs: true
```

### Para Gmail - App Password:
1. Ve a [Google Account Settings](https://myaccount.google.com/)
2. Security → 2-Step Verification → App passwords
3. Genera un password para "Crony"
4. Usa ese password (no tu contraseña normal)

## Configuración desde CLI

Para facilitar la configuración, puedes usar comandos de Crony en lugar de editar archivos YAML manualmente:

### Configuración Interactiva (Recomendado)

**Configuración paso a paso:**
```bash
crony config
```

Este comando inicia un **menú interactivo continuo** donde puedes:
1. Configurar notificaciones por email
2. Ver configuración actual
3. Estado de tareas
4. Iniciar/Detener daemon
5. Agregar/Eliminar tareas
6. Ver logs
7. Importar tareas
8. Configurar cuándo notificar
9. Salir

Después de cada acción, **regresas automáticamente al menú** para hacer más cambios sin tener que ejecutar el comando nuevamente.

**Durante la configuración de email**, se te preguntará:
- Cuándo enviar emails: éxito, fallo, o ambos
- Si incluir logs en los emails

### Configuración Directa

**Para Gmail (fácil):**
```bash
crony config email --email tuemail@gmail.com --password tu-app-password
```

Al finalizar cualquier configuración, **se envía automáticamente un email de prueba** para verificar que las credenciales SMTP funcionen correctamente.

**Para Outlook/Hotmail:**
```bash
crony config email --provider outlook --email tuemail@outlook.com --password tu-password
```

**Para Yahoo:**
```bash
crony config email --provider yahoo --email tuemail@yahoo.com --password tu-password
```

**Con múltiples destinatarios:**
```bash
crony config email --email tuemail@gmail.com --password tu-app-password --recipients "otro@email.com,equipo@email.com"
```

### Gestión de Configuración

**Ver configuración actual:**
```bash
crony config show
```

**Deshabilitar notificaciones:**
```bash
crony config disable-email
```

### Emails que recibirás:
- **Éxito**: "Crony: tarea 'scraper' completada"
- **Fallo**: "Crony: tarea 'scraper' fallo"
- Incluye duración, stdout/stderr según configuración

### Otros proveedores:
```yaml
# Outlook/Hotmail
smtp:
  server: "smtp-mail.outlook.com"
  port: 587

# Yahoo
smtp:
  server: "smtp.mail.yahoo.com"
  port: 587

# Tu propio servidor
smtp:
  server: "mail.tudominio.com"
  port: 465
  use_tls: false
```
