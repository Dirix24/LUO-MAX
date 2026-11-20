"""Serialize hardware writes, persist undo records and supervise active profiles."""
import fcntl
import json
import os
import signal
import stat
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path


class Controller:
    def __init__(self, hardware, state=Path("/var/lib/luo-max")):
        self.hardware = hardware
        self.state = state
        self.journal = state / "session.json"

    def prepare(self):
        self.state.mkdir(mode=0o700, exist_ok=True)
        info = self.state.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise RuntimeError(f"Directorio de estado inseguro: {self.state}.")

    def open_lock(self, name):
        return os.fdopen(os.open(self.state / name,
                                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "r+")

    @contextmanager
    def transaction(self):
        self.prepare()
        with self.open_lock("transaction.lock") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def monitor_running(self):
        with self.open_lock("monitor.lock") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            return False

    def boot_id(self):
        return (self.hardware.proc / "sys/kernel/random/boot_id").read_text().strip()

    def sync_directory(self):
        descriptor = os.open(self.state, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def save(self, record):
        with tempfile.NamedTemporaryFile(mode="w", dir=self.state, delete=False) as output:
            temporary = Path(output.name)
            try:
                json.dump(record, output, indent=2)
                output.flush()
                os.fsync(output.fileno())
                os.replace(temporary, self.journal)
                self.sync_directory()
            finally:
                temporary.unlink(missing_ok=True)

    def load(self):
        legacy = self.state / "backup.json"
        if legacy.exists() or legacy.is_symlink():
            raise RuntimeError(f"Copia heredada en {legacy}. Consulta la guía de migración.")
        try:
            descriptor = os.open(self.journal, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor) as source:
            record = json.load(source)
        if record["boot_id"] != self.boot_id():
            raise RuntimeError(f"{self.journal} pertenece a otro arranque. Consulta la guía de recuperación.")
        return record

    def set_value(self, path, value):
        if path.read_text().strip() != value:
            path.write_text(value + "\n")
        actual = path.read_text().strip()
        if actual != value:
            raise RuntimeError(f"{path}: se esperaba {value!r}, el controlador devolvió {actual!r}.")

    def restore_locked(self):
        record = self.load()
        if record is None:
            return []
        errors = []
        restored = []
        for entry in record["settings"]:
            path = Path(entry["path"])
            try:
                self.set_value(path, entry["original"])
                restored.append(entry)
            except (OSError, RuntimeError) as error:
                errors.append(f"{path}: {error}")
        for entry in restored:
            path = Path(entry["path"])
            try:
                if path.read_text().strip() != entry["original"]:
                    errors.append(f"{path}: el valor original cambió durante la restauración.")
            except OSError as error:
                errors.append(f"{path}: {error}")
        if errors:
            raise RuntimeError("Restauración incompleta. Se conserva el diario.\n" + "\n".join(errors))
        self.journal.unlink()
        self.sync_directory()
        return [entry["path"] for entry in restored]

    def restore(self, offline=False):
        with self.transaction():
            if offline and self.monitor_running():
                raise RuntimeError("Detén el monitor LUO-MAX antes de continuar.")
            return self.restore_locked()

    def apply(self, profile):
        if profile == "equilibrado":
            return self.restore()
        with self.transaction():
            if not self.monitor_running():
                raise RuntimeError("Inicia primero el monitor LUO-MAX.")
            existing = self.load()
            if existing:
                self.restore_locked()
            changes, devices = self.hardware.plan(profile)
            sensors = self.hardware.sensors(devices)
            expected_power = self.hardware.power() if profile in {"extremo", "maximo"} else None
            self.hardware.check(sensors, expected_power)
            settings = {}
            for path, target in changes.items():
                path = path.resolve(strict=True)
                settings[path] = {"path": str(path), "original": path.read_text().strip(), "target": target}
                if path.name == "scaling_governor":
                    preference = path.with_name("energy_performance_preference")
                    if preference.exists():
                        settings[preference] = {
                            "path": str(preference), "original": preference.read_text().strip(), "target": None
                        }
            record = {"boot_id": self.boot_id(), "profile": profile,
                      "sensors": [str(path) for path in sensors], "expected_power": expected_power,
                      "settings": list(settings.values())}
            try:
                self.save(record)
                for path, entry in settings.items():
                    if entry["target"] is not None:
                        self.set_value(path, entry["target"])
                self.hardware.check(sensors, expected_power)
                for path, entry in settings.items():
                    entry["observed"] = path.read_text().strip()
                    if entry["target"] is not None and entry["target"] != entry["observed"]:
                        raise RuntimeError(f"{path}: el valor aplicado cambió durante la operación.")
                self.save(record)
            except (OSError, RuntimeError) as error:
                try:
                    self.restore_locked()
                except (OSError, RuntimeError) as rollback:
                    raise RuntimeError(f"Aplicación fallida: {error}\n{rollback}") from error
                raise RuntimeError(f"Aplicación fallida y revertida: {error}") from error
            return [entry["path"] for entry in settings.values()
                    if entry["original"] != entry["observed"]]

    def guard(self, report):
        with self.transaction():
            record = self.load()
            if record is None:
                return
            try:
                self.hardware.check([Path(path) for path in record["sensors"]], record["expected_power"])
            except (OSError, RuntimeError) as error:
                report(f"Protección térmica o eléctrica: {error}")
                self.restore_locked()
                report("Valores originales verificados. El perfil requiere reactivación manual.")

    def daemon(self, report, stop=None):
        if stop is None:
            stop = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stop.set())
        self.prepare()
        with self.open_lock("monitor.lock") as monitor:
            with self.transaction():
                try:
                    fcntl.flock(monitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise RuntimeError("Ya existe un monitor activo.") from error
                self.restore_locked()
            try:
                report("Monitor activo. En espera de selección manual.")
                while not stop.wait(2):
                    self.guard(report)
            finally:
                with self.transaction():
                    try:
                        self.restore_locked()
                    finally:
                        fcntl.flock(monitor, fcntl.LOCK_UN)
