# Primera fresa: aproximación y retirada con ASPIRE

Esta lección añade una maceta, hojas, pedúnculo y una fresa a la simulación del
SO-101. El brazo orienta la pinza abierta hacia el fruto, se acerca al marcador
azul, mantiene la posición y vuelve a su postura inicial. La escena y el programa
quedan guardados para repetir y estudiar el ejercicio.

## Ejecutarlo en la terminal Ubuntu

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
cap-harness run --benchmark so101 --suite so101_strawberry_approach \
  --task-id 0 --seed 1 \
  --program examples/robosuite/so101_strawberry_approach.py \
  --output-root outputs/local/so101-strawberry --max-steps 300 \
  --camera-width 640 --camera-height 640
```

El comando imprime la carpeta de resultados. Cada intento conserva su propio
programa, mediciones y vídeos, incluidos los intentos fallidos.

## Entender el movimiento

El [programa](../examples/robosuite/so101_strawberry_approach.py) utiliza solo la API
pública de ASPIRE: `get_robot_state`, `so101.get_task_metadata`, `move_to_joints`
y `step`. Las órdenes se ejecutan sobre el modelo SO-101 importado en
Robosuite/MuJoCo. El programa no accede al estado interno del simulador.

1. **Orientación:** el brazo gira con la herramienta a cierta distancia del fruto.
2. **Aproximación:** la referencia de la pinza llega al marcador azul y mantiene
   el objetivo durante diez pasos de control, equivalentes a medio segundo.
3. **Retirada:** recorre las posturas anteriores en orden inverso y vuelve al inicio.

Cada postura contiene cinco ángulos en radianes, uno por articulación del brazo.
La pinza permanece abierta. Esas posturas se prepararon para esta escena concreta:
no constituyen un planificador que encuentre caminos para cualquier planta.

| Dato | Valor y significado |
| --- | --- |
| Referencia medida | `so101_gripperframe`, el sitio definido por el modelo oficial. |
| Sistema de coordenadas | `so101_base`, coincidente con el mundo en esta escena. |
| Objetivo de aproximación | x=0,300 m; y=0; z=0,240 m. |
| Centro de la fresa | x=0,365 m; y=0; z=0,240 m. |
| Separación nominal | 6,5 cm entre la referencia de la pinza y el centro de la fresa. |
| Margen de posición admitido | 8 mm; es una tolerancia didáctica de simulación. |
| Dirección de la herramienta | Eje X hacia +X de la base, con error máximo de 10°. |

El marcador azul es una referencia visual que no produce contactos. La distancia
de 6,5 cm no es una medición de holgura entre todas las superficies de los dedos y
la fruta. La fresa, el tallo y las hojas son cuerpos rígidos fijos en esta lección.

## Cómo se decide si salió bien

El evaluador exige llegar al objetivo, mantener una postura estable durante al
menos 0,25 segundos observados y regresar a la postura inicial con otra pausa
estable. A 20 Hz se exigen seis observaciones consecutivas, que abarcan cinco
intervalos. La pinza debe permanecer abierta durante todo el episodio.

Los contactos entre robot y planta, fruta o mesa, y los contactos del robot consigo
mismo, invalidan el intento. Se inspecciona cada paso físico de MuJoCo (2 ms),
incluido el estado resultante del último paso de cada acción. Un contacto breve
permanece registrado aunque luego el brazo se retire correctamente. La base usa
las colisiones del modelo oficial; sus limitaciones se describen en la
[guía de importación](so101-import.md).

`program_ok=true` indica que el programa terminó correctamente. Además debe
aparecer `task_success=true`, que acredita esta aproximación y retirada. Llegar
y quedarse junto a la fresa, o permanecer desde el principio en la postura inicial,
no completa la tarea.

El archivo `evaluation/so101-task.json` contiene los errores medidos, los pasos
en que se verificó cada etapa, los contactos y la comprobación de pinza abierta.
Este informe lo escribe el entorno al terminar; el programa recibe las coordenadas
declaradas del ejercicio, pero no las variables internas del evaluador.

## Qué representa este avance

Resultado verificado el 18 de octubre de 2026:

- `program_ok=true` y `task_success=true`.
- 68 pasos de control: 3,4 segundos simulados.
- Error al verificar la aproximación: 0,200 mm; error al terminar la retirada:
  0,144 mm. Son mediciones de este modelo simulado y esta escena fija.
- Error de dirección de la herramienta: 0,044°.
- Pinza abierta durante todo el episodio y ningún contacto prohibido detectado.
- Dos vídeos completos de 69 fotogramas, 640×640 píxeles.
- 137 pruebas aprobadas, incluidos los casos de aproximación sin retirada,
  cierre indebido, contacto transitorio y reinicio del evaluador.

La copia Windows del intento completo está en
`outputs/local/so101-strawberry-demo/run-20261018T083647.974361Z-d7233579`.
Los vídeos son `media/videos/agentview.mp4` y `media/videos/sideview.mp4`.
El informe de revisión está en `validation-artifacts/setup/strawberry-review.json`.

Ya existe una tarea de plantas que podemos repetir y medir con ASPIRE. La escena
es fija: cambiar la semilla no genera posiciones nuevas. El LLM preparó el programa
desde este chat; su ejecución no hace llamadas a un LLM ni utiliza SAM3.

La [siguiente lección de contacto](so101-fresa-agarre.md) ya comprueba el cierre con
ambos dedos sobre la fresa todavía unida, seguido de reapertura y retirada.
La unión liberable y la retención después de desprenderla siguen pendientes,
además de percepción, variación de escenas y un ciclo de mejora y selección de
habilidades sobre casos nuevos.
