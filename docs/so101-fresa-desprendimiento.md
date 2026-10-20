# Una fresa: inclinar, cargar la unión y retirarla

Esta prueba añade una unión liberable al SO-101 importado. Sustituye el reloj
de la lección de retención por una condición basada en la reacción física de
la unión y el movimiento relativo del fruto. Es un **banco mecánico provisional**,
con fuerzas de referencia publicadas; todavía no identifica la fractura de un
pedúnculo real ni acredita que una fresa quede sin daños.

## Qué respalda la investigación

[Dimeas et al., Robotica, DOI 10.1017/S0263574714001155](https://doi.org/10.1017/S0263574714001155)
([postprint del autor](https://www.researchgate.net/publication/269516901_Design_and_fuzzy_control_of_a_robotic_gripper_for_efficient_strawberry_harvesting)),
sección 2.2, tabla 1: nueve frutos frescos de una misma variedad, no especificada.
El pedúnculo se fija a un medidor de fuerza y se compensa el peso del fruto.

| Maniobra | Diámetro medio del tallo, mm | Fuerza de separación, N |
|---|---:|---:|
| Tracción directa A | 2,69 | 22,00 |
| A | 1,95 | 10,00 |
| A | 1,87 | 9,81 |
| Flexión y tracción B | 1,77 | 2,78 |
| B | 1,79 | 3,76 |
| B | 1,68 | 2,31 |
| B | 2,19 | 1,57 |
| B | 1,76 | 5,10 |
| B | 1,53 | 3,53 |

Las medias son 13,9367 N y 3,175 N. Son grupos pequeños, distintos y no pareados:
no permiten ajustar una ley universal ni aislar el efecto del diámetro. Los
autores describen flexión seguida de retirada, no una medición de torsión axial.
Su prueba de compresión usa espuma de poliuretano de 1 cm y látex: sus resultados
no establecen un límite seguro para los dedos rígidos del SO-101.

[Yamamoto, Hayashi, Yoshida y Kobayashi, JARQ 48(3), 261–269, 2014](https://doi.org/10.6090/jarq.48.261)
([PDF, páginas 263 y 266](https://www.jircas.go.jp/sites/default/files/publication/jarq/48-03-02_0.pdf)):
ensayan Beni hoppe a 50 mm/min y ángulos de tracción de 0°, 45° y 90°.
Al tirar a 90° favorecen separación en la capa de abscisión; la tracción recta
puede romper el tallo por otro punto. El robot usa inclinación de 70° para evitar
choques con la bancada. Ese ángulo operativo no es un ángulo crítico de rotura.
La figura 3 presenta dispersión, no una función continua fuerza/ángulo.

## Hipótesis explícitas del banco

Una restricción nativa `connect` une el punto local `(0, 0, 0.024)` m del fruto
con la planta. Permite rotar y una pequeña deformación numérica de traslación.
No hay unión fruto-pinza. La gravedad, los contactos, la masa de 20 g y los
actuadores originales determinan el movimiento. Se mantienen los límites
didácticos anteriores de fuerza, penetración, deslizamiento y colisiones.

Se registra la reacción de **esa igualdad**, aislando sus filas de `efc_force`
y aplicando el Jacobiano transpuesto. No se confunde con la fuerza de cierre
de los dedos. Al vector de reacción se resta el soporte del peso inicial.
La norma resultante sirve como carga incremental del banco. La velocidad
puede introducir carga inercial: no se ha ajustado una ley dependiente de tasa.
El producto fuerza/desplazamiento registrado como `outward_work_j` es sólo una
prueba de signo, no trabajo integrado ni energía de fractura.

La unión se desactiva irreversiblemente durante el episodio si:

1. La carga compensada alcanza 3,175 N y la inclinación del eje del fruto
   respecto al tallo alcanza 70°; o alcanza 13,9367 N con inclinación de hasta 15°.
2. El punto de unión se ha desplazado al menos 0,1 mm respecto a su anclaje,
   proyectado sobre el eje del fruto en dirección opuesta al pedúnculo, y
   el producto carga exterior/desplazamiento es positivo, rechazando compresión.

Los 70°, 15° y 0,1 mm son **condiciones del escenario**, no resultados de una
identificación biológica. No se interpola entre los dos regímenes ni se afirma
que otros ángulos impidan la rotura real. Las dos medias proceden de grupos
distintos: combinar estos modos en un mismo fruto sintético es una hipótesis.
Ni alcanzar un ángulo sin carga ni esperar libera la fresa.
El modo de tracción recta es un control mecánico de carga, no una predicción de
separación limpia: el banco no distingue rotura intermedia del tallo, pérdida del
cáliz ni daño del fruto. Tampoco mide un momento crítico de torsión axial.

`solref=(0.01, 1)` y `solimp=(0.9, 0.9, 0.001, 0.5, 2)` controlan la
deformabilidad de la restricción. No son constantes elásticas de tejido medidas.
La articulación no ofrece una resistencia elástica a la flexión identificada;
esto puede facilitar artificialmente la inclinación. La fricción torsional
fruto-dedos continúa sin calibrar. Véase la
[documentación de MuJoCo 3.3.0](https://mujoco.readthedocs.io/en/3.3.0/modeling.html#solver-parameters).

Al liberar sólo cambia `eq_active`: no se reposiciona el fruto, no se cambia
su velocidad, no se añade impulso y no se sustituye por otro objeto. El éxito
exige conservarlo libre durante 2 s, con contacto bilateral, sin apoyos ajenos
y con menos de 8 mm de deslizamiento respecto a la pinza.

## Qué falta medir para hablar de realismo biológico

Con frutos de la variedad, madurez y tamaño deseados: fuerza y momento frente
a desplazamiento y ángulo, localización de la separación, velocidad de carga,
variación entre frutos y daño superficial o magulladura posterior. Medir también
rigidez y amortiguación del pedúnculo/planta, fricción y presión con las futuras
yemas. Sin esos datos no hay un par de rotura ni una distancia de retirada
universal defendibles. El siguiente ajuste debe usar datos reservados para
validación, además de los usados para calibrar.

## Ejecutar

```bash
cap-harness run --benchmark so101 --suite so101_strawberry_detachment \
  --task-id 0 --seed 1 \
  --program examples/robosuite/so101_strawberry_detachment.py \
  --output-root outputs/local/so101-detachment --max-steps 1000 \
  --camera-width 640 --camera-height 640
```

Los puntos de la maniobra se calculan previamente con la cinemática del modelo;
el programa ejecutado utiliza sólo la API pública. Este perfil mantiene una sola
posición conocida y sensores de contacto virtuales. No usa SAM3 ni estima el
pedúnculo visualmente. El resultado y las trazas físicas se guardan en
`evaluation/so101-task.json`, fuera del acceso del programa.

## Maniobra y sensibilidad observadas

Con los dedos de lado, el programa incrementa `wrist_roll` desde 90° hasta
160° y compensa la traslación del punto de unión con las otras articulaciones.
Después solicita una retirada de hasta 15 mm sobre el eje girado del fruto.
Los siete tramos de inclinación duran 1,5 s cada uno. Las retiradas nominales
de 1, 2, 4, 8 y 15 mm también duran 1,5 s por tramo; la velocidad no coincide
en todos ellos con la del ensayo de Yamamoto. No se afirma calibración de tasa.

El caso central libera la unión a 3,193 N y 75,48° efectivos, con extensión
proyectada de 1,439 mm. Al final conserva contacto bilateral durante 3,138 s
continuos y el máximo deslizamiento es 4,307 mm. No registra contactos prohibidos.
La menor distancia angular a un límite articular es 0,04683 rad, unos 2,68°:
la muñeca queda cerca del tope en esta dirección. Esto verifica una trayectoria
concreta; no calcula todo el espacio de movimientos factibles.

La geometría de la planta es rígida y simplificada; la comprobación de choques
se limita a los volúmenes de colisión disponibles. La base del modelo oficial
no tiene colisión. La fuerza máxima inicial de los dedos alcanza 9,30 N en uno
de ellos: cumplir el límite didáctico de 12 N no demuestra ausencia de daño real.

| Cambio sobre el caso central | Separación | Retención final válida |
|---|---|---|
| Umbral 1,57 N | Sí, a 1,58 N, antes de la retirada nominal | No: no acredita contactos opuestos estables |
| Umbral 3,175 N | Sí, a 3,19 N | Sí |
| Umbral 5,10 N | No; carga máxima 4,67 N | No |
| Deformabilidad con `solref` 0,008 s | Sí, a 3,18 N | No: no acredita contactos opuestos estables |
| Deformabilidad con `solref` 0,012 s | Sí, a 3,19 N | Sí |
| Puerta angular supuesta de 60° | Sí | Sí |
| Puerta angular supuesta de 80° | No | No |

Estas siete variantes de una misma escena no son siete frutos independientes ni
una tasa de éxito biológica. El programa termina sin errores en todas, pero la
evaluación física conserva sus fallos. La sensibilidad confirma que hay que
mejorar el agarre y medir la unión antes de extrapolar al robot y fruto reales.

Para repetir la sensibilidad con el mismo programa público:

```bash
python scripts/evaluate_so101_detachment.py \
  --output outputs/local/so101-detachment-sensitivity.json
python -m pytest -q tests/test_so101_detachment.py
```

Las pruebas comprueban también espera sin separación, flexión sin retirada,
tracción frente a compresión, fuerza conocida sobre la unión, pérdida posterior
del fruto y restauración del estado al reiniciar.

Validación local del 19 de octubre de 2026: **51 pruebas aprobadas**, incluidas
las 16 nuevas y regresiones de retención, transporte, adaptador, registro y
grabación. Ruff sin incidencias. La ejecución de ASPIRE registró 590 pasos,
29,50 s simulados y 591 fotogramas por cámara, con `program_ok=true` y
`task_success=true`. La copia revisada está en
`outputs/local/so101-detachment-demo/run-20261019T092012.133876Z-b7374d05` y el
vídeo comentado en `outputs/local/so101-detachment-demo/flexion-y-desprendimiento.mp4`.
