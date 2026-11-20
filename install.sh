#!/bin/bash
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 022

usage() { echo "Uso: ./install.sh [--systemd] [--destdir RUTA_ABSOLUTA]" >&2; exit 2; }
with_systemd=0
root=
while (( $# )); do
    case "$1" in
        --systemd) with_systemd=1; shift ;;
        --destdir) [[ ${2:-} == /* && $2 != / ]] || usage; root=$2; shift 2 ;;
        *) usage ;;
    esac
done

if [[ -z $root && $EUID != 0 ]]; then
    echo "La instalación en el sistema requiere sudo." >&2
    exit 1
fi
/usr/bin/python3 -I -c 'import sys; sys.exit(sys.version_info < (3, 9))' ||
    { echo 'Se requiere Python 3.9+ en /usr/bin/python3.' >&2; exit 1; }

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
app="$root/usr/local/lib/luo-max"
bin="$root/usr/local/bin/luo-max"
unit="$root/etc/systemd/system/luo-max.service"

for legacy in /var/lib/luo-max/backup.json /etc/sysctl.d/99-luo-max.conf /etc/sysctl.d/99-luo-performance.conf /etc/systemd/system/luo.service
do
    if [[ -e $root$legacy || -L $root$legacy ]]; then
        echo "Instalación anterior detectada en $legacy. Consulta docs/MIGRACION.md." >&2
        exit 1
    fi
done
if [[ -f $unit ]] && ! grep -qx 'Description=LUO-MAX thermal and power monitor' "$unit"; then
    echo "Unidad heredada detectada. Consulta docs/MIGRACION.md." >&2
    exit 1
fi
if [[ -z $root ]] && (( with_systemd )) && ! [[ -d /run/systemd/system ]]; then
    echo 'No hay un gestor systemd activo. Ejecuta sin --systemd.' >&2
    exit 1
fi
if [[ -z $root && -f $unit ]]; then
    systemctl stop luo-max.service
fi
if [[ -z $root ]]; then
    if [[ -x $app/luo-max.py ]]; then
        "$app/luo-max.py" restore --offline
    elif [[ -e /var/lib/luo-max/session.json ]]; then
        echo 'Hay una sesión pendiente y falta el ejecutable para restaurarla.' >&2
        exit 1
    fi
fi

install -d -m 0755 "$app/luomax" "$app/assets" "$(dirname -- "$bin")"
install -m 0755 luo-max.py "$app/luo-max.py"
install -m 0644 luomax/*.py "$app/luomax/"
install -m 0644 assets/logo-*.png "$app/assets/"
ln -sfn ../lib/luo-max/luo-max.py "$bin"
if (( with_systemd )); then
    install -D -m 0644 systemd/luo-max.service "$unit"
    if [[ -z $root ]]; then systemctl daemon-reload; fi
fi
echo 'LUO-MAX instalado. Inicia el monitor cuando quieras activar un perfil de rendimiento.'
