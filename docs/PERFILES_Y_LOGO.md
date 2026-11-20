# Identidad visual y perfiles — requisitos para Codex

## Logo
Crear un logotipo original de LUO-MAX: engranaje y rayo, estética tecnológica azul/cian, legible sobre fondo oscuro y claro. Integrarlo en README y, si se desarrolla interfaz gráfica, en su cabecera e icono. Mantener fuentes editables preferiblemente SVG y alternativa PNG. No incluir afirmaciones de compatibilidad Windows: LUO-MAX es para Linux. Revisar licencia y originalidad de los recursos.

## Perfiles
1. **Equilibrado (predeterminado y recomendado)**: configuración conservadora, sin limpieza destructiva ni límites máximos de potencia.
2. **Alto rendimiento**: ajustes reversibles para tareas intensivas, con información de consumo y temperatura.
3. **Extremo**: ajustes adicionales exclusivamente opt-in, verificación de hardware, batería y sensores.
4. **Máximo (riesgo térmico elevado)**: el perfil más alto, con advertencia explícita de sobrecalentamiento, mayor consumo, ruido, posible inestabilidad y reducción de autonomía. No es overclock físico garantizado; no superar límites definidos por el fabricante. Nunca aplicar automáticamente al instalar o iniciar el sistema.

## Confirmación obligatoria para Máximo
Mostrar antes de aplicar: **«ADVERTENCIA: el perfil Máximo puede aumentar significativamente la temperatura y el consumo eléctrico, provocar inestabilidad o apagados de protección. Se recomienda refrigeración adecuada, vigilar las temperaturas y evitar sesiones prolongadas. Utilízalo bajo tu responsabilidad.»**

Exigir aceptación explícita en UI y CLI (por ejemplo `--acknowledge-risk`), además de un `--dry-run`. No aceptar el riesgo implícitamente por instalar la aplicación. Validar umbrales con histéresis y disponibilidad real de sensores; si no hay telemetría suficiente, denegar el perfil Máximo. En portátiles con batería, denegar por defecto. El monitor térmico debe reducir o detener ajustes al superar límites adecuados al hardware, no usar un único valor universal como garantía de seguridad. Facilitar botón/comando Restaurar.

## UX
- Si se crea GUI, Linux primero; que sea opcional y no sustituya CLI.
- Visualizar perfil seleccionado, acciones previstas, CPU/GPU, temperatura disponible y estado de reversión.
- Diferenciar advertencias reales de datos de ejemplo. No mostrar valores de hardware inventados.
- El logotipo y el mockup visual son referencias de diseño, no prueba de funcionamiento.

## Pruebas
Probar transiciones entre perfiles, confirmación requerida para Máximo, rechazo sin sensores, rechazo por batería, errores de escritura, protección térmica, restauración, y ausencia de acciones peligrosas en perfil Equilibrado. No declarar la versión funcional hasta probar en VM y hardware autorizado.
