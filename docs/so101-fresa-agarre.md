# Segunda tarea de fresas: contacto de ambos dedos

Esta lección acerca la pinza de lado a la fresa, cierra hasta detectar contacto
en ambos dedos, lo mantiene al menos medio segundo, abre y vuelve al inicio.
La fresa sigue rígida y unida a la planta. El ejercicio comprueba geometría y
contactos opuestos; el ensayo de retención después de desprenderla vendrá después.

## Repetir el ejercicio

Desde la terminal Ubuntu:

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
cap-harness run --benchmark so101 --suite so101_strawberry_grasp_contact \
  --task-id 0 --seed 1 \
  --program examples/robosuite/so101_strawberry_grasp_contact.py \
  --output-root outputs/local/so101-grasp-contact --max-steps 400 \
  --camera-width 640 --camera-height 640
```

El [programa](../examples/robosuite/so101_strawberry_grasp_contact.py) utiliza la
API pública de ASPIRE. Las posturas se prepararon para esta escena fija; la fruta
tiene coordenadas declaradas y todavía no se localiza mediante visión.

## Qué cambia respecto a la aproximación

La pinza tiene un dedo fijo y otro que gira. El programa coloca el giro de muñeca
a 90° para cerrar desde un lateral y evitar el pedúnculo. La referencia oficial
`so101_gripperframe` está cerca del extremo del dedo fijo; no es el centro de una
apertura simétrica. Por eso el centro del fruto se sitúa a 21 mm en el eje Z de
esa referencia para preparar el cierre.

El brazo avanza mediante puntos de paso articulares. Después reduce la apertura
por etapas y lee `so101.get_finger_contacts()`. Al detectar una fuerza normal
superior a 0,1 N en cada dedo, mantiene ese objetivo de apertura. No ordena llegar
al tope de cierre atravesando el objeto. Al terminar abre y retira la pinza para
que el ejercicio se pueda repetir.

```python
sensors = so101.get_finger_contacts()
fixed_force = sensors["fixed"]["normal_force_n"]
moving_force = sensors["moving"]["normal_force_n"]
```

Estas lecturas son **sensores virtuales de la simulación**. No representan sensores
táctiles que incluya el SO-101 de serie. Informan de contactos en los extremos
de los dedos con cualquier objeto; no entregan etiquetas de fruta, puntuaciones
ni el estado interno del evaluador.

Se conservan las mallas, masas y parámetros de los motores del modelo importado.
Los contactos de MuJoCo con mallas usan su representación convexa, que puede
diferir de superficies cóncavas de las piezas impresas. El fruto tampoco se
deforma: este ejercicio no predice magulladuras ni demuestra un agarre seguro en
una fresa real.

## Condiciones para completar la tarea

El evaluador exige estas relaciones en orden:

1. Alcanzar la zona de agarre con la pinza abierta y la postura estable.
2. Contactar con las superficies distales de ambos dedos sobre el fruto durante
   al menos 0,5 s continuos. Los contactos deben estar en lados opuestos, separados
   al menos 20 mm y con normales suficientemente enfrentadas.
3. Abrir, eliminar los contactos y volver a la postura inicial con otra pausa estable.

Cerrar la pinza en el aire, tocar con un solo dedo o conseguir únicamente un
contacto breve no completa la tarea. Los contactos de otras partes del robot con
la fruta, el pedúnculo, las hojas, la maceta o la mesa, y los contactos del robot
consigo mismo, invalidan el intento.

Cada paso físico de 2 ms comprueba también un límite de 12 N por dedo y una
penetración máxima del modelo de 1,5 mm. Son límites didácticos para rechazar
exceso de cierre e interpenetraciones; **no son umbrales de daño calibrados para
fresas reales**. Una violación queda registrada aunque el programa abra después.

El informe `evaluation/so101-task.json` conserva el instante del contacto sostenido,
sus posiciones, normales y fuerzas, los máximos de todo el episodio, la apertura
y la retirada. `program_ok=true` solo acredita que terminó el código; además debe
aparecer `task_success=true` para estas condiciones de contacto.

## Resultado verificado

Resultado medido el 18 de octubre de 2026:

- `program_ok=true` y `task_success=true` para `so101_strawberry_grasp_contact`.
- 220 pasos: 11 segundos simulados.
- Contactos opuestos sostenidos durante 0,722 s; separación de 32,0 mm y producto
  de normales de −0,799 en la comprobación del evaluador.
- Fuerzas simuladas en esa comprobación: 0,315 N en el dedo fijo y 3,504 N en el
  móvil. Los máximos del episodio fueron 3,157 N y 7,191 N, respectivamente.
- Apertura normalizada elegida por las lecturas: 0,246. Penetración máxima del
  modelo: 0,271 mm, por debajo del límite didáctico de 1,5 mm.
- Reapertura y retirada verificadas, sin contactos prohibidos ni violaciones de límites.
- Dos vídeos completos de 221 fotogramas, 640×640 píxeles.
- 142 pruebas aprobadas: cinco del nuevo ejercicio y 137 de regresión.

El resultado completo está en
`outputs/local/so101-grasp-contact-demo/run-20261018T085020.912435Z-e5ac507a`.
Los vídeos son `media/videos/agentview.mp4` y `media/videos/sideview.mp4`.
El informe de revisión es `validation-artifacts/setup/grasp-contact-review.json`.

## Próximo paso: retención

La planta soporta el fruto durante esta prueba. La siguiente
[lección de retención](so101-fresa-retencion.md) incorpora una fijación liberable,
masa y gravedad, y compara contactos puntuales con contactos que transmiten
rozamiento torsional. Conserva tanto el fallo por caída como la retención
condicionada al modelo de contacto. Después podremos ensayar transporte,
depósito, giro y tracción, y comparar con una herramienta que sujete y corte.
