# LUO-MAX: auditoría y plan de versión funcional

Fecha: 2026-11-20. Base: rama `main` del repositorio `Dirix24/LUO-MAX`.

## Hallazgos priorizados
| Prioridad | Hallazgo | Evidencia | Solución verificable |
| --- | --- | --- | --- |
| P0 | Instalador inutilizable | `install.sh` copia directorios y binario inexistentes | Instalar únicamente `luo-max.py` como `luo-max`, comprobar errores |
| P0 | Desinstalación incorrecta | `uninstall.sh` apunta a `luo.service` y `/usr/local/bin/luo`, mientras Python utiliza `luo-max.service` y `/usr/local/bin/luo-max` | Unificar nombres y ejecutar rollback antes de retirar archivos |
| P0 | Borrado peligroso | `clean_temp_files()` elimina archivos en directorios compartidos por antigüedad | Desactivar limpieza global, nunca asumir que antigüedad implica desuso |
| P0 | Restauración incompleta | `snapshot_current_state()` no captura todas las operaciones de `apply_all()` | Registro reversible de cada operación, pruebas de round-trip |
| P0 | Éxitos falsos | `write_file()` devuelve falso y muchas llamadas lo ignoran; `run()` puede devolver None | Resultados tipados/errores visibles y códigos de salida |
| P0 | Configuración de alta potencia sin control | `apply_gpu_max()` usa límite superior NVIDIA, y el modo extremo fija frecuencias altas | Opt-in explícito, límites validables, desactivado por defecto |
| P1 | Daemon y systemd | Escritura PID simple y `ExecStop` basado en ese PID | Bloqueo/identidad segura y detener con systemd |
| P1 | Pruebas ausentes | No existe `tests/` ni workflow en main | Tests y CI sin root |
| P1 | Documentación exagerada | README promete recuperación absoluta y hardware universal | Documentar compatibilidad comprobada y limitaciones |

## Arquitectura destino (responsabilidades)
```text
CLI (sin efectos secundarios)
  -> HardwareProbe (solo lectura)
  -> Planner (perfil, restricciones, consentimiento, dry-run)
  -> Executor (operaciones pequeñas con resultado explícito)
  -> StateStore (backup atómico y manifiesto de cambios)
  -> Verifier (lee los valores realmente aplicados)
  -> Restorer (reversión ordenada, verificable, parcial reportada)
Daemon -> Planner + ThermalGuard -> Executor; systemd supervisa ciclo de vida
```

## Política de seguridad
- Por defecto hacer diagnóstico o simulación, no optimización extrema permanente.
- No borrar `/tmp` ni `/var/tmp` globalmente; evitar `drop_caches` periódico por ser potencialmente contraproducente.
- No confundir cambios de rendimiento/energía con overclock físico.
- Ausencia de sensores no significa temperatura segura.
- No sobreescribir ajustes originales que no se puedan recuperar.
- `restore` sin respaldo debe salir sin alterar ajustes.
- La compatibilidad se establece mediante tests y verificación del kernel/driver, no solo existencia de rutas.

## Criterios de aceptación de una versión candidata
1. Instalación y desinstalación coherentes, idempotentes y sin errores en VM Linux compatible.
2. `status` y `--help` funcionan sin root ni cambios en el sistema.
3. Simulación de operaciones visible; operaciones de riesgo desactivadas por defecto.
4. Restore recupera exactamente todos los valores que el programa cambió o devuelve error parcial explícito, jamás falso éxito.
5. `systemctl stop luo-max` detiene el daemon sin afectar a otros procesos.
6. CI verde y suite de tests de casos positivos, negativos y fallo de I/O.
7. README contiene requisitos mínimos, precauciones, ejemplos, soporte real, licencia y aviso de asistencia de IA.
8. PR revisable hacia `main`, sin fusión automática.

## Notas sobre la licencia y atribución
Se propone MIT por su carácter permisivo. El titular del repositorio debe comprobar que tiene derecho a licenciar todas las contribuciones y dependencias; inspirarse en otro proyecto no concede automáticamente derechos sobre su código. La asistencia de IA debe declararse con transparencia, pero no sustituye revisión humana.

## Limitación de esta auditoría
Auditoría estática del código remoto: no se ha ejecutado el optimizador en hardware ni se ha validado rendimiento real. El código fuente actual requiere implementación y pruebas antes de declarar versión funcional.
