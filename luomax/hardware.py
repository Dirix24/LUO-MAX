"""Read Linux hardware interfaces and plan reversible driver settings."""
import re
from pathlib import Path

PROFILES = ("equilibrado", "alto", "extremo", "maximo")
POWER_WARNING = "El perfil Extremo puede aumentar el consumo, el ruido y la temperatura."
MAX_WARNING = """⚠️ ATENCIÓN: PERFIL MÁXIMO

Este perfil intenta alcanzar el mayor rendimiento permitido por el hardware y sus controladores.

Puede provocar:

- Temperaturas significativamente más altas.
- Mayor consumo eléctrico.
- Aumento del ruido de ventiladores.
- Reducción de autonomía en portátiles.
- Inestabilidad o apagados de protección.

Se recomienda disponer de una refrigeración adecuada, vigilar las temperaturas de CPU y GPU y evitar sesiones prolongadas si el equipo no está preparado.

Confirma expresamente que comprendes los riesgos."""


def optional(path):
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return None


def read_setting(path):
    value = path.read_text().strip()
    if path.name == "scheduler":
        active = re.search(r"\[([^\s\[\]]+)\]", value)
        if not active:
            raise RuntimeError(f"{path}: no se pudo identificar el planificador activo.")
        return active[1]
    return value


class Hardware:
    def __init__(self, sysfs=Path("/sys"), proc=Path("/proc")):
        self.sysfs = sysfs
        self.proc = proc

    def policies(self):
        return sorted(self.sysfs.glob("devices/system/cpu/cpufreq/policy[0-9]*"))

    def cards(self):
        return sorted(p for p in self.sysfs.glob("class/drm/card*")
                      if re.fullmatch(r"card[0-9]+", p.name))

    def power(self):
        supplies = self.sysfs / "class/power_supply"
        if not supplies.is_dir():
            return "desconocida"
        types = [(p, optional(p / "type")) for p in sorted(supplies.iterdir())]
        external = [optional(p / "online") for p, kind in types if kind in
                    {"Mains", "USB", "USB_C", "USB_PD", "USB_PD_DRP", "Wireless"}]
        if "1" in external:
            return "corriente"
        if any(kind == "Battery" for _, kind in types):
            return "batería o corriente sin verificar"
        if types:
            return "desconocida"
        return "sin batería detectada"

    def gpu_sensors(self, device):
        return sorted(device.resolve().glob("hwmon/hwmon*/temp[0-9]*_input"))

    def package_sensor(self, device):
        if (optional(device / "vendor"), optional(device / "device"), device.resolve().name) != (
            "0x8086", "0x0a16", "0000:00:02.0"
        ):
            return []
        # The Haswell ULT GT2 is part of the same package reported by coretemp.
        packages = []
        for monitor in self.sysfs.glob("class/hwmon/hwmon*"):
            if optional(monitor / "name") == "coretemp":
                for label in monitor.resolve().glob("temp[0-9]*_label"):
                    if (optional(label) or "").startswith("Package id "):
                        packages.append(label.with_name(label.name.replace("_label", "_input")))
        return packages if len(packages) == 1 and packages[0].exists() else []

    def intel_policy(self, card, profile):
        # Only program frequency limits the i915 driver already exposes.
        device = card / "device"
        package = self.package_sensor(device)
        if profile == "alto" or not (self.gpu_sensors(device) or package):
            return {}
        minimum = card / "gt_min_freq_mhz"
        raw = [optional(path) for path in (
            minimum, card / "gt_max_freq_mhz", card / "gt_RP1_freq_mhz", card / "gt_RP0_freq_mhz"
        )]
        if not all(value and value.isascii() and value.isdigit() for value in raw):
            return {}
        current, ceiling, sustained, peak = map(int, raw)
        if not 0 < current <= ceiling <= peak or not 0 < sustained <= peak:
            return {}
        if package:
            floor = optional(card / "gt_RPn_freq_mhz")
            if floor and floor.isascii() and floor.isdigit() and 0 < int(floor) <= current:
                low = int(floor)
                # The Haswell GT frequency interface uses 50 MHz steps.
                divisor = 3 if profile == "extremo" else 2
                cap = min(ceiling, low + (peak - low) // divisor)
                sustained = max(sustained, cap // 50 * 50)
        target = min(ceiling, sustained)
        return {minimum: str(target)} if current < target else {}

    def sensors(self, gpu_devices=()):
        sensors = set()
        cpu_names = {"coretemp", "k10temp", "zenpower", "cpu_thermal"}
        thermal_zones = cpu_names | {"x86_pkg_temp", "cpu", "soc_thermal"}
        for hwmon in sorted(self.sysfs.glob("class/hwmon/hwmon*")):
            if optional(hwmon / "name") in cpu_names:
                sensors.update(hwmon.resolve().glob("temp[0-9]*_input"))
        for zone in sorted(self.sysfs.glob("class/thermal/thermal_zone*")):
            kind = optional(zone / "type") or ""
            if kind.lower().replace("-", "_") in thermal_zones:
                sensors.add(zone.resolve() / "temp")
        if not sensors:
            raise RuntimeError("Sin sensores válidos de CPU o SoC.")
        for device in gpu_devices:
            gpu = self.gpu_sensors(device) or self.package_sensor(device)
            if not gpu:
                raise RuntimeError(f"Sin sensores para la GPU {device}.")
            sensors.update(gpu)
        return sorted(sensors)

    def check(self, sensors, expected_power):
        if expected_power is not None and (
            expected_power not in {"corriente", "sin batería detectada"} or self.power() != expected_power
        ):
            raise RuntimeError("Alimentación insuficiente o sin verificar.")
        if not sensors:
            raise RuntimeError("Sin supervisión térmica.")
        for path in sensors:
            raw = optional(path)
            if not raw or not re.fullmatch(r"-?[0-9]+", raw) or not 0 < int(raw) <= 150000:
                raise RuntimeError(f"Lectura térmica inválida o ausente: {path}.")
            limit = 80000
            if path.name.endswith("_input"):
                critical = optional(path.with_name(path.name.replace("_input", "_crit")))
                if critical and critical.isdigit() and int(critical) > 5000:
                    limit = min(limit, int(critical) - 5000)
            else:
                for kind in path.parent.glob("trip_point_*_type"):
                    if optional(kind) in {"hot", "critical"}:
                        value = optional(kind.with_name(kind.name.replace("_type", "_temp")))
                        if value and value.isdigit() and int(value) > 5000:
                            limit = min(limit, int(value) - 5000)
            if int(raw) >= limit:
                raise RuntimeError(f"{path}: {int(raw) / 1000:g} °C (umbral {limit / 1000:g} °C).")

    def storage_policy(self):
        changes = {}
        for disk in self.sysfs.glob("block/*"):
            if not any(re.fullmatch(r"ata[0-9]+", part) for part in disk.resolve().parts):
                continue
            if optional(disk / "removable") != "0" or optional(disk / "device/type") != "0":
                continue
            scheduler = disk / "queue/scheduler"
            modes = (optional(scheduler) or "").replace("[", "").replace("]", "").split()
            if "mq-deadline" in modes:
                changes[scheduler] = "mq-deadline"
        return changes

    def memory_policy(self):
        swappiness = self.proc / "sys/vm/swappiness"
        value = optional(swappiness) or ""
        if not value.isascii() or not value.isdigit() or not 40 < int(value) <= 100:
            return {}
        if optional(self.sysfs / "module/zswap/parameters/enabled") not in {None, "N"}:
            return {}
        memory = re.search(r"^MemAvailable:\s+(\d+)\s+kB", optional(self.proc / "meminfo") or "", re.M)
        swaps = (optional(self.proc / "swaps") or "").splitlines()[1:]
        if not memory or int(memory[1]) < 2 * 1024 * 1024 or not swaps:
            return {}
        for row in swaps:
            entry = row.split()
            if len(entry) != 5 or entry[1] not in {"file", "partition"} or entry[0].startswith(
                ("/dev/zram", "/dev/ram", "/dev/loop", "/dev/dm-", "/dev/mapper/")
            ):
                return {}
        return {swappiness: "40"}

    def plan(self, profile):
        changes = {}
        gpu_devices = []
        for policy in self.policies():
            governor = optional(policy / "scaling_available_governors") or ""
            if "performance" in governor.split():
                changes[policy / "scaling_governor"] = "performance"
            if profile in {"extremo", "maximo"}:
                preferences = optional(policy / "energy_performance_available_preferences") or ""
                if "performance" in preferences.split():
                    changes[policy / "energy_performance_preference"] = "performance"
        if profile == "maximo":
            cpu = self.sysfs / "devices/system/cpu"
            for relative, target in (("cpufreq/boost", "1"), ("intel_pstate/no_turbo", "0")):
                path = cpu / relative
                if optional(path) in {"0", "1"}:
                    changes[path] = target
        if profile in {"alto", "extremo", "maximo"}:
            for card in self.cards():
                device = card / "device"
                driver = device / "driver"
                path = device / "power_dpm_force_performance_level"
                driver_name = driver.resolve().name
                if driver_name == "i915":
                    candidate = self.intel_policy(card, profile)
                    if candidate:
                        changes.update(candidate)
                        gpu_devices.append(device)
                    continue
                current = optional(path) if driver_name == "amdgpu" else None
                if current in {"auto", "low", "high"} and (
                    profile == "maximo" or current == "low"
                ):
                    changes[path] = "high" if profile == "maximo" else "auto"
                    gpu_devices.append(device)
        if profile in {"extremo", "maximo"}:
            changes.update(self.storage_policy())
            changes.update(self.memory_policy())
        if not changes:
            raise RuntimeError("El equipo no expone ajustes compatibles con este perfil.")
        return changes, gpu_devices

    def status(self):
        cpuinfo = optional(self.proc / "cpuinfo") or ""
        model = re.search(r"^(?:model name|Hardware|Processor)\s*:\s*(.+)", cpuinfo, re.M)
        meminfo = optional(self.proc / "meminfo") or ""
        total = re.search(r"^MemTotal:\s+(\d+)", meminfo, re.M)
        available = re.search(r"^MemAvailable:\s+(\d+)", meminfo, re.M)
        vendors = {"0x8086": "Intel", "0x1002": "AMD", "0x10de": "NVIDIA"}
        gpus = []
        gpu_details = []
        for card in self.cards():
            device = card / "device"
            vendor = optional(device / "vendor")
            driver = device / "driver"
            label = vendors.get(vendor, vendor or (driver.resolve().name if driver.is_symlink() else card.name))
            gpus.append(label)
            driver_name = driver.resolve().name if driver.is_symlink() else "controlador desconocido"
            detail = f"{card.name}: {label} ({driver_name})"
            frequency = optional(card / "gt_cur_freq_mhz")
            busy = optional(device / "gpu_busy_percent")
            if frequency and frequency.isascii() and frequency.isdigit():
                detail += f", {frequency} MHz"
            if busy and busy.isascii() and busy.isdigit() and int(busy) <= 100:
                detail += f", uso {busy} %"
            if driver_name == "i915" and not self.gpu_sensors(device):
                detail += (", sensor térmico del paquete" if self.package_sensor(device)
                           else ", sin sensor térmico compatible")
            minimum = optional(card / "gt_min_freq_mhz")
            if minimum and minimum.isascii() and minimum.isdigit():
                detail += f", mínimo {minimum} MHz"
            gpu_details.append(detail)
        disks = []
        for disk in sorted(self.sysfs.glob("block/*")):
            if "virtual" in disk.resolve().parts:
                continue
            value = optional(disk / "queue/rotational")
            if value in {"0", "1"}:
                kind = "óptico" if optional(disk / "device/type") == "5" else ("HDD" if value == "1" else "SSD")
                disks.append(f"{disk.name} ({kind})")
        temperatures = []
        for pattern in ("class/thermal/thermal_zone*/temp", "class/hwmon/hwmon*/temp[0-9]*_input"):
            for path in self.sysfs.glob(pattern):
                sample = optional(path)
                if sample and sample.isdigit() and 0 < int(sample) <= 150000:
                    temperatures.append(int(sample) / 1000)
        return {
            "cpu": model[1] if model else "Sin modelo disponible",
            "gpu": gpus,
            "gpu_details": gpu_details,
            "ram_gib": round(int(total[1]) / 1048576, 2) if total else None,
            "ram_available_gib": round(int(available[1]) / 1048576, 2) if available else None,
            "storage": disks,
            "storage_scheduler": [
                f"{p.parent.parent.name}: {read_setting(p)}"
                for p in sorted(self.sysfs.glob("block/*/queue/scheduler"))
                if "virtual" not in p.resolve().parts
            ],
            "swappiness": optional(self.proc / "sys/vm/swappiness"),
            "temperature_c": max(temperatures, default=None),
            "power": self.power(),
            "governors": sorted({value for p in self.policies()
                                 if (value := optional(p / "scaling_governor"))}),
        }
