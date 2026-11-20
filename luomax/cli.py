"""Entry points for inspection, profiles and the thermal monitor."""
import argparse
import json
import os
import sys

from . import __version__
from .controller import Controller, MonitorRequired
from .hardware import Hardware, MAX_WARNING, POWER_WARNING, PROFILES


def main(argv=None):
    parser = argparse.ArgumentParser(description="LUO-MAX · Políticas de rendimiento Linux")
    parser.add_argument("--version", action="version", version=f"LUO-MAX {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Inventario y estado actual del hardware")
    status.add_argument("--json", action="store_true")
    apply = commands.add_parser("apply", help="Aplicar un perfil con supervisión")
    profile = commands.add_parser("perfil", help="Elegir perfil e iniciar el monitor si hace falta")
    for command in (apply, profile):
        command.add_argument("profile", choices=PROFILES, default="equilibrado", nargs="?")
        command.add_argument("--confirm-risks", action="store_true")
        command.add_argument("--dry-run", action="store_true", help="Consultar los ajustes candidatos sin escribir")
    commands.add_parser("version", help="Mostrar la versión de LUO-MAX")
    restore = commands.add_parser("restore", help="Recuperar y verificar los valores originales")
    restore.add_argument("--offline", action="store_true", help="Exigir que el monitor esté detenido")
    for name in ("daemon", "gui"):
        commands.add_parser(name)
    args = parser.parse_args(argv)
    if args.command == "version":
        print(f"LUO-MAX {__version__}")
        return 0
    hardware = Hardware()
    controller = Controller(hardware)
    try:
        if args.command == "status":
            data = hardware.status()
            if args.json:
                print(json.dumps(data, ensure_ascii=False))
            else:
                for label, value in data.items():
                    if isinstance(value, list):
                        value = ", ".join(value)
                    print(f"{label}: {value if value not in (None, '') else 'no disponible'}")
            return 0
        if args.command == "gui":
            if os.geteuid() == 0:
                raise RuntimeError("Abre la aplicación gráfica con tu usuario habitual.")
            from .gui import launch
            return launch()
        if args.command in {"apply", "perfil"} and args.dry_run:
            if args.profile == "equilibrado":
                print("Equilibrado restauraría la sesión pendiente, si existe.")
                return 0
            settings, devices = hardware.plan(args.profile)
            expected_power = hardware.power() if args.profile in {"extremo", "maximo"} else None
            hardware.check(hardware.sensors(devices), expected_power)
            print("Ajustes candidatos según el estado actual:")
            for path, target in settings.items():
                print(f"  {path} = {target}")
            return 0
        if args.command in {"apply", "perfil"} and args.profile in {"extremo", "maximo"}:
            print(MAX_WARNING if args.profile == "maximo" else POWER_WARNING, file=sys.stderr)
            if not args.confirm_risks:
                raise RuntimeError("Confirma la activación explícita con --confirm-risks.")
        if os.geteuid() != 0:
            raise PermissionError("Esta operación requiere permisos de administrador.")
        if args.command == "daemon":
            controller.daemon(lambda message: print(message, flush=True))
        elif args.command == "restore" or args.profile == "equilibrado":
            restored = controller.restore(offline=getattr(args, "offline", False))
            print(f"Restauración verificada ({len(restored)} parámetros)." if restored
                  else "No hay cambios de LUO-MAX pendientes de restaurar.")
        else:
            try:
                changed = controller.apply(args.profile)
            except MonitorRequired:
                if args.command != "perfil":
                    raise
                controller.daemon(lambda message: print(message, flush=True), profile=args.profile)
                return 0
            print(f"Perfil {args.profile} supervisado. Parámetros modificados: {len(changed)}.")
            for path in changed:
                print(f"  {path}")
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, ImportError) as error:
        print(f"LUO-MAX: {error}", file=sys.stderr)
        return 1
    return 0
