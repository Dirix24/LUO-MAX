import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from luomax.cli import main
from luomax.controller import Controller
from luomax.hardware import Hardware


class Profiles(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.hw = Hardware(self.root / "sys", self.root / "proc")
        self.controller = Controller(self.hw, self.root / "state")
        self.policy = "sys/devices/system/cpu/cpufreq/policy0/"
        self.gov = self.put(self.policy + "scaling_governor", "powersave")
        self.put(self.policy + "scaling_available_governors", "powersave performance")
        self.epp = self.put(self.policy + "energy_performance_preference", "balance_power")
        self.put(self.policy + "energy_performance_available_preferences", "performance balance_power")
        self.boost = self.put("sys/devices/system/cpu/cpufreq/boost", "0")
        self.temp = self.put("sys/class/hwmon/hwmon0/temp1_input", "41000")
        self.put("sys/class/hwmon/hwmon0/name", "coretemp")
        self.put("sys/probe", "1")
        (self.root / "sys/class/power_supply").mkdir()
        self.put("proc/sys/kernel/random/boot_id", "test-boot")
        self.report = []

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n")
        return path

    def start_monitor(self):
        stop = threading.Event()
        ready = threading.Event()
        errors = []

        def report(message):
            self.report.append(message)
            ready.set()

        def monitor():
            try:
                self.controller.daemon(report, stop)
            except Exception as error:
                errors.append(error)
                ready.set()

        thread = threading.Thread(target=monitor)
        thread.start()

        def cleanup():
            stop.set()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])

        self.addCleanup(cleanup)
        self.assertTrue(ready.wait(timeout=5))
        self.assertEqual(errors, [])
        return stop, thread

    def test_inventory(self):
        self.put("proc/cpuinfo", "model name: Test CPU")
        self.put("proc/meminfo", "MemTotal: 4194304 kB\nMemAvailable: 3145728 kB")
        self.put("sys/class/drm/card0/device/vendor", "0x10de")
        self.put("sys/class/drm/card1/device/vendor", "0x1002")
        self.put("sys/class/drm/card0-HDMI-A-1/status", "connected")
        self.put("sys/block/sda/queue/rotational", "1")
        report = self.hw.status()
        self.assertEqual(report["cpu"], "Test CPU")
        self.assertEqual(report["gpu"], ["NVIDIA", "AMD"])
        self.assertEqual(report["ram_gib"], 4)
        self.assertEqual(report["ram_available_gib"], 3)
        self.assertEqual(report["storage"], ["sda (HDD)"])
        self.assertEqual(report["temperature_c"], 41)

    def test_profiles_and_restore(self):
        self.start_monitor()
        self.assertEqual(self.controller.apply("equilibrado"), [])
        for profile, values in (("alto", ("performance", "balance_power", "0")),
                                ("extremo", ("performance", "performance", "0")),
                                ("maximo", ("performance", "performance", "1"))):
            with self.subTest(profile=profile):
                self.controller.apply(profile)
                self.assertEqual(tuple(path.read_text().strip()
                                       for path in (self.gov, self.epp, self.boost)), values)
        self.controller.apply("equilibrado")
        self.assertEqual(self.gov.read_text().strip(), "powersave")
        self.assertEqual(self.epp.read_text().strip(), "balance_power")
        self.assertEqual(self.boost.read_text().strip(), "0")
        self.assertFalse(self.controller.journal.exists())

    def test_maximum_amd_gpu_covered_and_restored(self):
        gpu = self.put("sys/class/drm/card0/device/power_dpm_force_performance_level", "auto")
        (gpu.parent / "driver").symlink_to("/sys/bus/pci/drivers/amdgpu")
        self.start_monitor()
        with self.assertRaisesRegex(RuntimeError, "Sin sensores para la GPU"):
            self.controller.apply("maximo")
        gpu_temp = self.put("sys/class/drm/card0/device/hwmon/hwmon4/temp1_input", "47000")
        self.controller.apply("maximo")
        self.assertEqual(gpu.read_text().strip(), "high")
        gpu_temp.unlink()
        self.controller.guard(self.report.append)
        self.assertEqual(gpu.read_text().strip(), "auto")

    def test_i915_bounds_and_thermal_rollback(self):
        card = "sys/class/drm/card0"
        self.put(f"{card}/device/vendor", "0x8086")
        (self.root / card / "device/driver").symlink_to("/sys/bus/pci/drivers/i915")
        minimum = self.put(f"{card}/gt_min_freq_mhz", "200")
        self.put(f"{card}/gt_max_freq_mhz", "700")
        self.put(f"{card}/gt_RP1_freq_mhz", "800")
        self.put(f"{card}/gt_RP0_freq_mhz", "1000")
        self.assertNotIn(minimum, self.hw.plan("extremo")[0])
        temp = self.put(f"{card}/device/hwmon/hwmon1/temp1_input", "48000")
        self.start_monitor()
        self.controller.apply("extremo")
        self.assertEqual(minimum.read_text().strip(), "700")
        temp.write_text("81000")
        self.controller.guard(self.report.append)
        self.assertEqual(minimum.read_text().strip(), "200")

    def test_profile_monitor_restores_on_exit(self):
        stop = threading.Event()
        observed = []

        def report(message):
            if message.startswith("Perfil alto:"):
                observed.append(self.gov.read_text().strip())
                stop.set()

        self.controller.daemon(report, stop=stop, profile="alto")
        self.assertEqual(observed, ["performance"])
        self.assertEqual(self.gov.read_text().strip(), "powersave")
        self.assertFalse(self.controller.journal.exists())

    def test_hot_sensor_restores_and_never_reactivates(self):
        self.start_monitor()
        self.controller.apply("maximo")
        self.temp.write_text("80000")
        self.controller.guard(self.report.append)
        self.assertEqual(self.gov.read_text().strip(), "powersave")
        self.temp.write_text("41000")
        self.controller.guard(self.report.append)
        self.assertFalse(self.controller.journal.exists())
        self.assertTrue(any("Protección" in entry for entry in self.report))

    def test_hardware_critical_limit_caps_guard(self):
        self.start_monitor()
        self.put("sys/class/hwmon/hwmon0/temp1_crit", "79000")
        self.temp.write_text("74500")
        with self.assertRaisesRegex(RuntimeError, "umbral 74"):
            self.controller.apply("alto")
        self.assertFalse(self.controller.journal.exists())

    def test_requires_monitor_and_valid_sensor(self):
        with self.assertRaisesRegex(RuntimeError, "Inicia primero"):
            self.controller.apply("maximo")
        self.start_monitor()
        self.temp.unlink()
        with self.assertRaisesRegex(RuntimeError, "Sin sensores"):
            self.controller.apply("maximo")
        self.assertFalse(self.controller.journal.exists())

    def test_missing_power_restores_active_maximum(self):
        self.start_monitor()
        self.put("sys/class/power_supply/BAT1/type", "Battery")
        online = self.put("sys/class/power_supply/AC/online", "0")
        self.put("sys/class/power_supply/AC/type", "Mains")
        with self.assertRaisesRegex(RuntimeError, "Alimentación insuficiente"):
            self.controller.apply("maximo")
        online.write_text("1")
        self.controller.apply("maximo")
        online.write_text("0")
        self.controller.guard(self.report.append)
        self.assertEqual(self.boost.read_text().strip(), "0")

    def test_lost_power_telemetry_restores_maximum(self):
        self.start_monitor()
        online = self.put("sys/class/power_supply/AC/online", "1")
        kind = self.put("sys/class/power_supply/AC/type", "Mains")
        self.controller.apply("maximo")
        online.unlink()
        kind.unlink()
        kind.parent.rmdir()
        self.controller.guard(self.report.append)
        self.assertEqual(self.boost.read_text().strip(), "0")

    def test_offline_restore_refuses_running_monitor(self):
        self.start_monitor()
        self.controller.apply("alto")
        with self.assertRaisesRegex(RuntimeError, "Detén el monitor"):
            self.controller.restore(offline=True)
        self.assertEqual(self.gov.read_text().strip(), "performance")

    def test_no_supported_writes(self):
        self.start_monitor()
        self.put(self.policy + "scaling_available_governors", "schedutil")
        with self.assertRaisesRegex(RuntimeError, "ajustes compatibles"):
            self.controller.apply("alto")
        self.assertFalse(self.controller.journal.exists())

    def test_write_permission_failure_rolls_back_and_reports(self):
        self.start_monitor()
        original = self.controller.set_value

        def fail_boost(path, value):
            if path == self.boost and value == "1":
                raise PermissionError("prueba: acceso denegado")
            original(path, value)

        with patch.object(self.controller, "set_value", side_effect=fail_boost):
            with self.assertRaisesRegex(RuntimeError, "revertida: prueba: acceso denegado"):
                self.controller.apply("maximo")
        self.assertEqual(self.gov.read_text().strip(), "powersave")
        self.assertFalse(self.controller.journal.exists())

    def test_failed_restore_keeps_record(self):
        self.start_monitor()
        self.controller.apply("alto")
        self.gov.unlink()
        with self.assertRaisesRegex(RuntimeError, "Restauración incompleta"):
            self.controller.restore()
        self.assertTrue(self.controller.journal.exists())
        self.gov.write_text("performance")
        self.controller.restore()
        self.assertEqual(self.gov.read_text().strip(), "powersave")

    def test_daemon_restores_on_stop(self):
        stop, thread = self.start_monitor()
        self.controller.apply("maximo")
        stop.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.boost.read_text().strip(), "0")
        self.assertFalse(self.controller.journal.exists())

    def test_legacy_backup_untouched(self):
        self.controller.prepare()
        legacy = self.controller.state / "backup.json"
        legacy.write_text("legacy")
        with self.assertRaisesRegex(RuntimeError, "Copia heredada"):
            self.controller.restore()
        self.assertEqual(legacy.read_text(), "legacy")

    def test_record_keeps_intent_and_observed_values(self):
        self.start_monitor()
        self.controller.apply("maximo")
        state = json.loads(self.controller.journal.read_text())
        self.assertEqual(state["settings"][0]["original"], "powersave")
        self.assertEqual(state["settings"][0]["target"], "performance")
        self.assertEqual(state["settings"][0]["observed"], "performance")


class Entrypoints(unittest.TestCase):
    def test_cli_confirmation_and_privilege(self):
        with patch("luomax.cli.Controller.apply") as apply:
            with patch("luomax.cli.os.geteuid", return_value=0):
                self.assertEqual(main(["apply", "maximo"]), 1)
                apply.assert_not_called()
                apply.return_value = []
                self.assertEqual(main(["apply", "maximo", "--confirm-risks"]), 0)
                apply.assert_called_once_with("maximo")
            with patch("luomax.cli.os.geteuid", return_value=1000):
                self.assertEqual(main(["restore"]), 1)

    def test_preview_is_unprivileged_and_cannot_write(self):
        plan = Hardware()
        with patch("luomax.cli.Hardware", return_value=plan), patch("luomax.cli.Controller") as controller:
            with patch.object(plan, "plan", return_value=({Path("/test"): "performance"}, [])):
                with patch.object(plan, "sensors", return_value=[Path("/sensor")]):
                    with patch.object(plan, "check"), patch("luomax.cli.os.geteuid", return_value=1000):
                        self.assertEqual(main(["apply", "alto", "--dry-run"]), 0)
            controller.return_value.apply.assert_not_called()
            controller.return_value.restore.assert_not_called()

    def test_version_is_available_without_privileges(self):
        project = Path(__file__).resolve().parents[1]
        result = subprocess.run([str(project / "luo-max.py"), "--version"], check=True,
                                capture_output=True, text=True)
        self.assertRegex(result.stdout, r"^LUO-MAX \d+\.\d+\.\d+\n$")

    def test_repeat_staged_install_and_uninstall(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as staging:
            stage = Path(staging)
            install = [str(project / "install.sh"), "--systemd", "--destdir", staging]
            uninstall = [str(project / "uninstall.sh"), "--destdir", staging]
            for _ in range(2):
                subprocess.run(install, check=True, capture_output=True, cwd="/")
            executable = stage / "usr/local/bin/luo-max"
            self.assertTrue(executable.is_symlink())
            self.assertEqual(subprocess.run([str(executable), "--help"], capture_output=True).returncode, 0)
            self.assertTrue((stage / "etc/systemd/system/luo-max.service").exists())
            for _ in range(2):
                subprocess.run(uninstall, check=True, capture_output=True, cwd="/")
            self.assertFalse(executable.is_symlink())
            self.assertFalse((stage / "etc/systemd/system/luo-max.service").exists())
            self.assertFalse((stage / "usr/local/lib/luo-max").exists())


if __name__ == "__main__":
    unittest.main()
