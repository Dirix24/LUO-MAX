# LUO-MAX

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-oscuro.svg">
  <img src="assets/logo-claro.svg" alt="LUO-MAX · engranaje y rayo" width="296">
</picture>

LUO-MAX (Linux Universal Optimizer) permite consultar el hardware y aplicar políticas de rendimiento Linux supervisadas y reversibles. 

## Comandos para MX Linux

| Quiero | Comando | Qué hace |
| --- | --- | --- |
| Instalar o actualizar | `sudo ./install.sh` | Instala LUO-MAX, inicia el monitor en segundo plano y lo habilita al arrancar. Detecta systemd o SysVinit. |
| Ver la versión | `luo-max --version` | Muestra la versión instalada. |
| Elegir un perfil | `sudo luo-max perfil alto` | Aplica Alto rendimiento y deja el monitor vigilando el equipo. |
| Volver a Equilibrado | `sudo luo-max perfil equilibrado` | Restaura los valores originales. El monitor sigue activo. |
| Simular un perfil | `luo-max perfil alto --dry-run` | Muestra los ajustes candidatos sin escribirlos. |
| Ver hardware y temperatura | `luo-max status` | Muestra CPU, GPU, RAM, discos, temperatura y alimentación. |
| Abrir la interfaz | `luo-max gui` | Abre la interfaz gráfica como usuario normal. |
| Desinstalar | `sudo ./uninstall.sh` | Detiene el monitor, verifica la restauración y retira su arranque automático. |

Ejecuta los scripts desde la carpeta del repositorio. Si tenías un monitor manual en una terminal, detenlo con **Ctrl+C** antes de actualizar.

**Funcionamiento permanente.** Después de instalar, puedes cerrar la terminal. El monitor permanece en segundo plano y se inicia en cada arranque. Tras reiniciar, LUO-MAX parte en Equilibrado y espera que elijas un perfil; Alto, Extremo y Máximo se seleccionan de nuevo cuando los necesitas. Así se combinan un monitor permanente con ajustes a demanda, inspirados en [GameMode de Feral Interactive](https://github.com/FeralInteractive/gamemode).

### Requisitos

- Linux con Python 3.9 o posterior en `/usr/bin/python3`, Bash y utilidades GNU. En SysVinit también se usan `update-rc.d` y `flock`.
- Para aplicar perfiles de rendimiento se necesita un administrador, controles compatibles y sensores térmicos válidos.
- La GUI requiere Tkinter (paquete `python3-tk` en Debian y MX Linux). Las operaciones de administrador desde la GUI usan `pkexec` y un agente de Polkit.
- Si vienes de la versión anterior al sistema de perfiles, consulta la [guía de migración](docs/MIGRACION.md).

Para una instalación manual puedes usar `sudo ./install.sh --sin-servicio`. En ese caso `sudo luo-max perfil alto` mantiene el monitor en la terminal hasta Ctrl+C o hasta volver a Equilibrado. Los comandos anteriores `apply`, `restore` y `daemon` siguen disponibles.

## Perfiles

| Perfil | Comando | Política |
| --- | --- | --- |
| **Equilibrado** (predeterminado) | `sudo luo-max perfil equilibrado` | Delega la política al sistema. Si existe una sesión, recupera sus valores originales. |
| **Alto rendimiento** | `sudo luo-max perfil alto` | Selecciona el governor `performance` donde esté disponible. Puede devolver una GPU AMD restringida al modo dinámico `auto`. |
| **Extremo** | `sudo luo-max perfil extremo --confirm-risks` | Añade preferencia energética de rendimiento donde el controlador la exponga. Comprueba sensores y alimentación. |
| **Máximo** | `sudo luo-max perfil maximo --confirm-risks` | Habilita el boost de fábrica cuando esté disponible y puede seleccionar el modo `high` de AMDGPU con sensores asociados. Requiere confirmación y comprueba sensores y alimentación. |

Consulta los cambios con `luo-max perfil extremo --dry-run`. El comando agrupa los ajustes por componente e indica el valor actual, el propuesto o «sin cambio» si coinciden. Si un componente queda sin ajustes candidatos, la simulación también lo indica. Después de aplicar, `luo-max status` muestra también el mínimo de la GPU, el planificador de disco y `swappiness`.

Extremo y Máximo pueden ajustar cuatro tipos de componentes:

- **CPU**. Governor y preferencias de energía cuando el controlador los admite. Máximo puede habilitar el boost de fábrica, incluidos los controles por política cuando existen, y seleccionar la preferencia EPB de mayor rendimiento en Intel compatible. [CPUFreq](https://docs.kernel.org/admin-guide/pm/cpufreq.html) · [Intel EPB](https://docs.kernel.org/admin-guide/pm/intel_epb.html)
- **GPU**. AMDGPU puede usar los modos de su controlador. Intel i915 puede elevar el mínimo hasta RP1 si hay sensor dedicado. En la Intel HD 4400 Haswell ULT con identificador PCI `8086:0a16`, LUO-MAX puede usar el sensor térmico compartido del paquete si identifica uno solo. Para esta GPU adapta el mínimo con pasos de 50 MHz dentro del tope vigente. Intel Xe usa los niveles de frecuencia eficiente o alcanzable publicados por cada GT, sin fijar el reloj al tope. En Panfrost, Panthor, Lima y MSM puede seleccionar `performance` si el controlador expone el governor y un sensor propio. Una GPU sin telemetría compatible queda fuera del ajuste. NVIDIA aparece en el inventario desde PCI aunque falte DRM. Las GPU NVIDIA compatibles pueden optar al límite de potencia de fábrica con el comando indicado más abajo. [AMDGPU](https://docs.kernel.org/gpu/amdgpu/thermal.html) · [Coretemp](https://docs.kernel.org/hwmon/coretemp.html) · [Intel Xe](https://docs.kernel.org/gpu/xe/xe_gt_freq.html)
- **RAM**. Puede reducir `vm.swappiness` a 40 con al menos 2 GiB disponibles y swap en disco. Conserva valores ya inferiores y omite zram y zswap activos. [Parámetros de memoria del kernel](https://docs.kernel.org/admin-guide/sysctl/vm.html#swappiness)
- **Disco**. Puede seleccionar `mq-deadline` en discos SATA internos o `none` en NVMe PCIe interno si el kernel lo ofrece. Conserva la política de discos extraíbles y unidades ópticas. [Planificadores de E/S del kernel](https://docs.kernel.org/block/switching-sched.html)

Las diferencias de rendimiento dependen del equipo y de la carga. Si un valor ya coincide con el perfil, LUO-MAX lo conserva.

### NVIDIA con el controlador del fabricante

Si tienes `nvidia-smi` en `/usr/bin/nvidia-smi`, puedes consultar y autorizar el ajuste con:

```sh
luo-max perfil maximo --nvidia-fabrica --dry-run
sudo luo-max perfil maximo --nvidia-fabrica --confirm-risks
sudo luo-max perfil equilibrado
```

LUO-MAX identifica cada GPU por UUID. Si su límite actual es inferior al valor de fábrica y el controlador expone sus límites y la temperatura, puede subirlo hasta el valor de fábrica. Conserva los límites que ya coinciden y omite los superiores o desconocidos. Esto puede aumentar el consumo y la temperatura. El monitor usa la lectura de NVIDIA para revertir el ajuste si alcanza 80 °C o pierde la telemetría. [Referencia de NVIDIA SMI](https://docs.nvidia.com/deploy/nvidia-smi/)

### Protección térmica

![Confirmación del perfil Máximo en la interfaz](docs/capturas/maximo.png)

El perfil Máximo puede aumentar la temperatura, el consumo y el ruido, reducir la autonomía y provocar inestabilidad o apagados de protección. Usa refrigeración adecuada y vigila la temperatura de CPU y GPU. LUO-MAX modifica políticas del controlador y opciones de boost de fábrica. Mantiene los voltajes y los topes del fabricante. NVIDIA solo puede recuperar su límite de potencia de fábrica con autorización específica. No realiza overclock físico. Tampoco borra temporales ni vacía cachés.

El monitor verifica cada dos segundos la telemetría de CPU y de las GPU que modifica. Restaura la sesión si desaparece una lectura, si alcanza el umbral preventivo de 80 °C o un umbral inferior calculado a partir del límite crítico del sensor, o si cambia la alimentación verificada de Extremo o Máximo. En portátiles, esos dos perfiles requieren corriente confirmada. Si un equipo no expone batería ni fuentes de alimentación en sysfs, el monitor lo trata como equipo sin batería. Tras una protección, el perfil requiere reactivación manual.

## Restauración y desinstalación

Usa `sudo luo-max perfil equilibrado` para restaurar los ajustes durante el uso normal. Ejecuta `sudo ./uninstall.sh` para retirar también el servicio.

La GUI ofrece **Restaurar valores originales**. El diario se guarda de forma atómica antes de escribir y registra objetivos y valores observados. La restauración comprueba los valores devueltos por los controladores. La desinstalación se detiene ante un error de restauración para conservar el ejecutable y el diario. Los bloqueos en `/var/lib/luo-max` se conservan para mantener la exclusión entre procesos. Para fallos parciales, diarios de otro arranque o instalaciones antiguas, consulta la [guía de migración y recuperación](docs/MIGRACION.md).

## Verificación

| Entorno | Resultado comprobado |
| --- | --- |
| Debian 13, Python 3.13.5, Intel i7-4500U y GPU Intel | Inventario real de solo lectura, GUI en Xvfb y diálogo de confirmación. |
| Debian 13, espacio de nombres Linux aislado con sysfs simulado | Instalación y desinstalación repetibles, verificación estática de la unidad systemd, CLI instalada, rechazo de Máximo sin confirmación, activación confirmada, restauración a 90 °C y restauración al detener el daemon, inicio y parada de SysVinit y alta y retiro de sus enlaces de arranque. |
| Pruebas de regresión sin root | Perfiles, hardware simulado, sensores y alimentación, permisos, rollback, restauración parcial, daemon y scripts. |

```sh
python3 -m unittest discover -s tests -v
bash tests/integration-linux.sh   # requiere bubblewrap y espacios de nombres de usuario
```

GitHub Actions ejecuta las pruebas en Ubuntu 24.04 con Python 3.9 y 3.13. La validación local usó sysfs simulado para todas las escrituras. Siguen pendientes comprobar un reinicio completo con el servicio instalado, ejecutar con systemd como gestor activo, la autenticación gráfica de Polkit y pruebas de escritura y restauración en hardware autorizado Intel, AMD, NVIDIA y ARM. La tabla refleja las rutas que se verificaron. En MX Linux, el usuario comprobó Alto y la restauración sobre un Intel i7-4500U que ya usaba el governor `performance`. Las escrituras de i915, Xe, GPU ARM, RAM y disco y su restauración se probaron con atributos simulados. El control de NVIDIA se probó con respuestas simuladas de nvidia-smi. En el i7-4500U se comprobó de solo lectura la propuesta de frecuencia mínima de su iGPU. El proyecto se entrega como candidato a revisión humana.

## Licencia y desarrollo con IA

Licencia [MIT](LICENSE). Los logotipos SVG y PNG del repositorio se diseñaron para LUO-MAX. La GUI utiliza Tkinter y Polkit instalados por la distribución. El repositorio no incluye copias de esas dependencias ni de las fuentes del sistema.

**LUO-MAX — Proyecto de código abierto desarrollado con asistencia de inteligencia artificial.**

Este proyecto ha sido creado y desarrollado con ayuda de herramientas de inteligencia artificial, incluyendo OpenAI Codex y ChatGPT.

La inteligencia artificial ha participado en tareas de arquitectura, programación, documentación, análisis y revisión del software.

El proyecto es mantenido y supervisado por sus colaboradores humanos.

El uso de IA no sustituye las pruebas, la revisión humana ni las garantías de seguridad.

**Licencia: MIT.**
