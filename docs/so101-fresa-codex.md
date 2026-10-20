# Codex como controlador del ciclo de mejora

El ciclo conecta **Codex CLI autenticado con ChatGPT** con las campañas ASPIRE de
la fresa SO-101. Usa el inicio de sesión normal de Codex y no requiere una clave
de API de OpenAI. Consume el acceso y los límites de la cuenta de Codex.
La integración sigue el [modo no interactivo documentado](https://learn.chatgpt.com/docs/non-interactive-mode),
con respuesta JSON estructurada y reutilización de la autenticación guardada.
No lee, copia ni registra el archivo de credenciales.

## Qué hace una ejecución

1. Evalúa una copia del programa inicial en los casos de desarrollo elegidos.
2. Entrega a Codex el [contexto público del SO-101](so101-llm-context.md), el código
   anterior, los diagnósticos de desarrollo y la mejor versión disponible.
3. Codex devuelve un análisis, un resumen del cambio y un programa completo.
4. Valida el código con las restricciones existentes de ASPIRE. Un programa
   rechazado vuelve como error al siguiente intento, sin ejecutarse en MuJoCo.
5. Ejecuta el programa admitido con el mismo evaluador, casos y presupuesto.
6. Conserva la mejor versión y repite con el nuevo diagnóstico hasta completar
   los casos elegidos o consumir el número máximo de propuestas.

Cada vuelta es una ejecución nueva de Codex con contexto explícito. Esta
conversación puede supervisar e inspeccionar el proceso; sus mensajes no se
inyectan automáticamente en una campaña que ya esté en marcha. Las instrucciones
guardadas y los registros permiten reconstruir lo que recibió el modelo.
El ciclo modifica programas de la tarea; no entrena los pesos del modelo.

Codex tiene desactivadas las herramientas de shell, apps, plugins, hooks y
subagentes, no carga la configuración personal de herramientas y usa modo de
solo lectura. Se rechazan propuestas cuyo registro muestre uso de herramientas.
El coordinador escribe y ejecuta el código propuesto. La ejecución del programa
usa el runtime público restringido de ASPIRE en un proceso de simulación separado;
estas comprobaciones no constituyen un aislamiento de seguridad para código hostil.

## Configuración local de este PC

`configs/so101/codex-local.json` está excluido de Git. Contiene únicamente rutas
de ejecutables y del intercambio de archivos entre Ubuntu y Windows:

```json
{
  "codex": "/mnt/c/.../Codex/bin/.../codex.exe",
  "host_python": "/mnt/c/.../dependencies/python/python.exe",
  "exchange_dir": "/mnt/d/AI/Aspire/outputs/codex-exchange"
}
```

Las rutas reales ya se han configurado y comprobado en este equipo. Ubuntu ejecuta
las simulaciones y el Python nativo de Windows ejecuta el Codex ya autenticado.
Si se actualiza o cambia la ruta de Codex, comprobar `Get-Command codex` en
PowerShell y actualizar este archivo. La versión de CLI y estas rutas forman
parte de la identidad de la campaña; un cambio exige una carpeta nueva.

También admite un Codex instalado directamente en Linux: indicar su ejecutable
en `codex`, omitir `host_python` e indicar un directorio Linux de intercambio.
La instalación debe estar autenticada mediante `codex login` con ChatGPT.
`model` es opcional: si se omite, se utiliza la selección predeterminada de la
CLI con configuración personal ignorada. Esto no garantiza usar exactamente el
mismo modelo o historial que esta conversación. El programa y la respuesta
efectivamente usados siempre quedan guardados.

No incluir claves ni tokens en el JSON. El worker usa la autenticación guardada
y elimina del entorno las variables de claves de API de los proveedores conocidos.

## Ejecutar desde la terminal Ubuntu visible

Con `.venv-robosuite` activado y WSLg/D3D12 configurados como en la
[guía de campañas](so101-fresa-campanas.md):

```bash
python -m cap_harness.so101.learning \
  --output outputs/so101-codex-learning-demo \
  --initial-program examples/robosuite/so101_strawberry_detachment.py \
  --seeds 101 102 --max-rounds 2 --max-attempts 1 \
  --width 160 --height 120 --round-budget 1
```

Esto permite como máximo dos propuestas nuevas de Codex para toda la campaña;
`--round-budget 1` pausa esta invocación después de evaluar una propuesta. El
programa inicial se evalúa primero y no consume propuestas del modelo. Repetir
sin `--round-budget 1` continúa. Si se alcanzó el objetivo, repetir el comando
audita los archivos y termina sin nuevas llamadas ni episodios.

Sin `--seeds` usa los **12 casos de desarrollo**. `--max-rounds` limita las
propuestas del modelo; no se renueva al reanudar. El valor predeterminado es 2.
Cada propuesta puede ejecutar todos los casos elegidos. Los errores de código
consumen una propuesta, sin consumir episodios si los detecta la validación
estática. La corrección de un fallo físico requiere una propuesta nueva: no se
repite el mismo programa hasta obtener un éxito.

`--model-timeout-s` limita cada llamada a Codex, por defecto 300 segundos. El
worker de Windows mantiene su propio plazo y mata el árbol de procesos del
modelo al agotarlo. `Ctrl+C` solicita cancelar la llamada en curso y conserva
los registros. Si hubo un cierre abrupto, una llamada pendiente debe terminar
antes de reanudar; no se reenvía automáticamente una petición de estado incierto.
Un error terminal del proveedor se conserva y detiene el ciclo. Tras resolver
el acceso o la configuración se debe usar otra carpeta para iniciar otra campaña.

Los límites de episodios (`--max-steps`, `--timeout-s`, `--max-attempts`, cámaras
y renderizador) tienen la misma semántica que el lanzador de campañas. Antes de
empezar se fijan en la identidad, junto al código inicial, contexto, protocolo,
CLI y huella del simulador. Cambiarlos exige otra carpeta de salida.

## Cómo selecciona la mejor versión

La regla está fijada antes de ejecutar: mayor número de `task_success`; en
empate, mayor número de `program_ok`; si sigue el empate, conserva la versión
más antigua. Un resultado peor no sustituye al mejor, aunque permanece en el
historial y se entrega a Codex para corregirlo. El ciclo se detiene por objetivo
cuando todos los casos seleccionados satisfacen la tarea y el programa termina
correctamente en todos ellos. No modifica el criterio físico del evaluador.

`summary.json` indica `selected_cases_passed`, `budget_exhausted` o `paused`.
Agotar el presupuesto con fallos es un resultado válido del experimento; la CLI
sale con 0 al completar o pausar normalmente. Sale con 1 ante errores de acceso,
infraestructura o integridad, y con 130 ante una interrupción del usuario.

## Evidencias y separación de información

- `learning.json` y `inputs/`: identidad inmutable, programa inicial, contexto y
  copia del protocolo.
- `round-000/`: evaluación inicial sin llamada al modelo.
- `round-001/`, etc.: `model/` con petición, respuesta, eventos y uso registrado
  por la CLI; `proposal.json`, `candidate.py`, `feedback.json` y campaña nativa.
- `finished.json`: inventario con hashes de la vuelta. Los episodios conservan
  también sus propios manifiestos y vídeos. Al reanudar se auditan ambos niveles.
- `best.py` y `best.json`: copia y procedencia de la mejor versión de desarrollo.
- `summary.json`: estado, puntuaciones y número de propuestas.

El feedback para Codex contiene errores de ejecución, etiquetas de fallo,
instantes, fases, parejas de contacto relevantes y medidas acotadas de agarre y
retención. Omite semillas, fuerzas ocultas de separación, constantes de la unión,
posiciones nativas del fruto y fuerzas internas del solver. Estos diagnósticos
son información para corregir después del ensayo, no nuevas herramientas para
consultar el éxito o la física oculta durante el programa.

Este primer ciclo envía contexto y diagnósticos textuales, sin imágenes al modelo.
Los vídeos se guardan para inspección humana. SAM3 y la variación de posiciones
siguen siendo fases posteriores.

El ciclo **solo ejecuta desarrollo**. No acepta semillas reservadas ni ejecuta
validación o evaluación automáticamente. `best.py` es un candidato elegido en
desarrollo, no una solución validada. Tras la campaña completa se puede congelar
la campaña nativa de la versión elegida con el procedimiento existente y lanzar
las particiones reservadas por separado. Superar dos casos de demostración no
establece robustez en los 12 ni transferencia al SO-101 real.

## Resultado de la primera prueba real

El 19 de octubre de 2026 se ejecutó el ciclo con la sesión real de Codex y los
casos de desarrollo 101 y 102. Las 66 pruebas conjuntas aprobaron antes de la
demostración: 15 del ciclo/worker, 20 de campañas, 20 de casos y 11 de diagnósticos.
Una llamada corta previa comprobó la conexión; después, la campaña realizó dos
propuestas nuevas de Codex y seis episodios de simulación.

| Versión | Programa sin errores | Tareas válidas | Evidencia principal |
|---|---:|---:|---|
| Inicial, vuelta 0 | 2/2 | 1/2 | Contacto fruto-pedúnculo en 101; éxito en 102 |
| Propuesta Codex 1 | 0/2 | 0/2 | Caída y aserción de retención bilateral al finalizar |
| Propuesta Codex 2 | 0/2 | 0/2 | Aserción de precarga bilateral; el fruto seguía unido |

La primera propuesta intentó adelantar la retirada durante el giro y cambiar la
regulación de la pinza. Tras recibir los registros de caída de ambos casos, Codex
produjo la segunda propuesta, recuperando parte de la estrategia inicial y
añadiendo una comprobación de precarga. Esa comprobación detuvo el programa antes
de completar el desprendimiento. La etiqueta `junction_not_released` describe el
estado al terminar; el error de ejecución conserva el motivo de la interrupción.

El ciclo alcanzó su presupuesto de dos propuestas. Ninguna mejoró la inicial, que
se conservó en `best.py` con 1/2 tareas válidas. La prueba acredita la conexión,
el intercambio de diagnósticos y la conservación del mejor resultado; no acredita
una mejora de cosecha ni una solución robusta. El evaluador no se cambió y los
fallos físicos no se repitieron con el mismo código para intentar obtener un pase.

Se verificó una pausa después de la primera propuesta, su continuación y una
invocación adicional al terminar. Los hashes permanecieron iguales y no aparecieron
llamadas al modelo ni episodios adicionales. Las propuestas recibidas coincidían
con el código ejecutado y sus eventos no mostraron uso de herramientas.

Los resultados completos están en
`D:\AI\Aspire\outputs\local\so101-codex-learning-demo`, y la auditoría en
`D:\AI\Aspire\outputs\local\so101-codex-learning-verification.json`.
Los casos de validación y evaluación siguen sin ejecutarse. Para ampliar el
presupuesto o cambiar el contexto debe crearse una campaña nueva, conservando
esta como registro del primer ensayo.
