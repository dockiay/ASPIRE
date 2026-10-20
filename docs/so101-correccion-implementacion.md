# Corrección de la implementación SO-101

20 de octubre de 2026. Trabajo de ingeniería previo a nuevas campañas de ASPIRE.

## Control de brazo y pinza

`so101.command_joints` acepta `gripper_position`, `gripper_speed` y
`minimum_duration_s`. La pinza puede recibir una consigna explícita durante el
movimiento del brazo, con velocidad limitada y supervisión de fuerzas/contacto
en cada subpaso. Una terminación normal conserva la consigna de pinza que
realmente llegó a emitirse; la siguiente orden explícita continúa desde ella.
Las paradas por fuerza, contacto, tiempo o violación cancelan las consignas
pendientes. El modo sin consigna explícita conserva el comportamiento anterior.

`completed` distingue la terminación normal de un `ok` que reconoce una parada
solicitada. `target_reached` describe el brazo: puede ser verdadero aunque se
haya perdido contacto. Las herramientas compartidas consultan ahora la consigna
vigente del adaptador, evitando reutilizar una apertura antigua después de una
orden específica del SO-101.

Es control de posición supervisado. La fuerza normal de los dedos es virtual;
no representa una medida del esfuerzo del tallo ni un sensor del robot real.
La finalización de `command_gripper` por fuerza sigue cancelando el cierre: el
programa debe decidir una consigna coordinada posterior a partir de la evidencia.

## Geometría de contacto

`check_joint_path(..., gripper_positions=[...])` comprueba también el barrido de
la mandíbula entre aperturas. Los puntos con contacto permitido se exceptúan
solo dentro de los límites de las almohadillas distales. Antes se exceptuaba
toda la geometría de los dedos, aunque el evaluador rechazaba contactos fuera
de esas zonas. Las cajas envolventes se usan como filtro inicial y se refinan
con la envolvente convexa de la malla: las esquinas vacías de una caja no se
consideran ocupadas. Esta corrección evitó un falso rechazo de la aproximación
archivada durante la validación. Se mantiene el alcance sobre puntos públicos:
una nube de la fruta sola no comprueba hojas o pedúnculos no suministrados.

## Visión y decisiones

La comparación RGB-D informa por separado sobre rotación y traslación mediante
`motion_components`. Una traslación significativa compatible con el movimiento
del robot ya puede reconocerse sin exigir rotación. La incertidumbre sigue
siendo heurística y las observaciones inconcluyentes conservan ese estado.

El perfil compartido por Codex y API exige usar los resultados dentro del bucle
cuando se estudia acoplamiento. El informe conserva las llamadas de visión y
acciones ordenadas. La revisión independiente distingue ausencia de visión,
diagnóstico final, ramas sin ejecutar, decisiones observadas e incertidumbre.
La mera presencia de una comparación seguida de movimiento no se acredita como
control visual. Una propuesta que afirma corregir mediante visión necesita
evidencia de esa corrección en su verificación independiente.

Esta entrega prueba herramientas y revisión. El próximo programa de cosecha
será generado por el controlador y deberá demostrar las decisiones durante su
ejecución antes de atribuirle corrección visual.

## Búsqueda y evaluación

El protocolo diverso v2 permite `phase="diagnose"` y refinamientos antes de
completar cuatro familias. Las reparaciones nombran un progenitor inspeccionado,
consumen presupuesto y pueden conservar estructura y mecanismo. Las familias
de exploración siguen exigiendo diversidad. El presupuesto es un máximo: se
permite una entrega de diagnóstico cuando un requisito repetidamente fallido
requiere ingeniería. El v1 conserva su interpretación para registros históricos.

`experiment_evidence` separa contratos aprobados, agarre observado, movimiento
supervisado posterior y disponibilidad de evidencia visual. El historial
resumido declara su cobertura. No asigna éxito a una maniobra que no llegó a
ejecutarse ni equipara una preferencia experimental con una skill verificada.

## Alcance de la física

El contrato público declara que el modelo representa flexión con tracción y
tracción recta. No contiene fractura por torsión axial ni calibración biológica.
Se exponen estas capacidades sin revelar umbrales privados o coordenadas.
La ley mecánica, los criterios de cosecha y las puntuaciones históricas no se
han ajustado para conseguir un aprobado. Identificar una ley real de torsión
requiere datos adicionales y una versión separada del benchmark.

## Paridad de herramientas: segunda revisión

La auditoría posterior reprodujo fallos que las pruebas de la primera entrega no
cubrían. Se reparan las transiciones entre herramientas propias del SO-101 y la
API compartida, además de incorporar proveedores compatibles con este robot.

| Problema | Cambio |
|---|---|
| Una orden de pinza reactivaba un objetivo cancelado del brazo | La cancelación sincroniza tanto las consignas nativas como las cachés del adaptador |
| El movimiento compartido congelaba un cierre pendiente a mitad de recorrido | Se distinguen objetivo aceptado, consigna emitida por el limitador y apertura medida; cada operación usa el valor correspondiente |
| La proyección omitida intentaba usar `robot_base` | El marco por defecto se obtiene del estado público del robot; SO-101 usa `so101_base` |
| El contrato describía permiso de contacto en todo el dedo | Contrato y comprobador coinciden: solo almohadillas distales; se comprueba el barrido de la mandíbula |
| Entradas mal formadas o guardas simultáneas producían comportamientos incoherentes | Validación tipada antes de mover o cambiar consignas; rechazo de una guarda concurrente; episodios terminados no avanzan |
| Cambiar la frecuencia cambiaba la velocidad física máxima | Los incrementos nativos se calculan por periodo: 1 rad/s para el brazo y 3 rad/s para la mandíbula |
| El perfil solo conectaba SAM3 e IK | El ejecutor configura también `so101-geometric` y el planificador `so101` |
| La reconstrucción 3D desplazaba superficies del robot fuera de su modelo | Se corrigen el centro de píxel de la cámara SO-101 y el muestreo de profundidad sin MSAA; se verifica contra un plano analítico renderizado a dos resoluciones |

El generador de agarres es una heurística geométrica propia del SO-101:
comprueba su mandíbula angular, busca poses alcanzables con IK y devuelve la
apertura, pose de preagarre y trayectoria final comprobada. El eje de aproximación
es +X del TCP; `select_grasp` respeta esa convención. Una propuesta no acredita
cierre, fuerza ni retención.

Las máscaras de SAM3 pueden incluir píxeles del fondo en el borde del fruto.
El generador busca una componente 3D dominante de los puntos observados antes
de estimar el volumen: requiere al menos un 70 % de apoyo y ninguna segunda
componente de un 20 % o más. Si hay ambigüedad rechaza la propuesta. Los puntos
descartados como parte del objeto se conservan como obstáculos, sin permiso de
contacto; el diagnóstico muestra el filtrado y las causas de rechazo por intento.

El planificador usa búsqueda RRT-Connect acotada sobre la geometría del robot y
puntos RGB-D públicos. Comprueba primero el camino directo y busca un desvío
si está obstruido. Conserva la fruta como obstáculo y permite contacto solo en
las almohadillas cuando se suministra `target_point_cloud`; el brazo y el resto
de los dedos siguen comprobándose contra ella. Un cierre pendiente se planifica
con el brazo quieto antes del tránsito. Si no encuentra un camino devuelve un
fallo explícito, sin cambiar a interpolación.

El espacio de trabajo para la fusión de profundidad se deriva de una cota
conservadora de todas las geometrías del modelo, incluida la mandíbula:
±0,58385088 m respecto a la base. Descarta fondo fuera de alcance antes de
voxelizar; no recorta una región arbitraria alrededor de la fresa.

La calibración de las cámaras reveló dos errores adicionales: la proyección
usaba el centro en `(ancho/2, alto/2)` en vez de `((ancho-1)/2, (alto-1)/2)`, y
el suavizado MSAA de cuatro muestras no producía profundidad correspondiente
al rayo central. El SO-101 ahora renderiza RGB y profundidad sin MSAA y publica
los intrínsecos correctos. La prueba independiente del plano reduce el error
RMS a aproximadamente 1,7 micras a ambas resoluciones (64×48 y 1280×960), frente
a 0,46 mm con los intrínsecos anteriores a resolución completa sin MSAA.
No se reescriben las imágenes ni resultados de campañas anteriores.

La profundidad usa además un rango métrico fijo de 2 cm a 5 m. El rango anterior
dependía de la extensión compilada de la escena: en FruitGym empezaba a 0,679 mm
y terminaba a 33,97 m, perdiendo precisión en el banco. Corregirlo permite conservar
la misma tolerancia numérica de 10 micras también en FruitGym. Los metadatos
públicos indican el rango efectivo. Se comprueba que las cámaras de control y
FruitGym contienen la esfera conservadora de alcance; otras cámaras siguen
limitadas a su campo visible y rango, sin certificar espacio oculto.

El filtrado del propio robot incluye sus mallas visuales además de las de
colisión: ambas aparecen en la cámara. Admite una tolerancia numérica de
10 micras, separada del margen de planificación de 3 mm. Las pruebas conservan
obstáculos a 0,1 mm de la superficie y los puntos del objeto de contacto.
Una superficie que coincida con la del robot sigue siendo visualmente ambigua;
el diagnóstico declara este límite.

Estos proveedores dan acceso mediante `generate_grasps`, `select_grasp`,
`plan_motion` y `execute_trajectory`. La configuración predeterminada vive en
`so101.integration.make_api`, utilizada por el ejecutor estándar para Codex y API.
No son Contact-GraspNet ni cuRobo, y no heredan sus prestaciones. Los comandos
directos de articulaciones siguen sin buscar desvíos automáticamente.
Las propuestas comprueban hasta 4.096 muestras del objeto y 4.096 de obstáculos;
los puntos descartados de la máscara tienen prioridad y se conservan todos.
La escena del planificador se voxeliza a 1 cm y se comprueba mediante muestreo
de la trayectoria. Los huecos entre muestras pueden ocultar geometría fina;
estas comprobaciones no equivalen a detectar toda posible colisión.

Persisten límites explícitos: cinco ejes no permiten toda pose 6D; los puntos
visibles no certifican espacio oculto ni seguimiento físico; el control sigue
siendo de posición supervisada, sin regulación continua de fuerza. La ley de
rotura y los requisitos de cosecha no se alteran para facilitar los resultados.

La evidencia de esta revisión se conserva en
`outputs/local/so101-control-parity-repair-20261020/`; incluye las reproducciones
anteriores y posteriores y comprobaciones de integración con SAM3 real.

## Verificación de paridad (T30)

La regresión final aprueba **423 pruebas**, sin fallos ni omisiones. Incluye la
regresión de T29, control nativo, API compartida, contratos, ejecución restringida,
grabación, propuestas de agarre, planificación, calibración, búsqueda y skills.
Ruff y `git diff --check` pasan. Las fuentes están sincronizadas con Ubuntu y
archivadas junto con sus hashes en el
[informe de validación](../outputs/local/so101-control-parity-repair-20261020/validation.json).

Resultados de integración a 1280×960:

- La cancelación del brazo deja de reactivarse al enviar una orden de pinza.
- Un cierre solicitado a 0,25 se conserva durante los movimientos compartidos;
  la apertura medida final es 0,249998.
- El planificador funciona con ambas cámaras en control y FruitGym. Un fixture
  independiente demuestra un desvío RRT alrededor de un obstáculo que bloquea
  el camino directo; un objetivo dentro del obstáculo se rechaza.
- SAM3 detecta la fresa en ambas vistas. Cada una produce una propuesta de agarre
  y un plan de preagarre válidos incluyendo la nube observada de la escena,
  con los límites de muestreo descritos arriba.
- La percepción y planificación no avanzan la simulación. El movimiento de
  comprobación de control sí se ejecuta con la API y el ejecutor estándar, dejando
  vídeos y trazas. Su `program_ok=true` no implica resolver el benchmark de control
  completo ni cosechar una fresa.

Los resultados completos están en
[integración nativa](../outputs/local/so101-control-parity-repair-20261020/native-integration-v4/results.json)
y [regresión final](../outputs/local/so101-control-parity-repair-20261020/final-regression-tests.xml).
Los intentos fallidos anteriores se conservan como evidencia de diagnóstico.
No se ejecuta una campaña de aprendizaje ni se promueve ninguna skill; la
biblioteca conserva los mismos hashes y dos habilidades anteriores.

## Verificación de la primera entrega (T29)

La regresión final aprueba **215 pruebas**, sin fallos ni omisiones, incluyendo
control nativo, API compartida, geometría, comparación visual, búsqueda,
procedencia y verificación de skills. Ruff y `git diff --check` también pasan.
El informe de pruebas está en
[`final-regression-tests.xml`](../outputs/local/implementation-repair-20261020/final-regression-tests.xml).

La prueba A/B reproduce el prefijo de agarre de un programa archivado mediante
SAM3 y compara estados físicos iniciales completos por hash. Después aplica
excitaciones de ingeniería: mantener el brazo o pedir 0,05 rad adicionales de
muñeca, con apertura medida o cierre explícito supervisado. Los registros de
contactos, esfuerzo del actuador, consigna y deslizamiento son mediciones del
anfitrión; no se pasan al agente como un sensor privilegiado.

Los resultados y fuentes ejecutadas están en
`outputs/local/implementation-repair-20261020/`. Estas comprobaciones no son
nuevas campañas de aprendizaje, habilidades promovidas ni validación agrícola.

La primera comparación (`grip-ab/`) completó ocho pruebas con estados iniciales
idénticos por caso. Al girar, el modo de apertura medida perdió contacto a
0,66°/0,14° de muñeca; el cierre coordinado llegó a 1,92°/2,38° y paró por fuerza.
El pico máximo fue 11,56 N y no hubo parada nativa por violación. Esto demuestra
que el control de cierre cambia la respuesta, pero aún no certifica un agarre
que permita desprender. La orden de cerrar completamente también acumula
presión: la política tendrá que elegir la consigna, no mantener cierre ilimitado.

Después se corrigió la continuidad de consignas entre tramos. El intento
`grip-ab-final/` se conserva como fallo de preparación por la caja envolvente.
`grip-ab-final-v2/` ejecutó el contraste en el caso 0, pero el margen geométrico
de 3 mm impidió preparar el caso 1001. Esos fallos no se cuentan como giros.

El contraste final `grip-ab-fixture-final/` emplea un margen geométrico de 0 mm
solo al preparar el fixture de ingeniería, declarado en el informe y en su
prefijo guardado. Conserva la misma aproximación y física, las comprobaciones
de intersección y las guardas nativas. Esto permite aislar la diferencia entre
consignas sin presentar la trayectoria como una nueva solución de ASPIRE.
Los programas futuros deberán gestionar el margen solicitado y sus rechazos.

El contraste final completó los cuatro movimientos, con estados iniciales
idénticos por pareja. Ninguno terminó la maniobra solicitada:

| Caso | Control de pinza | Giro medido de muñeca | Motivo de parada | Pico normal en un dedo |
|---|---|---:|---|---:|
| 0 | Apertura medida | 0,66° | Pérdida de contacto | 1,33 N |
| 0 | Cierre coordinado | 1,92° | Límite de fuerza | 11,60 N |
| 1001 | Apertura medida | 0,14° | Pérdida de contacto | 0,81 N |
| 1001 | Cierre coordinado | 2,31° | Límite de fuerza | 11,08 N |

El umbral solicitado fue 11 N; la dinámica produjo un sobrepaso de hasta 0,60 N.
No hubo una parada por violación del límite nativo. Estos ángulos corresponden
a la muñeca, **no prueban el giro de la fresa**. El resultado confirma una
diferencia en el mantenimiento de contacto y el funcionamiento de las paradas;
no establece una consigna estable de fuerza ni una habilidad de desprendimiento.
Datos completos en
[`summary.json`](../outputs/local/implementation-repair-20261020/grip-ab-fixture-final/summary.json),
con muestras cada 2 ms, imágenes antes/después y fuentes ejecutadas archivadas.

## Estado de la entrega

La corrección de herramientas y protocolo queda implementada y validada.
Los archivos están sincronizados con el entorno de Ubuntu. La biblioteca
verificada conserva sus dos habilidades anteriores; no se ha promovido ninguna
nueva. Sigue pendiente demostrar una política que regule el agarre durante el
movimiento y ejecute correcciones visuales, y calibrar una futura ley de rotura
por torsión. Estas comprobaciones no acreditan una cosecha completa.
