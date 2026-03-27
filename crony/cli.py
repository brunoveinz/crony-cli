import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from apscheduler.triggers.cron import CronTrigger
import yaml

from crony import db
from crony import daemon as daemon_module
from crony.i18n import get_translator

t = get_translator()
app = typer.Typer(help="Crony: Local cron job manager")
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    list_jobs: bool = typer.Option(False, "--list", help=t("commands.list")),
):
    """Crony: Local cron job manager"""
    if ctx.invoked_subcommand is not None:
        return
    if list_jobs:
        list()
    else:
        # Show status overview instead of generic help
        _show_status_overview()


@app.command()
def start():
    """Start daemon."""
    try:
        daemon_module.db.ensure_db()
        if daemon_module.is_running():
            pid = daemon_module._read_pid()
            console.print(f"[green]{t('daemon.started', pid=pid)}[/]")
            raise typer.Exit(0)
        pid = daemon_module.start_daemon()
        console.print(f"[green]{t('daemon.started', pid=pid)}[/]")
    except Exception as exc:
        console.print(f"[red]{t('messages.error', error=exc)}[/]")
        raise typer.Exit(1)


@app.command()
def stop():
    """Stop daemon."""
    try:
        daemon_module.stop_daemon()
        console.print(f"[green]{t('daemon.stopped_msg')}[/]")
    except Exception as exc:
        console.print(f"[red]{t('messages.error', error=exc)}[/]")
        raise typer.Exit(1)


@app.command()
def status():
    """Daemon status."""
    try:
        if daemon_module.is_running():
            pid = daemon_module._read_pid()
            console.print(f"[green]{t('daemon.running')}[/]  (pid {pid})")
        else:
            console.print(f"[red]{t('daemon.stopped')}[/]")
    except Exception as exc:
        console.print(f"[red]{t('messages.error', error=exc)}[/]")
        raise typer.Exit(1)


@app.command()
def add(name: str, cron: str, command: str):
    """Add a cron task."""
    try:
        job_id = db.add_job(name, cron, command)
        console.print(f"[green]{t('messages.task_created', id=job_id)}[/]")
    except Exception as exc:
        console.print(f"[red]{t('messages.error', error=exc)}[/]")
        raise typer.Exit(1)


@app.command()
def remove(job_id: int):
    """Remove a task."""
    ok = db.remove_job(job_id)
    if ok:
        console.print(f"[green]{t('messages.task_deleted', id=job_id)}[/]")
    else:
        console.print(f"[yellow]{t('messages.task_not_found', id=job_id)}[/]")


@app.command()
def pause(job_id: int):
    """Pause a task."""
    if db.update_job_enabled(job_id, False):
        console.print(f"[green]{t('messages.task_paused', id=job_id)}[/]")
    else:
        console.print(f"[yellow]{t('messages.task_not_found', id=job_id)}[/]")


@app.command()
def resume(job_id: int):
    """Resume a task."""
    if db.update_job_enabled(job_id, True):
        console.print(f"[green]{t('messages.task_resumed', id=job_id)}[/]")
    else:
        console.print(f"[yellow]{t('messages.task_not_found', id=job_id)}[/]")


@app.command()
def list():
    """List tasks."""
    from rich.text import Text

    jobs = db.list_jobs()
    t_loc = get_translator()
    tbl = Table()
    tbl.add_column(t_loc("tasks.id"), width=4)
    tbl.add_column(t_loc("tasks.name"), width=12)
    tbl.add_column(t_loc("tasks.cron"), width=13)
    tbl.add_column(t_loc("tasks.command"), width=28, overflow="fold")
    tbl.add_column(t_loc("tasks.status"), width=8)
    tbl.add_column(t_loc("tasks.last"), width=16, justify="center")
    tbl.add_column(t_loc("tasks.result"), width=10, justify="center")
    tbl.add_column(t_loc("tasks.duration"), width=8, justify="right")
    for j in jobs:
        last_run = db.get_runs(j["id"], limit=1)
        if last_run:
            run = last_run[0]
            last_exec = run["run_at"][:16]
            result_text = Text(t_loc("tasks.ok"), style="green") if run["success"] == 1 else Text(t_loc("tasks.error"), style="red")
            duration = f"{run['duration']:.1f}s"
        else:
            last_exec = t_loc("tasks.never")
            result_text = Text("-", style="dim")
            duration = "-"
        estado_text = Text(t_loc("tasks.active"), style="green") if j["enabled"] == 1 else Text(t_loc("tasks.paused"), style="yellow")
        tbl.add_row(str(j["id"]), j["name"], j["cron"], j["command"], estado_text, last_exec, result_text, duration)
    console.print(tbl)


@app.command()
def logs(job_id: int, limit: int = 20):
    """Show task logs."""
    from rich.text import Text

    rows = db.get_runs(job_id, limit=limit)
    t_loc = get_translator()
    if not rows:
        console.print(f"[yellow]{t_loc('messages.no_executions', id=job_id)}[/]")
        raise typer.Exit(0)
    for r in rows:
        status_text = Text(t_loc("tasks.ok"), style="green") if r["success"] == 1 else Text(t_loc("tasks.error"), style="red")
        console.print(f"[{r['run_at']}]  {status_text}  {r['duration']:.2f}s")
        if r["stdout"]:
            console.print("[dim]stdout[/]")
            console.print(r["stdout"])
        if r["stderr"]:
            console.print(f"[yellow]{t_loc('tables.stderr')}[/]")
            console.print(r["stderr"])


@app.command("tasks")
def tasks():
    """Show summary of scheduled tasks."""
    from rich.text import Text
    from apscheduler.triggers.cron import CronTrigger
    from datetime import datetime, timezone

    jobs = db.list_jobs()
    t_loc = get_translator()
    total = len(jobs)
    active = sum(1 for j in jobs if j["enabled"] == 1)
    inactive = total - active

    console.print(f"[bold]{t_loc('tasks.scheduled')}[/]")
    console.print(t_loc("tasks.total", total=total, active=active, inactive=inactive))
    console.print()

    if not jobs:
        console.print(f"[yellow]{t_loc('tasks.no_tasks')}[/]")
        return

    tbl = Table()
    tbl.add_column(t_loc("tasks.id"), width=4)
    tbl.add_column(t_loc("tasks.name"), width=14)
    tbl.add_column(t_loc("tasks.next_exec"), width=20, justify="center")
    tbl.add_column(t_loc("tasks.status"), width=10)

    for j in jobs:
        estado_text = Text(t_loc("tasks.active"), style="green") if j["enabled"] == 1 else Text(t_loc("tasks.paused"), style="yellow")
        if j["enabled"] == 1:
            try:
                trigger = CronTrigger.from_crontab(j["cron"])
                next_run = trigger.get_next_fire_time(None, datetime.now(timezone.utc))
                if next_run:
                    next_str = next_run.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    next_str = t_loc("tasks.never")
            except Exception:
                next_str = "Error"
        else:
            next_str = "-"

        tbl.add_row(str(j["id"]), j["name"], next_str, estado_text)

    console.print(tbl)


@app.command("import")
def import_jobs(file_path: str):
    """Import jobs from YAML/JSON file."""
    path = Path(file_path)
    t_loc = get_translator()
    if not path.exists():
        console.print(f"[red]{t_loc('messages.file_not_found', file=file_path)}[/]")
        raise typer.Exit(1)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix.lower() in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif path.suffix.lower() == '.json':
                import json
                data = json.load(f)
            else:
                console.print(f"[red]{t_loc('messages.invalid_format')}[/]")
                raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]{t_loc('messages.error_reading', error=exc)}[/]")
        raise typer.Exit(1)

    services = data.get('services', {})
    if not services:
        console.print(f"[yellow]{t_loc('messages.no_services')}[/]")
        raise typer.Exit(0)

    # Save full config for daemon
    db.DB_DIR.mkdir(parents=True, exist_ok=True)
    with open(db.DB_DIR / "config.yml", 'w', encoding='utf-8') as f:
        yaml.dump(data, f)

    imported = 0
    for name, config in services.items():
        cron = config.get('cron')
        cmd = config.get('cmd')
        enabled = config.get('enabled', True)

        if not cron or not cmd:
            console.print(f"[yellow]{t_loc('messages.incomplete_service', name=name)}[/]")
            continue

        try:
            CronTrigger.from_crontab(cron)
        except Exception as exc:
            console.print(f"[red]{t_loc('messages.invalid_cron', name=name, error=exc)}[/]")
            continue

        job_id = db.add_job(name, cron, cmd)
        if not enabled:
            db.update_job_enabled(job_id, False)

        console.print(f"[green]{t_loc('messages.imported', name=name, id=job_id)}[/]")
        imported += 1

    console.print(f"[green]{t_loc('messages.imports_done', count=imported)}[/]")


def _show_status_overview():
    """Shows a summary of Crony status."""
    running = daemon_module.is_running()
    pid = daemon_module._read_pid() if running else None
    jobs = db.list_jobs()
    active = sum(1 for j in jobs if j["enabled"] == 1)
    paused = len(jobs) - active
    t_loc = get_translator()

    daemon_status = f"[green]{t_loc('daemon.running')}[/]  (pid {pid})" if running else f"[red]{t_loc('daemon.stopped')}[/]"

    console.print()
    console.print(f"[bold]{t_loc('status.title')}[/]")
    console.print()
    console.print(f"  [dim]{t_loc('status.daemon')}[/]    {daemon_status}")
    if jobs:
        console.print(f"  [dim]{t_loc('status.tasks')}[/]     {t_loc('status.active_paused', active=active, paused=paused)}")
    else:
        console.print(f"  [dim]{t_loc('status.tasks')}[/]     {t_loc('status.none_configured')}")
    console.print()
    console.print(f"{t_loc('status.commands')}")
    console.print(f"  crony start                        {t_loc('commands.start').lower()}")
    console.print(f"  crony stop                         {t_loc('commands.stop').lower()}")
    console.print(f"  crony status                       {t_loc('commands.status').lower()}")
    console.print(f"  crony list                         {t_loc('commands.list').lower()}")
    console.print(f"  crony add <name> <cron> <cmd>    {t_loc('commands.add').lower()}")
    console.print(f"  crony config                       {t_loc('config.title').lower()}")
    console.print(f"  crony --help                       full help")
    console.print()


config_app = typer.Typer(help="Interactive continuous menu for configuration")
app.add_typer(config_app, name="config", invoke_without_command=True)


@config_app.callback(invoke_without_command=True)
def config_main(ctx: typer.Context):
    """Main interactive configuration menu."""
    from crony import db
    t_loc = get_translator()

    while True:
        console.rule(f"[bold]{t_loc('config.title')}[/]")
        console.print()
        console.print(f"   1  {t_loc('config.email')}")
        console.print(f"   2  {t_loc('config.show_config')}")
        console.print(f"   3  {t_loc('config.task_status')}")
        console.print(f"   4  {t_loc('config.start_daemon')}")
        console.print(f"   5  {t_loc('config.stop_daemon')}")
        console.print(f"   6  {t_loc('config.add_task')}")
        console.print(f"   7  {t_loc('config.delete_task')}")
        console.print(f"   8  {t_loc('config.view_logs')}")
        console.print(f"   9  {t_loc('config.import_tasks')}")
        console.print(f"  10  {t_loc('config.notif_config')}")
        console.print(f"  11  Change language")
        console.print(f"  12  {t_loc('config.exit')}")
        console.print()

        while True:
            choice = typer.prompt(t_loc('config.option'), default="12")

            if choice == "1":
                _setup_email_interactive()
                break
            elif choice == "2":
                config_show()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "3":
                _show_jobs_status()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "4":
                _start_daemon()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "5":
                _stop_daemon()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "6":
                _add_job_interactive()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "7":
                _remove_job_interactive()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "8":
                _show_job_logs_interactive()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "9":
                _import_jobs_interactive()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "10":
                _update_notify_config_interactive()
                console.print()
                input(t_loc('config.continue'))
                break
            elif choice == "11":
                _change_language_interactive()
                # Re-get translator after language change
                t_loc = get_translator()
                break
            elif choice == "12":
                console.print()
                console.print(t_loc('config.goodbye'))
                return
            else:
                console.print(f"[red]{t_loc('config.invalid_option')}[/]")

        console.print()


@config_app.command()
def setup():
    """Interactive configuration."""
    import typer
    t_loc = get_translator()

    console.print()
    console.print(f"[bold]{t_loc('config.config_title')}[/bold]")
    console.print()
    console.print(f"  1  {t_loc('config.email')}")
    console.print(f"  2  {t_loc('config.show_config')}")
    console.print(f"  3  Disable email")
    console.print()

    while True:
        choice = typer.prompt("Option (1-3)", default="1")
        if choice == "1":
            _setup_email_interactive()
            break
        elif choice == "2":
            config_show()
            break
        elif choice == "3":
            config_disable_email()
            break
        else:
            console.print("[red]Invalid option.[/]")


def _setup_notify_config_interactive():
    """Interactive configuration for when to send notifications."""
    import typer
    t_loc = get_translator()

    console.print()
    console.print(f"[bold]{t_loc('config.notifications')}[/bold]")
    console.print()
    console.print(t_loc("config.notify_on_success"))

    notify_success = typer.confirm(t_loc("config.notify_on_success"), default=True)
    notify_failure = typer.confirm(t_loc("config.notify_on_failure"), default=True)

    return {
        'success': notify_success,
        'failure': notify_failure
    }


def _update_notify_config_interactive():
    """Update notification configuration."""
    config_path = db.DB_DIR / "config.yml"
    t_loc = get_translator()

    if not config_path.exists():
        console.print(f"[yellow]{t_loc('config.no_config')}[/]")
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        if not config.get("notifications", {}).get("email", {}).get("enabled"):
            console.print(f"[yellow]{t_loc('config.email_not_setup')}[/]")
            return

        console.print()
        console.print(f"[bold]{t_loc('config.notifications')}[/bold]")
        console.print()

        # Get current config
        current_notify_on = config.get("notifications", {}).get("email", {}).get("notify_on", {})
        current_success = current_notify_on.get('success', True)
        current_failure = current_notify_on.get('failure', True)

        console.print(t_loc("config.current_config", success=current_success, failure=current_failure))
        console.print()

        notify_on = _setup_notify_config_interactive()

        # Update config
        if "notifications" not in config:
            config["notifications"] = {}
        if "email" not in config["notifications"]:
            config["notifications"]["email"] = {}

        config["notifications"]["email"]["notify_on"] = notify_on

        # Save
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        console.print(f"[green]{t_loc('config.config_saved').replace('[yellow]', '[green]')}[/]")
        console.print(f"  {t_loc('config.configured_success')}: {notify_on['success']}")
        console.print(f"  {t_loc('config.configured_failure')}: {notify_on['failure']}")

    except Exception as e:
        console.print(f"[red]{t_loc('messages.error', error=e)}[/]")


def _setup_email_interactive():
    """Interactive email configuration."""
    import typer
    t_loc = get_translator()

    console.print()
    console.print(f"[bold]{t_loc('config.email')}[/bold]")
    console.print()
    console.print(f"{t_loc('config.provider')}:")
    console.print(f"  1  {t_loc('config.gmail')}")
    console.print(f"  2  {t_loc('config.outlook')}")
    console.print(f"  3  {t_loc('config.yahoo')}")
    console.print(f"  4  {t_loc('config.custom')}")
    console.print()

    while True:
        choice = typer.prompt("Option (1-4)", default="1")
        if choice == "1":
            provider = "gmail"
            break
        elif choice == "2":
            provider = "outlook"
            break
        elif choice == "3":
            provider = "yahoo"
            break
        elif choice == "4":
            provider = "custom"
            break
        else:
            console.print("[red]Invalid option.[/]")

    # Request email
    email = typer.prompt(t_loc("config.enter_email"))

    # Request password
    if provider == "gmail":
        console.print()
        console.print(t_loc("config.gmail_info"))
        console.print(t_loc("config.gmail_link"))
        console.print(t_loc("config.spaces_auto"))
        console.print()
    password = typer.prompt(t_loc("config.enter_password"), hide_input=False)

    # For custom, request server and port
    server = None
    port = None
    if provider == "custom":
        console.print()
        server = typer.prompt(t_loc("config.smtp_server"))
        port = typer.prompt(t_loc("config.smtp_port"), type=int, default=587)

    # Ask for additional recipients
    console.print()
    recipients = None
    add_recipients = typer.confirm(t_loc("config.add_recipients"), default=False)
    if add_recipients:
        recipients = typer.prompt(t_loc("config.recipients_input"))

    console.print()

    # Ask when to notify
    notify_on = _setup_notify_config_interactive()

    # Call configuration function with collected parameters
    _configure_email(provider, email, password, server, port, recipients, notify_on)


@config_app.command("email")
def config_email(
    provider: str = typer.Option(None, help="Provider: gmail, outlook, yahoo, custom"),
    email: str = typer.Option(None, help="Your email address"),
    password: str = typer.Option(None, help="App password (Gmail) or normal password (spaces removed automatically)"),
    server: str = typer.Option(None, help="SMTP Server (custom only)"),
    port: int = typer.Option(None, help="SMTP Port (custom only)"),
    recipients: str = typer.Option(None, help="Additional emails separated by comma"),
):
    """Configure email notifications (advanced mode). Sends test email when done."""
    t_loc = get_translator()

    # If no required parameters provided, use interactive mode
    if not email or not password:
        console.print(f"[yellow]Incomplete parameters. Using interactive mode...[/yellow]")
        console.print()
        _setup_email_interactive()
        return

    # Direct configuration with parameters
    _configure_email(provider or "gmail", email, password, server, port, recipients, None)


def _clean_password(password: str, provider: str) -> str:
    """Limpia la contraseña removiendo espacios y caracteres extra."""
    cleaned = password.strip()
    
    # Para Gmail, remover espacios automáticamente (las app passwords vienen con espacios)
    if provider == "gmail":
        cleaned = cleaned.replace(" ", "")
    
    return cleaned


def _show_jobs_status():
    """Show status of jobs."""
    from crony import db
    from rich.text import Text
    t_loc = get_translator()

    jobs = db.list_jobs()

    if not jobs:
        console.print(f"[yellow]{t_loc('tasks.no_tasks')}[/]")
        return

    table = Table()
    table.add_column("ID")
    table.add_column(t_loc("tasks.name"))
    table.add_column(t_loc("tasks.status"))
    table.add_column(t_loc("tasks.last"))
    table.add_column(t_loc("tasks.result"))

    for job in jobs:
        status_text = Text(t_loc("tasks.active"), style="green") if job["enabled"] == 1 else Text(t_loc("tasks.paused"), style="yellow")
        runs = db.get_runs(job["id"], limit=1)
        if runs:
            last_run = runs[0]
            last_time = last_run["run_at"][:16]  # YYYY-MM-DD HH:MM
            result_text = Text(t_loc("tasks.ok"), style="green") if last_run["success"] == 1 else Text(t_loc("tasks.error"), style="red")
        else:
            last_time = t_loc("tasks.never")
            result_text = Text("-", style="dim")

        table.add_row(str(job["id"]), job["name"], status_text, last_time, result_text)

    console.print(table)


def _start_daemon():
    """Start the daemon."""
    t_loc = get_translator()
    try:
        daemon_module.db.ensure_db()
        if daemon_module.is_running():
            pid = daemon_module._read_pid()
            console.print(f"[green]{t_loc('daemon.started', pid=pid)}[/]")
        else:
            pid = daemon_module.start_daemon()
            console.print(f"[green]{t_loc('daemon.started', pid=pid)}[/]")
    except Exception as e:
        console.print(f"[red]{t_loc('messages.error', error=e)}[/]")


def _stop_daemon():
    """Stop the daemon."""
    t_loc = get_translator()
    try:
        if daemon_module.is_running():
            daemon_module.stop_daemon()
            console.print(f"[green]{t_loc('daemon.stopped_msg')}[/]")
        else:
            console.print(f"[yellow]{t_loc('daemon.not_running')}[/]")
    except Exception as e:
        console.print(f"[red]{t_loc('messages.error', error=e)}[/]")


def _add_job_interactive():
    """Add a task interactively."""
    console.print()
    console.print(f"[bold]{t('config.add_task')}[/bold]")
    console.print()

    name = typer.prompt(t("prompts.add_name"))
    cron_expr = typer.prompt(t("prompts.add_cron"))
    command = typer.prompt(t("prompts.add_command"))

    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(cron_expr)
    except Exception as e:
        console.print(f"[red]{t('messages.invalid_cron', error=e)}[/]")
        return

    job_id = db.add_job(name, cron_expr, command)
    console.print(f"[green]{t('messages.task_created_name', name=name, id=job_id)}[/]")


def _remove_job_interactive():
    """Delete a task interactively."""
    jobs = db.list_jobs()
    if not jobs:
        console.print(f"[yellow]{t('messages.no_tasks_to_delete')}[/]")
        return

    console.print()
    console.print(f"{t('tables.available_tasks')}")
    for job in jobs:
        console.print(f"  {job['id']}  {job['name']:15} {job['cron']}")

    job_id = typer.prompt(t("prompts.delete_id"), type=int)

    if any(job["id"] == job_id for job in jobs):
        db.remove_job(job_id)
        console.print(f"[green]{t('messages.task_deleted', id=job_id)}[/]")
    else:
        console.print(f"[yellow]{t('messages.task_not_found', id=job_id)}[/]")


def _show_job_logs_interactive():
    """Show logs of a task interactively."""
    from rich.text import Text

    jobs = db.list_jobs()
    if not jobs:
        console.print(f"[yellow]{t('tasks.no_tasks')}[/]")
        return

    console.print()
    console.print(f"{t('tables.available_tasks')}")
    for job in jobs:
        console.print(f"  {job['id']}  {job['name']}")

    job_id = typer.prompt(t("prompts.view_logs_id"), type=int)

    if any(job["id"] == job_id for job in jobs):
        runs = db.get_runs(job_id, limit=10)
        if runs:
            console.print()
            console.print(f"[bold]{t('tables.last_runs', id=job_id)}[/bold]")
            console.print()
            for run in runs:
                status_text = Text(t("tasks.ok"), style="green") if run["success"] == 1 else Text(t("tasks.error"), style="red")
                time_str = run["run_at"][:19]  # YYYY-MM-DD HH:MM:SS
                console.print(f"  {time_str}  {status_text}  {run['duration']:.2f}s")
                if run["stdout"]:
                    console.print(f"    stdout: {run['stdout'][:80]}{'...' if len(run['stdout']) > 80 else ''}")
                if run["stderr"]:
                    console.print(f"    stderr: {run['stderr'][:80]}{'...' if len(run['stderr']) > 80 else ''}")
        else:
            console.print(f"[yellow]{t('messages.no_executions', id=job_id)}[/yellow]")
    else:
        console.print(f"[yellow]{t('messages.task_not_found', id=job_id)}[/]")


def _import_jobs_interactive():
    """Import jobs from file interactively."""
    file_path = typer.prompt(t("prompts.import_path"))

    if not Path(file_path).exists():
        console.print(f"[red]{t('messages.file_not_found', file=file_path)}[/]")
        return

    try:
        import_jobs(file_path)
    except Exception as e:
        console.print(f"[red]{t('messages.error_importing', error=e)}[/]")


def _change_language_interactive():
    """Interactive language configuration."""
    from crony.i18n import get_supported_languages, set_language
    from crony import db
    import typer
    import yaml
    
    t_loc = get_translator()
    config_path = db.DB_DIR / "config.yml"
    
    console.print()
    console.print(f"[bold]Change Language / Cambiar Idioma[/bold]")
    console.print()
    
    langs = get_supported_languages()
    for i, lang in enumerate(langs, 1):
        console.print(f"  {i}  {lang}")
    console.print()
    
    while True:
        choice = typer.prompt("Option", default="1")
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(langs):
                selected_lang = langs[choice_idx]
                break
            else:
                console.print("[red]Invalid option. / Opción inválida.[/]")
        except ValueError:
            console.print("[red]Invalid option. / Opción inválida.[/]")
            
    # Save to config
    try:
        config = {}
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
                
        config['language'] = selected_lang
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
        # Update current session
        set_language(selected_lang)
        console.print(f"[green]Language changed to {selected_lang}[/]")
    except Exception as e:
        console.print(f"[red]{t_loc('messages.error', error=e)}[/]")


def _configure_email(provider, email, password, server=None, port=None, recipients=None, notify_on=None):
    """Internal function to configure email."""
    password = _clean_password(password, provider)
    t_loc = get_translator()

    db.DB_DIR.mkdir(parents=True, exist_ok=True)
    config_path = db.DB_DIR / "config.yml"

    # Load existing config
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            console.print(f"[yellow]{t_loc('messages.error', error=e)}[/]")

    # Configure based on provider
    if provider == "gmail":
        smtp_config = {
            "server": "smtp.gmail.com",
            "port": 587,
            "username": email,
            "password": password,
            "use_tls": True
        }
    elif provider == "outlook":
        smtp_config = {
            "server": "smtp-mail.outlook.com",
            "port": 587,
            "username": email,
            "password": password,
            "use_tls": True
        }
    elif provider == "yahoo":
        smtp_config = {
            "server": "smtp.mail.yahoo.com",
            "port": 587,
            "username": email,
            "password": password,
            "use_tls": True
        }
    elif provider == "custom":
        if not server or not port:
            console.print(f"[red]For custom provider you need to specify server and port[/]")
            return
        smtp_config = {
            "server": server,
            "port": port,
            "username": email,
            "password": password,
            "use_tls": True
        }
    else:
        console.print(f"[red]Provider '{provider}' not supported. Use: gmail, outlook, yahoo, custom[/]")
        return

    # Configure recipients
    recipient_list = [email]  # Main email is always a recipient
    if recipients:
        additional = [r.strip() for r in recipients.split(",") if r.strip()]
        recipient_list.extend(additional)

    # Update config
    if "notifications" not in config:
        config["notifications"] = {}
    if "email" not in config["notifications"]:
        config["notifications"]["email"] = {}

    email_config = {
        "enabled": True,
        "smtp": smtp_config,
        "recipients": recipient_list
    }

    # Add notify_on if provided
    if notify_on:
        email_config["notify_on"] = notify_on

    config["notifications"]["email"].update(email_config)

    # Save config
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print()
    console.print(f"[green]{t_loc('config.email_configured', provider=provider)}[/]")
    console.print(f"{t_loc('config.recipients', recipients=', '.join(recipient_list))}")

    # Send test email
    console.print()
    console.print(f"{t_loc('config.sending_test')}")
    try:
        from crony.notifications import EmailNotifier
        test_notifier = EmailNotifier({
            "enabled": True,
            "smtp": smtp_config,
            "recipients": recipient_list
        })

        test_subject = t_loc("config.test_subject")
        test_body = t_loc("config.test_body", provider=provider, email=email, datetime=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        test_notifier.send_notification(test_subject, test_body, "Crony")
        console.print(f"{t_loc('config.test_sent')}")
        console.print(f"{t_loc('config.check_inbox', email=email)}")

    except Exception as e:
        console.print(f"{t_loc('config.test_failed', error=e)}")
        console.print(f"{t_loc('config.config_saved')}")


@config_app.command("show")
def config_show():
    """Show current configuration."""
    config_path = db.DB_DIR / "config.yml"
    t_loc = get_translator()

    if not config_path.exists():
        console.print(f"[yellow]{t_loc('config.no_config')}[/]")
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        console.print()
        console.print(f"[bold]{t_loc('config.config_title')}[/]")
        console.print()

        if config.get("notifications", {}).get("email", {}).get("enabled"):
            email_config = config["notifications"]["email"]
            console.print(f"  [dim]email[/]       {t_loc('config.enabled')}")
            console.print(f"{t_loc('config.server_port', server=email_config['smtp']['server'], port=email_config['smtp']['port'])}")
            console.print(f"{t_loc('config.username', username=email_config['smtp']['username'])}")
            console.print(f"{t_loc('config.recipients_msg', recipients=', '.join(email_config['recipients']))}")

            # Show when to notify
            notify_on = email_config.get('notify_on', {})
            notify_success = notify_on.get('success', True)
            notify_failure = notify_on.get('failure', True)
            parts = []
            if notify_success:
                parts.append(t_loc("config.configured_success"))
            if notify_failure:
                parts.append(t_loc("config.configured_failure"))
            notify_str = ", ".join(parts) if parts else t_loc("config.disabled")
            console.print(f"{t_loc('config.notification_email', notify_str=notify_str)}")
        else:
            console.print(f"  [dim]email[/]       {t_loc('config.disabled_msg')}")

        if config.get("services"):
            console.print()
            console.print(f"{t_loc('config.services_configured', count=len(config['services']))}")
            for name, service in config["services"].items():
                status_text = t_loc("config.active_service") if service.get("enabled", True) else t_loc("config.paused_service")
                console.print(f"{t_loc('config.service_status', name=name, cron=service.get('cron', 'N/A'), status=status_text)}")

    except Exception as e:
        console.print(f"[red]{t_loc('messages.error', error=e)}[/]")


@config_app.command("disable-email")
def config_disable_email():
    """Disable email notifications."""
    config_path = db.DB_DIR / "config.yml"
    t_loc = get_translator()

    if not config_path.exists():
        console.print(f"[yellow]{t_loc('config.no_config_modify')}[/]")
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        if "notifications" in config and "email" in config["notifications"]:
            config["notifications"]["email"]["enabled"] = False

            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            console.print(f"[green]{t_loc('config.email_disabled')}[/]")
        else:
            console.print(f"[yellow]{t_loc('config.no_email_config')}[/]")

    except Exception as e:
        console.print(f"[red]{t_loc('messages.error', error=e)}[/]")


if __name__ == "__main__":
    app()
