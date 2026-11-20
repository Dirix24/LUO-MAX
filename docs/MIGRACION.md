# Migración y recuperación

Las versiones anteriores podían dejar activos límites de frecuencia, políticas de CPU y GPU, cambios de persistencia y potencia NVIDIA, schedulers de disco y valores sysctl. El antiguo `backup.json` no registraba todos esos valores. Los archivos temporales que borró la versión antigua no se pueden recuperar con LUO-MAX.

1. Detén y deshabilita la unidad anterior si existe. Revisa primero sus rutas y órdenes con `systemctl cat luo-max.service` o `systemctl cat luo.service`. Si había un proceso manual, identifica y verifica su ejecutable y PID antes de detenerlo.
2. Conserva por separado las copias antiguas y revisa `/var/lib/luo-max/backup.json`, `/etc/sysctl.d/99-luo-max.conf` y, si existe, `/etc/sysctl.d/99-luo-performance.conf`. Contrasta los cambios persistentes con la configuración de tu distribución y conserva los ajustes que sean propios. Reinicia tras retirar la configuración persistente que corresponda y verifica las políticas con las herramientas de la distribución o el fabricante. Para los parámetros no registrados, se requiere una referencia fiable del valor original.
3. Archiva las unidades antiguas y el diario heredado fuera de sus rutas activas después de revisarlos. Si retiraste una unidad, ejecuta `sudo systemctl daemon-reload`. Después puedes instalar la versión nueva.

## Diario de la versión actual

`/var/lib/luo-max/session.json` contiene el identificador del arranque, los parámetros originales, los objetivos, los valores verificados y los sensores asignados. Si falla la restauración, el diario se conserva. Corrige la causa indicada y ejecuta nuevamente `sudo luo-max restore`. Un atributo que desapareció al desconectar un dispositivo puede volver al reconectarlo.

Si el diario pertenece a otro arranque, LUO-MAX evita escribir valores antiguos en dispositivos que pudieron cambiar de identificación. El monitor archiva el diario de otro arranque al iniciarse y evalúa el perfil guardado en `/var/lib/luo-max/profile.json` con los controles del arranque actual. Equilibrado es el valor inicial si todavía no se ha guardado un perfil. Puedes consultar la copia archivada para comparar sus valores con el hardware y los ajustes actuales. El software no puede verificar retrospectivamente qué valores se recuperaron en otro arranque.
