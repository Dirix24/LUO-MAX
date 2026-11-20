#!/bin/bash
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 022

usage() { echo "Uso: ./install.sh [--systemd|--sysv|--sin-servicio] [--destdir RUTA_ABSOLUTA]" >&2; exit 2; }
mode=auto
root=
while (( $# )); do
    case "$1" in
        --systemd) mode=systemd; shift ;;
        --sysv) mode=sysv; shift ;;
        --sin-servicio) mode=none; shift ;;
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
init="$root/etc/init.d/luo-max"
if [[ $mode == auto ]]; then
    if [[ -n $root ]]; then mode=none
    elif [[ -d /run/systemd/system ]] && [[ $(cat /proc/1/comm) == systemd ]]; then mode=systemd
    elif [[ $(cat /proc/1/comm) == init ]]; then mode=sysv
    else
        echo 'Gestor de arranque no compatible. Para una sesión manual, usa --sin-servicio.' >&2
        exit 1
    fi
fi

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
if [[ -e $init ]] && ! grep -qx '# LUO-MAX SysV monitor' "$init"; then
    echo "El script $init pertenece a otra instalación." >&2
    exit 1
fi
if [[ -z $root ]]; then
    if [[ $mode == systemd && ! -d /run/systemd/system ]]; then
        echo 'No hay un gestor systemd activo.' >&2
        exit 1
    fi
    if [[ $mode == sysv ]]; then
        command -v update-rc.d >/dev/null
        command -v flock >/dev/null
    fi
    if [[ -f $unit && -d /run/systemd/system ]]; then systemctl stop luo-max.service; fi
    if [[ -x $init ]]; then "$init" stop; fi
    if [[ $mode == none ]]; then
        if [[ -f $unit ]]; then systemctl --root=/ disable luo-max.service; fi
        if [[ -f $init ]]; then _SKIP_SYSTEMD_NATIVE=1 update-rc.d luo-max disable; fi
    fi
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
case "$mode" in
    systemd)
        install -D -m 0644 systemd/luo-max.service "$unit"
        if [[ -z $root ]]; then
            systemctl daemon-reload
            systemctl enable --now luo-max.service
            systemctl is-active --quiet luo-max.service
        fi
        ;;
    sysv)
        install -D -m 0755 sysv/luo-max "$init"
        if [[ -z $root ]]; then
            update-rc.d luo-max defaults
            _SKIP_SYSTEMD_NATIVE=1 update-rc.d luo-max enable
            "$init" start
        fi
        ;;
esac
if [[ -z $root && $mode != none ]]; then
    echo "LUO-MAX instalado. El monitor está activo y arrancará con el sistema ($mode)."
else
    echo 'LUO-MAX instalado. Puedes iniciar una sesión con sudo luo-max perfil alto.'
fi
