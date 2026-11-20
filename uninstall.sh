#!/bin/bash
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

root=
if [[ $# == 2 && $1 == --destdir && $2 == /* && $2 != / ]]; then
    root=$2
elif (( $# )); then
    echo "Uso: ./uninstall.sh [--destdir RUTA_ABSOLUTA]" >&2
    exit 2
fi
if [[ -z $root && $EUID != 0 ]]; then
    echo 'La desinstalación del sistema requiere sudo.' >&2
    exit 1
fi

app="$root/usr/local/lib/luo-max"
bin="$root/usr/local/bin/luo-max"
unit="$root/etc/systemd/system/luo-max.service"
if [[ -f $unit ]] && ! grep -qx 'Description=LUO-MAX thermal and power monitor' "$unit"; then
    echo 'Unidad anterior detectada. Consulta docs/MIGRACION.md.' >&2
    exit 1
fi
if [[ -z $root ]]; then
    if [[ -f $unit ]]; then systemctl stop luo-max.service; fi
    if [[ -x $app/luo-max.py ]]; then
        "$app/luo-max.py" restore --offline
    elif [[ -e /var/lib/luo-max/session.json || -e /var/lib/luo-max/backup.json ]]; then
        echo 'Hay una copia pendiente y falta el ejecutable para restaurarla.' >&2
        exit 1
    fi
    if [[ -f $unit ]]; then systemctl disable luo-max.service; fi
fi
if [[ -L $bin && "$(readlink -- "$bin")" == ../lib/luo-max/luo-max.py ]]; then rm -- "$bin"; fi
rm -f -- "$app/luo-max.py" "$app"/luomax/{__init__,cli,controller,gui,hardware}.py \
    "$app"/assets/logo-{claro,oscuro}.png
if [[ -d $app/luomax/__pycache__ && ! -L $app/luomax/__pycache__ ]]; then
    rm -f -- "$app"/luomax/__pycache__/{__init__,cli,controller,gui,hardware}.cpython-*.pyc
    rmdir -- "$app/luomax/__pycache__"
fi
for directory in "$app/luomax" "$app/assets" "$app"; do
    if [[ -d $directory ]]; then rmdir -- "$directory"; fi
done
if [[ -f $unit ]]; then
    rm -- "$unit"
    if [[ -z $root ]]; then systemctl daemon-reload; fi
fi
# Keep the lock inodes stable across uninstalls and concurrent commands.
echo 'LUO-MAX desinstalado.'
