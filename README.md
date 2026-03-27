# Crony

Crony is a lightweight, cross-platform local cron job manager (macOS, Linux, Windows) with no dependency on `crontab` or `Task Scheduler`.

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

## Architecture

- **Daemon**: Background engine powered by APScheduler (`crony.daemon`).
- **Database**: SQLite `~/.crony/jobs.db` with `jobs` and `job_runs` tables.
- **CLI**: Interactive and intuitive commands built with Typer + Rich in `crony.cli`.

## Installation (Development)

```bash
python -m pip install -e .
```

## Usage

### Status overview (run `crony` without arguments)
```bash
$ crony

Crony

  daemon    stopped
  tasks     1 active, 0 paused

Commands:
  crony start                        start daemon
  crony stop                         stop daemon
  crony status                       daemon status
  crony list                         list tasks
  crony add <name> <cron> <cmd>      add task
  crony config                       interactive configuration
  crony --help                       full help
```

### Daemon

Start daemon:
```bash
crony start
```

Status:
```bash
crony status
```

Stop:
```bash
crony stop
```

Show general help:
```bash
crony --help
```

Add a task manually:
```bash
crony add "backup" "0 3 * * *" "echo hi"
```

Import from file:
```bash
crony import crony.yml
# or
crony import crony.json
```

List tasks:
```bash
crony list
```

Displays a table with ID, name, cron, command, status, last execution, result (ok/error), and duration.

View scheduled tasks:
```bash
crony tasks
```

Shows a summary of total/active/inactive tasks and a table with their next scheduled execution times.

Logs:
```bash
crony logs 1
```

Pause a task:
```bash
crony pause 1
```

Resume a task:
```bash
crony resume 1
```

Remove a task:
```bash
crony remove 1
```

## Configuration File Format

Create a `crony.yml` or `crony.json` file in your project to define services:

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

Then import it:
```bash
crony import crony.yml
crony start
```

## For Project Users

If a project includes a `crony.yml` or `crony.json` file, you can easily automate it:

1. Install crony: `pipx install crony` (or `pip install crony`)
2. Go to the project directory
3. Import tasks: `crony import crony.yml`
4. **Configure email (optional)**: `crony config`
5. Start the daemon: `crony start`
6. List tasks: `crony list`
7. View logs: `crony logs <id>`

### Quick example for developers:

```bash
# Configure Gmail for notifications
crony config

# Import project jobs
crony import crony.yml

# Start daemon and verify
crony start
crony list
crony config show
```

Example `crony.yml` for a Docker project:

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

## Email Notifications

Crony can send HTML-formatted email notifications when your jobs execute. 

### Basic Configuration (Gmail):
```yaml
version: 1
notifications:
  email:
    enabled: true
    smtp:
      server: "smtp.gmail.com"
      port: 587
      username: "youremail@gmail.com"
      password: "your-app-password"
      use_tls: true
    recipients:
      - "youremail@gmail.com"

services:
  scraper:
    cron: "0 9 * * *"
    cmd: "docker compose up"
    notify:
      on_success: true
      on_failure: true
      include_logs: true
```

### For Gmail - App Passwords:
1. Go to your [Google Account Settings](https://myaccount.google.com/)
2. Security → 2-Step Verification → App passwords
3. Generate a new password named "Crony"
4. Use that app password (not your standard password)

## CLI Configuration

To make configuration easier, you can use Crony's built-in commands instead of manually editing YAML files:

### Interactive Configuration (Recommended)

**Step-by-step configuration:**
```bash
crony config
```

This command launches a **continuous interactive menu** where you can:
1. Configure email notifications
2. View current configuration
3. View task statuses
4. Start/Stop the daemon
5. Add/Delete tasks
6. View logs
7. Import tasks
8. Configure when to notify
9. Change Language
10. Exit

After executing any action, **you will automatically return to the menu** to make further changes without needing to run the command again.

**During email configuration**, you'll be asked:
- When to send emails: on success, on failure, or both.
- Whether to include execution logs in the emails.

### Direct Configuration

**For Gmail (easy):**
```bash
crony config email --email youremail@gmail.com --password your-app-password
```

Upon finishing any email configuration, **a test email is automatically sent** to verify that your SMTP credentials work correctly.

**For Outlook/Hotmail:**
```bash
crony config email --provider outlook --email youremail@outlook.com --password your-password
```

**For Yahoo:**
```bash
crony config email --provider yahoo --email youremail@yahoo.com --password your-password
```

**With multiple recipients:**
```bash
crony config email --email youremail@gmail.com --password your-app-password --recipients "other@email.com,team@email.com"
```

### Configuration Management

**View current config:**
```bash
crony config show
```

**Disable notifications:**
```bash
crony config disable-email
```

### Emails you'll receive:
- **Success**: "Crony: task 'scraper' completed" (Green styling)
- **Failure**: "Crony: task 'scraper' failed" (Red styling)
- Both include duration and stdout/stderr depending on your config.

### Other providers:
```yaml
# Outlook/Hotmail
smtp:
  server: "smtp-mail.outlook.com"
  port: 587

# Yahoo
smtp:
  server: "smtp.mail.yahoo.com"
  port: 587

# Your own server
smtp:
  server: "mail.yourdomain.com"
  port: 465
  use_tls: false
```
