#!/bin/bash
# Integration on Linux with private mounts and synthetic kernel attributes.
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf -- "$fixture"' EXIT
policy=devices/system/cpu/cpufreq/policy0
sensor=class/hwmon/hwmon0
mkdir -p "$fixture"/{local,lib,units,init} "$fixture/sys/$policy" \
    "$fixture/sys/$sensor" "$fixture/sys/class/power_supply"
printf '%s\n' powersave > "$fixture/sys/$policy/scaling_governor"
printf '%s\n' 'powersave performance' > "$fixture/sys/$policy/scaling_available_governors"
printf '%s\n' balance_power > "$fixture/sys/$policy/energy_performance_preference"
printf '%s\n' 'balance_power performance' > "$fixture/sys/$policy/energy_performance_available_preferences"
printf '%s\n' 0 > "$fixture/sys/devices/system/cpu/cpufreq/boost"
printf '%s\n' coretemp > "$fixture/sys/$sensor/name"
printf '%s\n' 39000 > "$fixture/sys/$sensor/temp1_input"

boot_dirs=()
for level in 0 1 2 3 4 5 6 S; do
    mkdir "$fixture/rc$level.d"
    boot_dirs+=(--bind "$fixture/rc$level.d" "/etc/rc$level.d")
done

# The host is read-only. The only writable system destinations are fixtures.
bwrap --unshare-user --uid 0 --gid 0 --unshare-pid --unshare-net --die-with-parent \
    --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --tmpfs /run \
    --bind "$fixture/local" /usr/local --bind "$fixture/lib" /var/lib \
    --bind "$fixture/sys" /sys --bind "$fixture/units" /etc/systemd/system \
    --bind "$fixture/init" /etc/init.d "${boot_dirs[@]}" \
    --chdir "$project" /bin/bash -s <<'TEST'
set -euo pipefail
governor=/sys/devices/system/cpu/cpufreq/policy0/scaling_governor
boost=/sys/devices/system/cpu/cpufreq/boost
temperature=/sys/class/hwmon/hwmon0/temp1_input
./install.sh --sin-servicio
./install.sh --sin-servicio
./install.sh --destdir /tmp/unit-stage --systemd
if command -v systemd-analyze >/dev/null; then
    systemd-analyze verify --man=no /tmp/unit-stage/etc/systemd/system/luo-max.service
fi
/usr/local/bin/luo-max apply maximo --dry-run
test "$(cat "$boost")" = 0
/usr/local/bin/luo-max status --json | /usr/bin/python3 -m json.tool
/usr/local/bin/luo-max daemon >/tmp/monitor.log 2>&1 &
monitor=$!
trap 'kill -TERM "$monitor" 2>/dev/null || true; wait "$monitor" || true; cat /tmp/monitor.log' EXIT
for i in {1..50}; do
    if grep -q 'Monitor activo' /tmp/monitor.log; then break; fi
    sleep 0.1
done
grep -q 'Monitor activo' /tmp/monitor.log
if /usr/local/bin/luo-max apply maximo; then exit 1; fi
/usr/local/bin/luo-max apply maximo --confirm-risks
test "$(cat "$governor")" = performance
test "$(cat "$boost")" = 1
printf '%s\n' 90000 > "$temperature"
for i in {1..60}; do
    if [[ ! -f /var/lib/luo-max/session.json ]]; then break; fi
    sleep 0.1
done
grep -q 'Protección térmica' /tmp/monitor.log
test "$(cat "$governor")" = powersave
test "$(cat "$boost")" = 0
printf '%s\n' 39000 > "$temperature"
/usr/local/bin/luo-max apply alto
kill -TERM "$monitor"
wait "$monitor"
test "$(cat "$governor")" = powersave
/usr/local/bin/luo-max --version
/usr/local/bin/luo-max perfil alto >/tmp/perfil.log 2>&1 &
monitor=$!
for i in {1..50}; do
    if grep -q 'Perfil alto:' /tmp/perfil.log; then break; fi
    sleep 0.1
done
grep -q 'Perfil alto:' /tmp/perfil.log
test "$(cat "$governor")" = performance
/usr/local/bin/luo-max perfil equilibrado
wait "$monitor"
test "$(cat "$governor")" = powersave
./install.sh --sysv
/etc/init.d/luo-max status
compgen -G '/etc/rc2.d/S*luo-max' >/dev/null
/usr/local/bin/luo-max perfil maximo --confirm-risks
test "$(cat "$boost")" = 1
/etc/init.d/luo-max stop
test "$(cat "$boost")" = 0
/etc/init.d/luo-max start
test "$(cat "$boost")" = 1
/usr/local/bin/luo-max perfil equilibrado
/etc/init.d/luo-max stop
/etc/init.d/luo-max start
test "$(cat "$governor")" = powersave
test "$(cat "$boost")" = 0
/usr/local/bin/luo-max perfil alto
test "$(cat "$governor")" = performance
./uninstall.sh
test "$(cat "$governor")" = powersave
test ! -e /var/lib/luo-max/profile.json
test ! -e /etc/init.d/luo-max
if compgen -G '/etc/rc2.d/*luo-max' >/dev/null; then exit 1; fi
./uninstall.sh
test ! -e /usr/local/bin/luo-max
TEST
