# Tercera tarea de fresas: retención bajo gravedad

Este ejercicio comprueba si los dedos sostienen una fresa cuando la planta deja
de soportarla. La fruta es un cuerpo rígido libre de 20 g. Una fijación temporal
la mantiene en su posición hasta el segundo 8; entonces se desactiva y el fruto
queda sometido a gravedad y contactos. El programa termina manteniendo la pinza.

La liberación es una operación automática del banco de pruebas. El giro y la
tracción necesarios para romper un pedúnculo se estudiarán en una tarea posterior.

## Ejecutar desde Ubuntu

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
cap-harness run --benchmark so101 --suite so101_strawberry_retention \
  --task-id 0 --seed 1 \
  --program examples/robosuite/so101_strawberry_retention.py \
  --output-root outputs/local/so101-retention --max-steps 400 \
  --camera-width 640 --camera-height 640

# Repetir el MISMO programa añadiendo rozamiento de contacto contra el giro:
cap-harness run --benchmark so101 --suite so101_strawberry_retention_torsion \
  --task-id 0 --seed 1 \
  --program examples/robosuite/so101_strawberry_retention.py \
  --output-root outputs/local/so101-retention --max-steps 400 \
  --camera-width 640 --camera-height 640
```

El [programa público](../examples/robosuite/so101_strawberry_retention.py) usa
acciones articulares y las lecturas virtuales `so101.get_finger_contacts()`.
Los puntos de paso corresponden a esta escena conocida. Los sensores táctiles
son simulados; el SO-101 de serie no incorpora estas mediciones.

Se conservan dos variantes explícitas. `so101_strawberry_retention` usa contactos
puntuales con fricción tangencial (`condim=3`). `so101_strawberry_retention_torsion`
añade fricción torsional (`condim=4`): una aproximación al momento que puede
transmitir una zona de contacto con superficie. El programa, la masa, las mallas,
los motores y los criterios de éxito son iguales en ambas.

El programa cierra hasta superar 1 N en cada sensor virtual y mantiene la apertura
elegida. A diferencia de la lección anterior, tocar con más de 0,1 N no se usa
como punto de parada del cierre. Esta elección es didáctica y no un umbral para
manipular fresas reales.

## Cómo se distingue contacto de retención

Antes de soltar la fijación se exige el contacto opuesto de ambos dedos durante
0,5 s. Después se exigen dos segundos continuos con:

- La fijación desactivada y gravedad de 9,81 m/s².
- Contactos opuestos de los extremos originales de ambos dedos.
- Desplazamiento del fruto respecto a la pinza de como máximo 8 mm.
- Ausencia de apoyo en la planta, mesa, motores u otras partes del robot.
- Fuerzas por dedo inferiores a 12 N y penetración del modelo inferior a 1,5 mm.

Cada paso físico de 2 ms comprueba estas relaciones. Una caída o un contacto
prohibido permanece registrado aunque después desaparezca. El estado final debe
seguir cumpliendo la retención: haber sujetado antes no permite aprobar después
de soltar. El informe `evaluation/so101-task.json` conserva la trayectoria, las
fuerzas y el estado de la fijación, además de la puntuación final.

## Qué representa el modelo

La fruta tiene una articulación libre de seis grados de libertad; cáliz y semillas
la acompañan. La única restricción temporal la une a la planta. No se añade una
unión entre fruta y pinza ni se corrigen manualmente sus posiciones o velocidades
durante la ejecución. Los motores y mallas del robot conservan el modelo importado.

La fijación usa un anclaje en el centro de la fruta y parámetros de un soporte
rígido (`solref=0.004 1`, `solimp=0.999 0.999 0.001 0.5 2`). El pedúnculo termina
con una pequeña separación para evitar que su geometría solapada soporte el fruto.
Los contactos del fruto usan `solref=0.004 1`, prioridad 1 y fricción
`1 0.005 0.0001`. El contacto predeterminado de 20 ms resultaba demasiado flexible
para este cuerpo de 20 g y producía penetración excesiva.

En la variante torsional, el coeficiente de giro es 0,005 m. Este coeficiente
tiene dimensión de longitud y **no significa un radio de contacto medido**.
La variante de contactos puntuales ignora ese componente. En los primeros ensayos
los contactos puntuales permitían que el fruto girase y cayese; añadir resistencia
al giro cambia esa hipótesis física. Por ello un éxito de la variante torsional
es condicional a sus parámetros, no una mejora demostrada del programa ni una
validación de la pinza de serie. Se conserva el fallo de la variante puntual.

Estos son parámetros didácticos de cuerpos rígidos y fricción, pendientes de
calibración. Ni el límite de 12 N ni el éxito del ejercicio predicen magulladuras
o garantizan que una fresa real pueda sujetarse con esta pinza. La geometría convexa
de colisión de las mallas tampoco reproduce todos los detalles de las piezas impresas.

La configuración de la fijación sigue la
[referencia de MuJoCo 3.3.0](https://mujoco.readthedocs.io/en/3.3.0/XMLreference.html#equality-weld):
una restricción entre cuerpos que puede desactivarse durante la simulación.
La documentación también explica cómo el
[rozamiento torsional influye en el deslizamiento](https://mujoco.readthedocs.io/en/3.3.0/modeling.html#preventing-slip).

## Resultados medidos

Ejecuciones completas del 18 de octubre de 2026, semilla 1 y la misma escena:

| Medida | Contacto puntual (`condim=3`) | Contacto torsional (`condim=4`) |
| --- | --- | --- |
| Programa terminado | Sí | Sí |
| Tarea cumplida | No: caída | Sí, condicionada al modelo de contacto |
| Liberación de la fijación | 8,000 s | 8,000 s |
| Retención continua al terminar | 0 s | 2,500 s |
| Desplazamiento relativo máximo | 228,64 mm | 0,714 mm |
| Primer exceso del límite de 8 mm | 8,096 s | Ninguno |
| Máximo de fuerza en dedo fijo / móvil | 5,445 / 7,338 N | 2,792 / 5,427 N |
| Penetración máxima del modelo | 0,398 mm | 0,398 mm |

Ambas ejecuciones duran 210 pasos (10,5 s). En la variante torsional no aparecen
apoyos externos, contactos prohibidos ni violaciones de límites. Sus fuerzas
normales finales son 0,516 y 0,502 N. Los contactos resueltos por MuJoCo tienen
dimensión 4 y transmiten momentos de aproximadamente 0,000626 y 0,000595 N·m
alrededor de sus normales. Esos datos permiten comprobar qué hipótesis sostiene
el resultado.

Los resultados completos, incluidos los vídeos de ambas cámaras, se guardan en
`outputs/local/so101-retention-demo/point/` y
`outputs/local/so101-retention-demo/torsion/`. La comparación utiliza el mismo
archivo de programa y conserva su SHA-256 en `comparison.json`.
`comparacion-retencion.mp4` coloca las grabaciones originales una junto a otra,
sin cambiar la velocidad, con un indicador de liberación. El informe de auditoría
es `validation-artifacts/setup/retention-review.json`.

## Comprobar el evaluador

```bash
pytest -q tests/test_so101_retention.py
```

Las seis pruebas comprueban retención, caída libre sin dedos, caída con el modelo
puntual, duración insuficiente, fijación todavía activa o reactivada y un apoyo
en la mesa durante un solo paso físico. También comprueban que abrir después de
un éxito lo invalida y que reiniciar restablece el fruto y la fijación. Las
perturbaciones directas del simulador se usan únicamente para provocar fallos
en estas pruebas; el programa de ASPIRE utiliza exclusivamente su API pública.

Validación terminada: seis pruebas de esta lección y 142 de regresión aprobadas
(148 en total), además de Ruff y comprobación de espacios de Git. La auditoría
decodificó íntegramente los cuatro vídeos originales y el vídeo comparativo.

## Próximo ejercicio

La [lección de transporte y depósito](so101-fresa-transporte.md) añade el recipiente,
ajuste del cierre durante el movimiento y comprobación del apoyo estable.
La separación por giro y tracción tendrá después sus propias condiciones de prueba.
