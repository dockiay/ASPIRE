# Campañas reproducibles de la fresa SO-101

El lanzador ejecuta programas públicos con `cap-harness run --benchmark so101`,
uno por proceso y caso. Compara sus resultados sobre el mismo conjunto de casos,
graba vídeos y diagnósticos y permite continuar una campaña. No llama a un LLM
ni modifica estrategias automáticamente: esa es la siguiente fase del plan.

## Uso en la terminal de Ubuntu

Desde el repositorio Linux, con el entorno ya instalado:

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
export CUDA_VISIBLE_DEVICES=0
```

Una comprobación pequeña con dos programas y dos casos de **desarrollo**:

```bash
python -m cap_harness.so101.campaign run \
  --output outputs/so101-campaign-smoke \
  --program a_probe=examples/robosuite/so101_strawberry_case_probe.py \
  --program b_baseline=examples/robosuite/so101_strawberry_detachment.py \
  --seeds 101 102 --run-budget 1
```

`--run-budget 1` limita esta invocación a un nuevo intento. Para continuar,
repetir el mismo comando sin `--run-budget 1`. Los episodios ya registrados se
auditan y se omiten. Al repetirlo una vez terminada la campaña, no se ejecutan
nuevos episodios. Los programas se ordenan por nombre dentro de cada caso.

Por defecto usa GLFW, adecuado para el WSLg de este PC; elimina las variables
heredadas de EGL que entrarían en conflicto y conserva la selección D3D12.
`--renderer egl` permite otra instalación Linux que ya tenga EGL funcionando.
El lanzador requiere Linux/WSL y no abre terminales adicionales.

## Presupuesto y puntuación

Los valores predeterminados son 800 pasos de simulación, 180 segundos reales
por intento, dos intentos máximos por programa/caso y cámaras de 320 × 240.
Se cambian con `--max-steps`, `--timeout-s`, `--max-attempts`, `--width` y
`--height`. Deben fijarse al crear la campaña. El máximo de intentos persiste
entre invocaciones; reanudar no renueva ese presupuesto. El tiempo total queda
acotado por programas × casos × intentos × tiempo por intento, más auditoría
y preparación. Al vencer el tiempo se termina el grupo de procesos del episodio.

El primer episodio con evidencias completas cuenta, aunque falle la cosecha,
llegue al límite de pasos o el programa lance una excepción. Esos fallos no se
repiten para buscar un éxito. Solo se reintentan interrupciones, tiempos agotados
y errores de infraestructura o grabación. Todos los intentos conservan sus
archivos y registros; los incompletos no se presentan como diagnósticos físicos.

`program_ok` y `task_success` se cuentan por separado. La puntuación física usa
`task_success` del evaluador original. La tasa permanece `null` mientras falten
episodios auditados: no se calcula sobre un subconjunto que pueda resultar más
fácil. Una campaña completa con fallos físicos sale con código 0; el código 2
indica presupuesto agotado por infraestructura. Una pausa por `--run-budget`
también sale con 0, por lo que debe consultarse `summary.json` → `complete`.

## Archivos y reanudación

- `campaign.json`: identidad inmutable, casos y hashes, código por versión,
  límites, partición y huella del entorno.
- `inputs/programs/*.py` y `inputs/protocol.json`: copias del código ejecutado
  y del protocolo. El proceso ejecuta estas copias.
- `attempts/PROGRAMA/SEMILLA/attempt-NNN/`: comando, salida, errores, resultado
  y episodio nativo con su manifiesto, diagnóstico y vídeos.
- `summary.json`: comparación y estado de todos los programas/casos, rutas
  de evidencias y motivo de fallo principal.

La huella incluye el código local de `src` aunque no esté confirmado en Git,
la configuración y los archivos del modelo, los archivos de Robosuite,
versiones de paquetes, Python y variables relevantes de renderizado. Se comprueba
antes y después de cada nuevo episodio. Un cambio durante el episodio invalida
la campaña; conserva las evidencias, pero exige empezar otra carpeta.
Esto registra el entorno de trabajo; no empaqueta una máquina hermética ni
garantiza idénticos resultados entre equipos o controladores gráficos.

Al continuar se verifican las copias de entrada y todos los hashes de los
episodios puntuados, incluyendo su caso, protocolo y diagnóstico. Un cambio de
código, casos, entorno o límites exige otra carpeta: no mezcla resultados.
Un bloqueo del sistema operativo impide dos escritores simultáneos y se libera
al terminar el proceso. El episodio hereda ese bloqueo; una señal de Linux termina
el simulador si muere el lanzador. Los límites de tiempo y las interrupciones
normales terminan además su grupo de procesos. Si se cerró el lanzador después de finalizar un episodio
pero antes de registrar su resultado, recupera ese episodio en vez de repetirlo.

Las carpetas incompletas por un cierre durante la creación inicial deben
conservarse para inspección y sustituirse por una carpeta nueva.

## Desarrollo completo y particiones reservadas

Sin `--seeds` ejecuta **todos los casos de desarrollo**, nunca las particiones
reservadas. Para una campaña real de desarrollo:

```bash
python -m cap_harness.so101.campaign run \
  --output outputs/so101-development-v1 \
  --program baseline=examples/robosuite/so101_strawberry_detachment.py
```

Cuando un programa tenga registrados los 12 casos de desarrollo, se puede
congelar su selección:

```bash
python -m cap_harness.so101.campaign freeze \
  --output outputs/so101-development-v1 --program baseline
```

Guarda `selection.json` con el hash del programa, entorno, protocolo y presupuesto.
La selección de una campaña no se puede sustituir por otro programa. Congelar
no afirma que haya alcanzado una tasa suficiente: registra una decisión explícita.

**No ejecutar ahora:** en una fase posterior se podrá lanzar `run` con
`--partition validation` o `--partition evaluation`, un solo `--program` y
`--selection outputs/so101-development-v1/selection.json`, usando otra carpeta
y el mismo código, entorno y presupuesto. Exige la partición completa; no admite
una selección parcial de casos reservados. No lanza automáticamente validación
ni evaluación al terminar desarrollo.

El archivo de selección es un control de procedimiento, no una barrera de
seguridad contra su modificación manual. Los fallos de evaluación final no deben
usarse para corregir este candidato ni convertir esos casos en desarrollo.
El lanzador no puede imponer esa disciplina fuera de sus propias ejecuciones.
Los casos siguen siendo combinaciones sintéticas de fuerza y deformabilidad,
con geometría fija y física vegetal pendiente de calibrar.

## Comprobación realizada

Se aprobaron 20 pruebas del lanzador, incluyendo presupuestos, interrupción,
cierre forzado, recuperación de un episodio ya finalizado, hashes, bloqueo de
escritores y congelación de la selección. Las pruebas de selección reservada
construyen identidades con archivos sintéticos; no ejecutan esos casos físicos.

La demostración `outputs/so101-campaign-smoke-v2` usó los dos programas del ejemplo
y los casos de desarrollo 101 y 102. Se pausó tras el primer episodio, se continuó
hasta cuatro y se repitió el comando completo: ningún episodio se repitió ni
cambió su registro. Las evidencias completas se copiaron a Windows en
`D:\AI\Aspire\outputs\local\so101-campaign-smoke-v2`, junto al informe
`so101-campaign-smoke-v2-verification.json`.

| Programa | Caso 101 | Caso 102 |
|---|---|---|
| Sonda con pinza abierta | Sin agarre, esperado | Sin agarre, esperado |
| Desprendimiento actual | Fallo: contacto fruto-pedúnculo tras liberar | Desprendimiento y retención válidos |

En 101 el primer contacto no permitido se registró a los 18,052 s de simulación,
al liberarse con 2,791 N y 74,48° de inclinación. El criterio original contabiliza
ese contacto como apoyo externo; este resultado identifica el incumplimiento,
sin demostrar por sí solo qué corrección de movimiento lo resolvería. En 102
se cumplió el mismo contrato. La muestra de dos casos comprueba el lanzador,
no demuestra generalización ni sustituye la campaña de desarrollo completa.

La carpeta previa `outputs/so101-campaign-smoke` conserva una sonda realizada
antes del refuerzo de cierre. Al cambiar el código, el lanzador rechazó continuar
esa carpeta y exigió la campaña nueva. No se ejecutó validación ni evaluación.
