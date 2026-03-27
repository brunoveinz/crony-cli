import logging
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from rich.console import Console
import yaml

from crony import db
from crony.notifications import notify_job_completion
from crony.i18n import get_translator

LOG = logging.getLogger("crony.daemon")
PID_PATH = Path.home() / ".crony" / "daemon.pid"
CONFIG_PATH = Path.home() / ".crony" / "config.yml"

console = Console()


def _write_pid(pid: int) -> None:
    db.DB_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(pid), encoding="utf-8")


def _read_pid() -> Optional[int]:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except Exception:
        return None


def _remove_pid_file() -> None:
    try:
        PID_PATH.unlink()
    except FileNotFoundError:
        pass


def is_running() -> bool:
    pid = _read_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class CronEngine:
    def __init__(self, config=None):
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = threading.RLock()
        self.config = config or {}
        self.email_config = self.config.get('notifications', {}).get('email', {})

    def _run_job(self, job_id: int, name: str, command: str, notify_config=None):
        start = datetime.utcnow()
        t = get_translator()
        LOG.info(t("daemon.executing", id=job_id, command=command))
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=3600,
            )
            duration = (datetime.utcnow() - start).total_seconds()
            success = result.returncode == 0

            db.add_run(
                job_id,
                success,
                result.stdout or "",
                result.stderr or "",
                duration,
            )

            # Send email notification
            if self.email_config:
                notify_job_completion(
                    self.email_config,
                    name,
                    success,
                    duration,
                    result.stdout,
                    result.stderr,
                    notify_config
                )

            if success:
                LOG.info(t("daemon.completed_ok", id=job_id))
            else:
                LOG.warning(t("daemon.failed", id=job_id, returncode=result.returncode))
        except Exception as exc:
            duration = (datetime.utcnow() - start).total_seconds()
            db.add_run(job_id, False, "", str(exc), duration)

            # Send email notification for exceptions
            if self.email_config:
                notify_job_completion(
                    self.email_config,
                    name,
                    False,
                    duration,
                    "",
                    str(exc),
                    notify_config
                )

            LOG.exception(t("daemon.exception", id=job_id))

    def _refresh_jobs(self):
        with self._lock:
            self.scheduler.remove_all_jobs()
            jobs = db.list_jobs()
            t = get_translator()
            services_config = self.config.get('services', {})

            for j in jobs:
                if j["enabled"] != 1:
                    continue
                try:
                    trigger = CronTrigger.from_crontab(j["cron"])
                except Exception as exc:
                    LOG.error(t("daemon.invalid_cron", id=j["id"], error=exc))
                    continue

                # Get notification config for this service
                service_config = services_config.get(j["name"], {})
                notify_config = service_config.get('notify')

                self.scheduler.add_job(
                    self._run_job,
                    trigger,
                    args=(j["id"], j["name"], j["command"], notify_config),
                    id=str(j["id"]),
                    name=j["name"],
                    max_instances=1,
                    replace_existing=True,
                )
            LOG.info(t("daemon.polling", count=len(self.scheduler.get_jobs())))

    def start(self):
        self.scheduler.start()
        self._refresh_jobs()
        # poll changes each 30 seg
        while True:
            time.sleep(30)
            self._refresh_jobs()


def run_daemon():
    # Daemon runs in the current process.
    existing_pid = _read_pid()
    if existing_pid and existing_pid != os.getpid() and is_running():
        raise RuntimeError("Daemon is already running")

    current_pid = os.getpid()
    _write_pid(current_pid)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(Path.home() / ".crony" / "daemon.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Load config
    config = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            LOG.warning(f"Could not load config: {e}")

    engine = CronEngine(config)

    def _terminate(signum, frame):
        t = get_translator()
        LOG.info(t("daemon.terminating", signal=signum))
        engine.scheduler.shutdown(wait=False)
        _remove_pid_file()
        sys.exit(0)

    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _terminate)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _terminate)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _terminate)

    db.ensure_db()
    engine.start()


def start_daemon() -> int:
    if is_running():
        raise RuntimeError("Daemon is already running")

    cmd = [sys.executable, "-m", "crony.daemon", "run"]
    if os.name == "nt":
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    return proc.pid


def stop_daemon():
    t = get_translator()
    pid = _read_pid()
    if not pid:
        raise RuntimeError(t("daemon.no_daemon_error"))
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as exc:
        LOG.warning(f"Could not stop daemon: {exc}")
    finally:
        _remove_pid_file()


def status_daemon() -> str:
    return "running" if is_running() else "stopped"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        run_daemon()
    else:
        print("Usage: python -m crony.daemon run")
