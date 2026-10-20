# SO-101 controlado desde ASPIRE

La entrada actual para el benchmark de cosecha y el ciclo completo con Codex o
API es [ASPIRE SO-101 v2](so101-iterative-debugging.md). Esta página conserva las
demostraciones iniciales de control y su contexto histórico.

El perfil de simulación `so101` permite ejecutar programas públicos de ASPIRE con
el modelo oficial importado en una escena de Robosuite/MuJoCo. El brazo tiene
cinco articulaciones, y la pinza se controla por separado. El perfil `robosuite`
conserva sus tareas y controladores Panda.

## Repetir el primer programa

En la terminal Ubuntu, desde la copia Linux del proyecto:

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
cap-harness run --benchmark so101 --suite so101_control \
  --task-id 0 --seed 1 \
  --program examples/robosuite/so101_aspire_control.py \
  --output-root outputs/local/so101-aspire --max-steps 300 \
  --camera-width 512 --camera-height 512
```

`--benchmark so101` selecciona el adaptador de cinco ejes; `--suite so101_control`
selecciona la tarea de comprobar cada articulación y la pinza. `--program` indica
el archivo con las instrucciones del robot. Cada ejecución crea una carpeta nueva
con el programa utilizado, las trazas, las mediciones y los vídeos.

El programa es
[so101_aspire_control.py](../examples/robosuite/so101_aspire_control.py).
ASPIRE le proporciona las funciones públicas al ejecutarlo:

```python
state = get_robot_state()
target = state.joint_positions["primary"].copy()
target[0] = target[0] + 0.18
motion = move_to_joints(target, tolerance=0.005, max_steps=80)
assert motion.ok
```

Cada uno de los cinco números representa el ángulo de una articulación, en
radianes. Aquí aumentamos la primera articulación 0,18 rad, aproximadamente 10,3°.
`move_to_joints` ejecuta el movimiento y comprueba su convergencia con mediciones;
devuelve un resultado tipado si converge, falla o se agota el tiempo disponible.

| Función | Qué permite aprender |
| --- | --- |
| `get_robot_state()` | Leer los cinco ángulos, velocidades, nombres, pose del efector y apertura de pinza. |
| `move_to_joints(...)` | Solicitar ángulos y comprobar que se alcanzan, manteniendo el objetivo de pinza. |
| `close_gripper()` / `open_gripper()` | Cerrar y abrir la pinza y comprobar su apertura medida. |
| `set_gripper(0.25)` | Mantener una apertura intermedia en este modelo de pinza. |
| `get_observation()` | Obtener las cámaras RGB-D `agentview` y `sideview`, con su calibración. |
| `so101.get_finger_contacts()` | Leer fuerzas y posiciones locales de contacto en sensores virtuales de los extremos de los dedos; el robot de serie no incluye estos sensores. |
| `go_home()` | Volver a la postura inicial recordada al comenzar la ejecución. |

Las cámaras de esta primera escena son fijas. Los ángulos solicitados se validan
contra los límites del modelo, y se limita el cambio del objetivo por tick. El
control articular directo necesita una estrategia explícita de colisiones. La
nueva lección de fresas usa puntos de paso preparados para su escena fija y un
evaluador de contactos. El perfil todavía no configura IK ni planificación cartesiana
para el SO-101; esos servicios Panda no se reutilizan para un brazo de cinco ejes.

## Qué significa completar esta tarea

El programa mueve y devuelve cada articulación, cierra la pinza y la vuelve a
abrir. El evaluador del entorno observa esos movimientos y exige que los cinco
ejes regresen y la pinza quede abierta. Ejecutar solo parte de la secuencia no
completa la tarea. Ese estado del evaluador permanece fuera de la API del programa.

Resultado comprobado el 17 de octubre de 2026:

- `program_ok=true` y `task_success=true` para la tarea de control `so101_control`.
- 100 ticks a 20 Hz: 5 segundos simulados.
- Error máximo al alcanzar los objetivos: aproximadamente 0,00201 rad,
  por debajo de la tolerancia de 0,005 rad.
- Error final respecto a la postura inicial: aproximadamente 0,000536 rad.
- Pinza medida: 0,000 cerrada → 1,000 abierta.
- Dos vídeos completos comprobados: 101 fotogramas por cámara, 512×512.
- 131 pruebas de contratos, API, registro, runtime, ejecuciones y adaptadores
  aprobadas; además se verificó la orden de pinzas en un solo tick.

La apertura normalizada corresponde a una interpolación del ángulo entre los
topes del modelo. Todavía no representa una calibración de la apertura física
de LeRobot. Las precisiones anteriores son mediciones de la simulación.

La copia Windows del resultado está en
`D:\AI\Aspire\outputs\local\so101-aspire-demo`. Su vídeo principal es
`media/videos/agentview.mp4`, y la segunda vista es `media/videos/sideview.mp4`.
El informe de revisión está en
`validation-artifacts/setup/so101-aspire-review.json`.

## Archivos de la integración

- [so101/adapter.py](../src/cap_harness/so101/adapter.py): estado y acciones públicos.
- [so101/codec.py](../src/cap_harness/so101/codec.py): conversión a los seis motores.
- [so101/environment.py](../src/cap_harness/so101/environment.py): simulación, cámaras
  y evaluación de la tarea de control.
- [so101/strawberry.py](../src/cap_harness/so101/strawberry.py): planta y evaluación
  de aproximación y retirada para la nueva lección.
- [so101/registry.py](../src/cap_harness/so101/registry.py): identidad e instrucción de la tarea.
- [contracts.py](../src/cap_harness/contracts.py): dimensión explícita `so101=5`.

## Primera lección de fresas: aproximación

La tarea `so101_strawberry_approach` ya está implementada y verificada con
`program_ok=true` y `task_success=true`. Añade maceta, fresa, pedúnculo y hojas
rígidos y fijos. El robot mantiene la
pinza abierta, llega a un marcador delante del fruto, mantiene la postura y vuelve
a su posición inicial. El evaluador comprueba posiciones, dirección de la
herramienta, permanencia y ausencia de contactos prohibidos, incluidos los contactos
del robot consigo mismo.

El programa utiliza coordenadas conocidas y puntos de paso articulares escritos
para esa escena. La visión con SAM3, el desprendimiento, un planificador
general y una campaña de mejora de programas siguen pendientes. Los resultados
anteriores corresponden únicamente a `so101_control`.

La [guía de aproximación a la fresa](so101-fresa-aproximacion.md) describe el nuevo
ejercicio y recoge sus resultados medidos. Su programa es
[so101_strawberry_approach.py](../examples/robosuite/so101_strawberry_approach.py).

## Contacto con ambos dedos

La tarea `so101_strawberry_grasp_contact` también está verificada. Gira la muñeca
para entrar de lado, cierra por etapas hasta detectar ambos dedos y mantiene
contactos opuestos durante al menos medio segundo. Después abre y regresa al
inicio. El evaluador comprueba las superficies de contacto, sus normales, fuerzas,
permanencia y límites durante los pasos físicos.

La fresa sigue rígida y unida a la planta: esta lección acredita contactos del
agarre; la retención después de desprenderla necesita otro ensayo. La
[guía de contacto](so101-fresa-agarre.md) incluye el programa, los sensores
virtuales, los límites didácticos y los resultados medidos.

## Retención de fruta libre

La [lección de retención](so101-fresa-retencion.md) añade una fresa libre de 20 g
y una fijación que se desactiva a los 8 segundos. Dos perfiles ejecutan el mismo
programa: `so101_strawberry_retention` usa contactos puntuales y
`so101_strawberry_retention_torsion` añade rozamiento contra el giro. El evaluador
exige dos segundos continuos sin apoyos externos ni deslizamiento mayor de 8 mm.
La comparación distingue el efecto del modelo de contacto del comportamiento
del programa. Sus parámetros siguen pendientes de calibración física.

## Transporte y depósito

La tarea `so101_strawberry_transport` lleva la fresa libre a un recipiente y la
deja apoyada y estable, con la pinza abierta y retirada. Añade ajuste del cierre
mediante sensores virtuales durante el movimiento y resistencia a la rodadura
en el fondo. Ambas hipótesis de contacto siguen sin calibrar en fruta real.
La [guía de transporte](so101-fresa-transporte.md) recoge el programa, los
parámetros y las condiciones que distinguen sostener sobre el recipiente de
depositar dentro.

## Unión liberable por carga

`so101_strawberry_detachment` sustituye el temporizador por una unión puntual
en el cáliz. Su programa inclina y retira el fruto con la API pública; el entorno
evalúa carga e inclinación relativas y exige retenerlo libre después. La
[guía de desprendimiento](so101-fresa-desprendimiento.md) documenta las mediciones
publicadas, las hipótesis pendientes de calibración y cómo reproducir la prueba.

El perfil `so101_strawberry_detachment_cases` añade selección explícita por semilla
y registro de la identidad de cada condición. La [guía de casos](so101-fresa-casos.md)
describe las particiones; el [plan de tareas](plan-so101-fresas.md) separa esta
base de la futura campaña de mejora con el agente LLM.
