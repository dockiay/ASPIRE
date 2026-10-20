# Aprender ASPIRE para cosechar fresas con un futuro SO-101

El trabajo vigente sigue el [plan de adaptación](plan-so101-fresas.md) y el
[flujo ASPIRE con Codex o API](so101-iterative-debugging.md). Las lecciones de
esta guía son referencias de aprendizaje; la estrategia de cosecha de la
campaña actual la genera y corrige el agente mediante herramientas públicas.

Objetivo acordado: aprender a crear y ejecutar simulaciones con ASPIRE para,
a largo plazo, usar un SO-101 que desprenda fresas de una planta y las deposite
en un recipiente. El método de separación queda abierto: la primera hipótesis a
evaluar será sujetar, girar y desprender conservando el fruto en la pinza; se
comparará con sujetar y cortar el pedúnculo.
El robot todavía no se ha comprado. La simulación debe ayudar a decidir la
disposición de la planta, la cámara y la herramienta, además de aprender a programar.

## Qué aporta cada componente

- **ASPIRE:** ejecuta programas que observan y controlan el robot mediante su API,
  y conserva resultados, trazas y vídeos para revisar cada intento.
- **Robosuite:** define el robot, las cámaras, los objetos y las reglas de la tarea.
- **MuJoCo:** calcula el movimiento y los contactos de los modelos simulados.
- **Nuestro desarrollo:** la escena de fresas, la integración del SO-101, el modelo
  de herramienta y las condiciones que acreditan aproximación, desprendimiento y depósito.

Podemos empezar con programas cortos y deterministas. Entrenar una política o
conectar servicios de percepción no es un requisito para la primera lección.

## Punto de partida verificado

En este PC ya funciona una simulación LIBERO-Pro con Panda, incluida la apertura,
cierre y reapertura de la pinza y la grabación de dos cámaras. El lanzador es
[`scripts/run_wsl_example.sh`](../scripts/run_wsl_example.sh) y el programa es
[`examples/libero/gripper_demo.py`](../examples/libero/gripper_demo.py).

Desde PowerShell:

```powershell
wsl -d Ubuntu-24.04 -- bash /mnt/d/AI/Aspire/scripts/run_wsl_example.sh
```

La ejecución ocurre en `/home/sergio/src/ASPIRE`. Al editar ejemplos, trabajar en
esa copia o copiar allí el archivo modificado: editar únicamente `D:\AI\Aspire`
no cambia automáticamente el programa que ejecuta Ubuntu.

Primera lectura del resultado: `program_ok=true` acredita que el programa terminó
sin fallos. `task_success=false` es esperado en esta demostración, porque no intenta
resolver la tarea de colocar una lata. Revisar también el vídeo y las aperturas
medidas en `source/program-result.json`.

El entorno dedicado `.venv-robosuite` ya está preparado y verificado con Python
3.11.17, Robosuite 1.4.0 y MuJoCo 3.3.0. El 17 de octubre se ejecutó también el
ejemplo de pinza mediante ASPIRE en `cube_lifting`: `program_ok=true`, 90 pasos,
apertura 0,988 → 0,015 → 0,985 y dos vídeos comprobados de 91 fotogramas cada uno.
La copia Windows está en `outputs/local/robosuite-demo`.

WSLg/GLFW funciona con ambas simulaciones; `glxinfo -B` identifica D3D12 en la
RTX 4090. El requisito de EGL NVIDIA del diagnóstico oficial sigue sin cumplirse.
El modelo oficial SO-101 ya está descargado a una revisión fija e importado en una
escena de Robosuite/MuJoCo: se verificaron los seis motores, la conservación de
parámetros físicos y la reapertura del XML exportado. Hay un visor 3D y un vídeo.
La API pública de acciones de ASPIRE también está conectada: el perfil `so101`
completó la tarea de control de cinco ejes y pinza, con vídeo y mediciones.
La primera escena de fresas ya está implementada como
`so101_strawberry_approach`: una planta rígida y fija, una fresa y un marcador
para acercarse con la pinza abierta y retirarse. La ejecución está verificada con
`program_ok=true` y `task_success=true`, con dos vídeos y mediciones.
La segunda tarea, `so101_strawberry_grasp_contact`, verifica contactos opuestos de
ambos dedos sobre la fresa todavía unida, seguida de reapertura y retirada.
La tercera [lección de retención](so101-fresa-retencion.md) libera una fresa de
20 g y compara el mismo programa con dos modelos de contacto: puntual y con
rozamiento torsional. El resultado depende de esa hipótesis física, aún sin calibrar.
La cuarta [lección de transporte y depósito](so101-fresa-transporte.md) añade
control del cierre durante el traslado y exige que el fruto quede dentro del
recipiente, apoyado y estable, después de retirar la pinza.
Véanse [aproximación a la fresa](so101-fresa-aproximacion.md),
[SO-101 con ASPIRE](so101-aspire.md), [importación SO-101](so101-import.md) y
[primeros pasos locales](primeros-pasos-locales.md).

## Progresión de ejercicios

| Paso | Qué construiremos | Qué aprenderás | Evidencia de que funciona |
| --- | --- | --- | --- |
| 1. Control básico | Un ejemplo breve con Panda en una tarea existente de Robosuite: pequeño movimiento articular y vuelta a la postura inicial. | Ejecutar un programa, leer articulaciones, cambiar un objetivo y revisar resultados. | Movimiento medido, retorno dentro de la tolerancia elegida y vídeo coherente. |
| 2. SO-101 | Modelo oficial y control de sus cinco articulaciones de brazo y su pinza, ya integrados y verificados. | Límites articulares y seguimiento de objetivos con mediciones. | Movimiento de cada eje, retorno a la postura inicial y cierre y reapertura de la pinza. |
| 3. Primera planta | Maceta, fresa, pedúnculo y hojas rígidos y fijos; aproximación y retirada con SO-101 implementadas y verificadas. | Crear objetos, configurar cámaras, entender coordenadas y comprobar contactos. | Llegar al objetivo, mantener la postura y retirarse con la pinza abierta y sin contactos prohibidos. |
| 4. Contacto de los dedos | Cierre sobre una fresa rígida unida, reapertura y retirada, implementados y verificados. | Geometría de la pinza, sensores virtuales y límites del modelo. | Contactos de ambos dedos en lados opuestos durante al menos medio segundo, dentro de los límites didácticos. |
| 5. Retención | Fresa libre de 20 g, liberación programada y comparación de contacto puntual y torsional. | Distinguir contacto de agarre, y resultado del programa de hipótesis físicas. | Dos segundos sin apoyos, con contactos opuestos y desplazamiento relativo menor de 8 mm; conservar también los fallos. |
| 6. Cosecha simplificada | Comparar agarre con giro y tracción frente a sujeción y corte; unión con desprendimiento condicionado, transporte y depósito. | Separar acercamiento, agarre, desprendimiento, transporte y depósito en estados verificables. | Unión liberada según el modelo elegido, fruto retenido después de separarse y depositado en el recipiente. |
| 7. Variación y visión | Cambiar posiciones, orientación de pedúnculos, hojas y cámaras; localizar objetivos a partir de imágenes. | Percepción, oclusiones, recuperación y evaluación con casos nuevos. | Tasas separadas de detección, agarre, desprendimiento y depósito; caídas, colisiones y fallos conservados. |

El Panda del comienzo sirve para aprender el ciclo de trabajo. Las conclusiones
sobre alcance, orientación y espacio para desprender se obtendrán con el SO-101 y la
geometría de su herramienta, en el paso 3 y siguientes.

El primer movimiento articular se verificó en espacio despejado con un desplazamiento
pequeño. `move_to_joints` controla articulaciones, pero no planifica por sí mismo
una trayectoria libre de colisiones. La nueva escena usa puntos de paso articulares
preparados para esa disposición fija y comprueba contactos durante la simulación;
todavía no dispone de un planificador general para rodear obstáculos.

## Primera escena propia: acercarse a la fresa y su pedúnculo

La tarea `so101_strawberry_approach` contiene una sola fresa visible, maceta,
pedúnculo y hojas simplificados. Todos estos elementos son rígidos y permanecen
fijos. El programa aproxima la pinza abierta a un marcador situado delante del
fruto, mantiene la postura y regresa a la postura inicial. El punto de referencia
es `so101_gripperframe`, con coordenadas declaradas en `so101_base`.

La posición objetivo es un dato conocido y explícito del ejercicio. El evaluador
comprueba el error de posición, la dirección del eje de la herramienta, la
permanencia en el objetivo, la retirada y la apertura de la pinza. Los contactos
del robot con la planta, la fresa o la superficie, y los contactos del robot
consigo mismo, invalidan el intento. Las tolerancias son didácticas y no equivalen
a una precisión demostrada en el robot real. La ejecución final y sus evidencias
se documentarán en [la guía de aproximación](so101-fresa-aproximacion.md).

Este ejercicio aún no usa detección visual ni SAM3, y no implementa agarre,
desprendimiento ni una campaña de mejora y selección de programas. Sus puntos de
paso están escritos para la escena fija. En lecciones posteriores cambiaremos una
sola variable: primero la posición de la fresa,
después la inclinación del pedúnculo y después una hoja que obstaculice el acceso.
Antes de ejecutar, predeciremos el efecto; después compararemos vídeo y mediciones.

Cuando añadamos percepción, el programa recibirá observaciones de cámara y
estimaciones. El evaluador conservará la geometría real del simulador para puntuar
el error sin entregar esa información privilegiada al programa.

## Comparar giro y desprendimiento con corte

La propuesta del usuario es sujetar la fresa, girar y desprender sin soltarla. Podría
evitar el mecanismo de corte y la necesidad de capturar un fruto que cae. Retener
la fresa también es posible con un cabezal que sujete y corte; compararemos las
soluciones completas, incluyendo transporte y depósito.

Hay precedentes, pero distintas técnicas producen separaciones diferentes:
[UF/IFAS](https://ask.ifas.ufl.edu/publication/HS403) describe la recolección manual
por giro, mientras que [Purdue Extension](https://ag.purdue.edu/department/hla/extension/extension-publications-library/ext-pubs/ho-46-w.html)
recomienda pellizcar el pedúnculo conservando cáliz y una porción de tallo.
Un [estudio de cosecha robótica](https://experts.illinois.edu/en/publications/mobile-robotics-platform-for-strawberry-sensing-and-harvesting-wi/)
probó agarre blando con tracción y giro y registró tanto éxitos como daño al fruto.
Son antecedentes para experimentar, no una validación de la pinza del SO-101.

Primer experimento propuesto: una fresa aislada, un pedúnculo visible y una pinza
con geometría de contacto definida. Secuencia: aproximar, agarrar, aplicar un giro
y retirada limitados, comprobar separación y retención, transportar y depositar.
Variar tamaño, fricción, dirección de entrada y resistencia de la unión. Registrar
deslizamiento, caída, movimiento transmitido a la planta y contactos no deseados.
El cierre de la pinza o un giro de muñeca no acreditan por sí solos el agarre ni
la separación: se medirán las relaciones entre fruta, pinza y planta.

Para aprender la secuencia, el entorno puede liberar una unión al cumplirse reglas
explícitas de desplazamiento y giro relativos. Serán parámetros didácticos, sin
pretender que representan una fuerza real de rotura. La fruta deberá mantenerse
en la pinza por sus contactos; no se fijará automáticamente a ella al separarse.
La alternativa de corte liberará la unión cuando el tallo esté en la zona de
corte, la herramienta alineada y su cierre completado. Ambos métodos compartirán
escenas y criterios de retención y depósito.

La detección y liberación pertenecen al entorno; el programa de ASPIRE solicita
acciones mediante su API. Esta primera simulación no predecirá magulladuras,
deformación del tallo ni fuerzas reales de separación. Para comparar daño harán
falta datos y modelos calibrados; las fuerzas de contacto de un modelo rígido
por sí solas no demuestran que una fresa real quede intacta.

El [modelo oficial](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/so101_new_calib.xml)
incluye giro de muñeca (`wrist_roll`), pero el eje de giro debe alinearse con el
movimiento de separación requerido. No asumiremos que la pinza de serie tiene
contactos adecuados para fruta ni control preciso de fuerza. Compararemos su
geometría con dedos envolventes o recubrimientos blandos como posibles adaptaciones.
La elección de herramienta y método permanece abierta. El
[ensayo de flexión y retirada](so101-fresa-desprendimiento.md) ya añade una unión
liberada por carga física. Usa referencias experimentales, con complacencia y
condiciones angulares explícitamente provisionales; la comparación con corte y
la calibración biológica siguen pendientes.

## Integración realizada y trabajo pendiente

El [modelo oficial del SO-101](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md)
incluye URDF y MJCF y ya está importado a una revisión fija. Su documentación
advierte de diferencias en la representación de la pinza respecto a LeRobot y de
la retirada de colisiones de la base. La apertura usada en estas lecciones
interpola el ángulo entre los topes del modelo; la calibración física sigue pendiente.

El perfil `so101` ya dispone de [adaptador](../src/cap_harness/so101/adapter.py),
[codec](../src/cap_harness/so101/codec.py),
[registro de tareas](../src/cap_harness/so101/registry.py) y
[contratos de cinco articulaciones](../src/cap_harness/contracts.py).
Las tareas Panda del perfil `robosuite` conservan su control de siete articulaciones.
Los proveedores de cinemática inversa y planificación cartesiana del SO-101 siguen
pendientes de configuración o adaptación.

El control actual del SO-101 es articular. Su brazo tiene cinco articulaciones,
por lo que no podemos exigir cualquier posición y orientación de seis dimensiones
de forma independiente. Después definiremos qué orientaciones necesita realmente
la herramienta y comprobaremos su factibilidad.

La escena propia está registrada como `so101_strawberry_approach`, con su evaluación
y dos cámaras fijas. Se verificaron aproximación, permanencia, retirada y ausencia
de contactos prohibidos, además de 137 pruebas de integración y regresión.
Robosuite documenta la [composición de entornos](https://robosuite.ai/docs/tutorials/add_environment.html),
pero la documentación web es de la versión 1.5 y este checkout usa un fork 1.4:
la implementación sigue el código fijado por este repositorio.

## Próxima sesión práctica

El entorno dedicado de Robosuite, el ejemplo Panda y la importación del modelo
SO-101 ya están verificados. El ejemplo nativo del SO-101 mueve cada eje, mide su
posición y vuelve a la postura inicial, con vídeo y resultado.
Sus cinco articulaciones y su pinza ya están conectadas con la API pública de
ASPIRE y el primer programa de control está verificado.
[La aproximación a la fresa](so101-fresa-aproximacion.md) también está ejecutada,
medida y grabada. El [contacto de ambos dedos](so101-fresa-agarre.md) también está
verificado con fuerza y permanencia medidas, seguido de reapertura y retirada.
El [ensayo de retención](so101-fresa-retencion.md) ya incorpora una unión liberable
y detecta deslizamiento, caída y apoyos externos. Mantiene una comparación entre
contactos puntuales y contactos con rozamiento torsional para mostrar la influencia
de los parámetros. El [transporte y depósito](so101-fresa-transporte.md) ya está
implementado, con ajuste del agarre y comprobación del apoyo estable, conservando
explícitas esas hipótesis. El siguiente ensayo es el
[desprendimiento de una sola fresa](so101-fresa-desprendimiento.md), con flexión,
retirada y evaluación de la sensibilidad a las hipótesis de la unión.
La percepción, la cosecha completa y el ciclo de mejora
y reutilización de programas sobre casos nuevos siguen pendientes.

El [plan desglosado](plan-so101-fresas.md) organiza esa integración. Su primera
entrega es el [conjunto versionado de casos](so101-fresa-casos.md), con parámetros
de unión variables y particiones separadas para desarrollo, validación y evaluación.
