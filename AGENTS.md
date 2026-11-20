# Instrucciones para Codex — LUO-MAX

## Misión
Convertir LUO-MAX en una herramienta Linux **realmente funcional, segura, reversible y verificable**, trabajando solamente en la rama `codex/version-funcional-segura-2026-11-20` (o una rama derivada). **No modificar ni fusionar `main`**. El usuario decidirá el merge.

## Diagnóstico verificado en `main` (20-11-2026)
- Repositorio de cuatro archivos: `README.md`, `luo-max.py`, `install.sh`, `uninstall.sh`; el código de aplicación reside en el archivo Python.
- `install.sh` intenta copiar `core detection backup optimization gaming persistence` y `luo`, que no existen: instalación rota.
- `uninstall.sh` elimina otra unidad (`luo.service`) y rutas diferentes de las usadas por `luo-max.py`: desinstalación inconsistente.
- `clean_temp_files()` recorre y borra globalmente archivos de `/tmp` y `/var/tmp` por antigüedad; una marca temporal vieja NO garantiza que un fichero no esté en uso. Riesgo de pérdida de datos. `clear_ram_cache()` ejecuta `drop_caches` y su éxito no comprueba el resultado de `write_file()`.
- `restore_all()` promete reversión completa, pero el snapshot no cubre todos los cambios: frecuencias CPU, scheduler, NVIDIA, `pp_dpm_*`, energía y algunos sysctls. Si la configuración sysctl ya existía, se sobreescribe sin guardar su contenido.
- `apply_all()` realiza cambios inmediatamente con root, incluidos límites de potencia de GPU, perfiles de CPU y sysctl, y hace limpieza. Falta un modo de simulación y permisos de consentimiento por operación.
- `thermal_guard()` depende de sensores disponibles, no cubre todas las modificaciones de GPU ni ausencia/fallo de sensores. Un límite fijo no es garantía universal de seguridad.
- El código utiliza `run()` y `write_file()` que frecuentemente ocultan fallos. `install_service()` informa de éxito sin comprobar fallos de subprocess.
- No hay suite de pruebas, ni CI, ni licencia en `main`.

## Prioridad P0 — seguridad y funcionamiento comprobable
1. Mantener `status`, `apply`, `restore`, `daemon`, `stop`, `install-service`, `uninstall-service` documentados, con códigos de salida significativos. Evitar efectos colaterales en imports y `status`.
2. Implementar `--dry-run` y modo predeterminado conservador: NUNCA borrar archivos temporales ajenos, forzar límites máximos de potencia ni vaciar cachés automáticamente. Funciones destructivas o de riesgo solo con consentimiento explícito, ámbito seguro y pruebas; preferible eliminarlas del modo normal.
3. Implementar operaciones reversibles: capturar estado previo real por recurso, guardar backup atómico con permisos 0600, no pisar respaldos, validar rutas de sysfs, aplicar/restaurar solo lo que se modificó exitosamente, rollback ante fallo e informes claros. Si no hay backup, `restore` no debe alterar valores arbitrarios. No prometer restauración total de cambios imposibles de revertir.
4. Estado consistente de daemon: bloqueo exclusivo, PID validado (evitar matar procesos ajenos), señales y parada limpia; systemd gestiona el proceso principal. `stop` no debe enviar señales a PIDs reutilizados.
5. Si falta información de temperatura, falla la lectura, o el equipo funciona con batería, evitar o limitar operaciones de alto consumo. No afirmar compatibilidad universal sin evidencias. No desactivar protecciones del kernel.
6. Evitar ejecutar `sysctl --system` como estrategia indiscriminada de rollback; conservar valores concretos y archivos originales, o excluir ajustes no reversibles del perfil normal.
7. Revisar scripts de instalación/desinstalación para usar un solo ejecutable `/usr/local/bin/luo-max`, una única unidad `luo-max.service`, gestión de errores, instalador idempotente y desinstalador que pare/restaure antes de borrar. No activar automáticamente turbo permanente durante la instalación.

## Prioridad P1 — arquitectura y calidad
- Refactorizar por módulos pequeños si aporta claridad: `cli`, `hardware`, `operations`, `backup`, `profiles`, `daemon`, `service`; sin romper la CLI. Mínimas dependencias y Python 3 en Linux.
- Separar detección, planificación, ejecución, verificación y restauración. Cada acción debe informar: compatible/no compatible/omitida/aplicada/fallida.
- Crear perfiles `balanced` y `performance` seguros; `extreme` solo opt-in con advertencias. Documentar efectos, límites y las variaciones de Intel/AMD/ARM/NVIDIA y discos.
- Registrar logs útiles sin información sensible, errores no silenciados y comandos diagnósticos.

## Pruebas y CI imprescindibles
- Test unitarios sin root ni escritura real en `/sys`, `/proc`, `/etc`, `/tmp`; usar `tmp_path`, mocks/fake filesystem y simulación de subprocesos.
- Probar CLI `--help`, `status` y `--dry-run`; detección de hardware ausente, sin sensores, sin NVIDIA, rutas read-only, excepciones de subprocess, batería, umbrales térmicos, persistencia atómica de backup, restauración exacta, idempotencia, manejo de señales, PID obsoleto y errores de instalación.
- Añadir GitHub Actions con `python -m compileall`, tests automatizados, `bash -n install.sh uninstall.sh`; herramientas externas opcionales si son justificadas.
- Integración real en máquina Linux/VM desechable, con autorización explícita y evaluación antes/después. NUNCA ejecutar ajustes de hardware privilegiados en el runner de CI.
- Documentar la matriz real de compatibilidad y resultados; no marcar `100% funcional` sin pruebas aprobadas.

## Entrega para revisión humana
- Commits en rama separada, PR a `main` **sin automerge** (preferentemente draft hasta que pasen tests).
- PR con checklist de riesgos, comandos de instalación/uso/restore/uninstall, cambios incompatibles, pruebas y logs.
- No hacer merge, ni activar el servicio permanentemente por defecto.
- Licencia MIT incorporada (comprobar derechos de terceros).
- Transparencia de IA: atribuir asistencia de IA sin atribuir a IA derechos de autor exclusivos y sin afirmar que ejecutó pruebas que no ejecutó.
