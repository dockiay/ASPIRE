# Auditoría de la adaptación SO-101 / ASPIRE

Este documento conserva el diagnóstico previo a la implementación v2.
Para el estado actual, consultar el [plan vigente](plan-so101-fresas.md) y el
[informe de validación de sistemas](so101-validacion-sistemas-v2.md).

Fecha: 19 de octubre de 2026. Alcance: revisión del código, del flujo canónico
`iterative-debugging` y de los cuatro episodios ya registrados en
[`so101-autonomous-harvest-v2`](../outputs/local/so101-autonomous-harvest-v2/resumen.md).
No se ejecutaron nuevos episodios para esta auditoría.

## Conclusión

El ciclo Codex → programa → simulación → diagnóstico → corrección funciona.
Todavía no tenemos una adaptación completa de la campaña ASPIRE ni una cosecha
resuelta. Hemos conservado reglas de antiguos ejercicios que condicionan cómo
debe agarrarse y soltarse la fruta, aunque la nueva tarea pide resolver el objetivo
completo desde observaciones. También faltan información del efector, control
durante el cierre y diagnósticos temporales fiables.

Nuestra responsabilidad es proporcionar un banco coherente, herramientas
generales, evidencia útil y el protocolo de aprendizaje/evaluación. El agente
debe proponer la estrategia de cosecha y sus correcciones. Continuar escribiendo
nosotros la alineación, el giro o el transporte desviaría el objetivo acordado.

El [plan actualizado](plan-so101-fresas.md) convierte estos hallazgos en tareas.
El [plan anterior](historial-plan-so101-fresas-2026-10-19.md) se conserva como
histórico: mezclaba logros del experimento de desprendimiento con pendientes de
la nueva cosecha completa y todavía proponía alinear/cerrar como siguiente tarea.

## Evidencia de los cuatro intentos

Todos corresponden al mismo caso fijo de desarrollo 0. Los cuatro terminaron
con `program_ok=true` y `task_success=false`: los programas capturaron su propia
excepción final de ausencia de contacto bilateral. Las llamadas al adaptador no
devolvieron abortos. Terminar el programa no acredita éxito físico.

| Candidato | Cambio propuesto por Codex | Evidencia física registrada |
|---|---|---|
| `c-a1f6e8a7eefdc2ba` | Aproximación visual y cierre | Pico dedo fijo 8,76 N; dedo móvil 0 N. Sin agarre acreditado. |
| `c-1f146d507729144c` | Cierre gradual, consulta de fuerzas entre comandos | Picos 50,45 y 61,09 N; penetración 2,43 mm. Sin agarre acreditado. |
| `c-774a304c99ac471a` | Mayor inserción a partir del radio visual | Desprendimiento a 2,930 s sin agarre cualificado y caída. Episodio de 29,05 s. |
| `c-c2f6b81ba87c2f17` | Cambio de altura a partir del radio visual | Desprendimiento a 2,738 s sin agarre cualificado, colisión y caída. Episodio de 28,90 s. |

Son fuerzas y contactos de la simulación, con parámetros todavía sin calibrar.
Los cuatro informes tienen `approach_ready_step=null` y `early_closure=true`.
El candidato 1 se seleccionó por la regla de desempate prefijada; no resolvió la
tarea. Hay contactos unilaterales, excesos de fuerza y caídas reales en el banco:
corregir el evaluador no convierte estos episodios en cosechas exitosas.

## Hallazgos confirmados

### 1. El evaluador exige una receta heredada que el contrato no describe

[`grasp_contact.py`](../src/cap_harness/so101/grasp_contact.py), líneas 200–224 y
258–271, invalida permanentemente el agarre si se cierra antes de una condición
`ready_step`. Esta exige situar el centro nativo de la fruta a menos de 8 mm de
un desplazamiento fijo de 21 mm respecto al TCP, con apertura superior a 0,97,
baja velocidad y varios ticks de asentamiento. La nueva tarea hereda esa regla,
pero [`harvest.py`](../src/cap_harness/so101/harvest.py), líneas 29–43, retira parte
de esa información del contrato público.

Un agarre físicamente válido puede quedar rechazado por no seguir aquella
preparación. Todos los intentos infringieron la regla; además fallaron en
contacto/retención. La corrección consiste en evaluar relaciones físicas y
restricciones declaradas, con una nueva versión del protocolo. Entregar al
agente el desplazamiento secreto perpetuaría el problema.

Existe una segunda condición heredada todavía no alcanzada: para abrir sobre
el recipiente, [`transport.py`](../src/cap_harness/so101/transport.py), líneas
112–116 y 181–190, exige una región muy estrecha alrededor del centro y altura
fija de liberación (0,13 m ±8 mm). El contrato de cosecha oculta esos números.
La contención, soporte y liberación segura deben poder cumplirse mediante
distintas poses válidas. Esta condición no causó los cuatro fallos actuales,
porque ninguno llegó al transporte.

### 2. El contrato de la pinza no basta para razonar sobre el agarre

El TCP `so101_gripperframe` está junto al extremo del dedo fijo; no representa
el centro de una pinza simétrica. Esto está explicado en la
[guía antigua](so101-fresa-agarre.md), pero el contrato autónomo de
[`debug_tools.py`](../src/cap_harness/so101/debug_tools.py), alrededor de la línea
264, solo indica la dirección del eje X del TCP. Los programas llevan ese marco
al centro estimado de la fruta y ensayan desplazamientos basados en su radio.

Falta una descripción general y comprobable de ejes, superficies de contacto,
apertura métrica y región de agarre dependiente de la apertura. Es una carencia
del adaptador; no demuestra por sí sola la causa de cada contacto unilateral.

### 3. El control de fuerza llega después de la acción

[`adapter.py`](../src/cap_harness/robosuite/adapter.py), líneas 695–725, ejecuta
30 ticks por `set_gripper`: 1,5 s a 20 Hz. La lectura pública posterior informa
del contacto instantáneo; el evaluador conserva picos en subpasos físicos.
En el segundo candidato, consultar fuerzas entre cierres no evitó los picos de
50,45/61,09 N y todas las llamadas devolvieron `ok=true`.

Se necesita una primitiva general que limite velocidad/duración y permita
parada por contacto/fuerza dentro del controlador, con máximos y causa de parada
en el resultado. Los sensores usados ahora son virtuales; la pinza estándar del
SO-101 no ofrece automáticamente estas mediciones.

También falta definir qué viola definitivamente el episodio y qué permite
recuperación. Actualmente el horizonte termina la ejecución, mientras otras
infracciones quedan acumuladas; los candidatos 3 y 4 continuaron cerrando mucho
después del desprendimiento. No se debe llamar a esto «ignorar un aborto API»:
ese aborto no se emitió.

### 4. El diagnóstico pierde cuándo y durante qué comando ocurrió el fallo

[`harvest_feedback.py`](../src/cap_harness/so101/harvest_feedback.py), líneas
15–23, asigna el tiempo y fase finales a infracciones acumuladas. Los eventos de
las líneas 59–70 recogen hitos, pero omiten fallos temporales que el monitor de
[`diagnostics.py`](../src/cap_harness/so101/diagnostics.py), líneas 183–205, sí
registra. Los candidatos 1 y 2 tienen `events=[]`, incluso con los picos citados.

ASPIRE necesita primer instante, comando activo, pares de contacto, mediciones
y referencias de imágenes antes/después. Se pueden conservar estos diagnósticos
sin revelar poses nativas, semillas o parámetros biológicos ocultos.

### 5. Solo está conectada una parte de la campaña ASPIRE

El [perfil SO-101](../.claude/skills/iterative-debugging/so101/SKILL.md) declara
correctamente que entrega un resultado de desarrollo, sin Stage 1 canónico
completo. El [manifiesto de cosecha](../configs/so101/fruitgym-harvest-agent-v1.json)
solo define dev0 y ninguna partición reservada. Los casos antiguos de
desprendimiento no validan esta nueva escena.

En [`handoff.py`](../src/cap_harness/so101/handoff.py), líneas 29–40, el informe de
habilidades se construye con listas siempre vacías. No existe todavía un camino
para recibir propuestas del agente, verificarlas independientemente y promover
una biblioteca reutilizable. Guardar código y episodios no equivale a tener esa
memoria de habilidades funcionando.

La procedencia permanece `PENDING` por construcción; los hashes y la auditoría
de herramientas no sustituyen su revisión. El
[runner canónico](../.claude/skills/iterative-debugging/scripts/run_validation.py)
necesita integrar registro, horizonte y configuración GLFW de SO-101. Actualmente
aplica EGL a este benchmark y no admite SO-101 en su ruta de múltiples workers.

Además, la auditoría de interacción comprueba presencia global de herramientas,
sin exigir por código la relación diagnóstico → siguiente corrección. La traza
v2 sí contiene revisiones: es una carencia de verificación, no una omisión
demostrada de aquel agente.

## Límites y dudas que siguen abiertos

- **Factibilidad:** falta una comprobación positiva de contacto bilateral con el
  mesh FruitGym y estas primitivas. Los tests actuales cubren importación,
  permanencia, desprendimiento por carga externa y fallos negativos. Cuatro
  intentos fallidos no demuestran imposibilidad.
- **Movimiento:** la IK y la interpolación declaran `collision_aware=False`.
  Llegar a una pose no garantiza una trayectoria libre. Los cinco ejes limitan
  orientaciones posibles, pero no hubo `IK_FAILED` en los cuatro episodios.
- **Percepción:** se usa color RGB-D y ajuste geométrico aproximado, no SAM3.
  Hay que medir error y oclusión respecto a la holgura de agarre. No hay evidencia
  de que cambiar únicamente el segmentador resuelva estos fallos.
- **Física:** los límites de fuerza/penetración son reglas sintéticas; fricción,
  unión liberable y hojas/tallos rígidos no están calibrados para una planta
  real. Se puede aprender el flujo ASPIRE con este perfil declarado. Transferir
  resultados a hardware requerirá medición y calibración posteriores.
- **Selección:** cuatro candidatos y desempate por orden aportan poca evidencia
  sobre una tarea larga. Hay que fijar presupuesto por modo de fallo y criterios
  antes de ejecutar. No consta que el selector descartase una solución exitosa.

## Qué conservar

Conservar las APIs compartidas, generación sin política inicial, restricciones
sobre acceso privilegiado, caché por hash, identidades de programa/protocolo,
registros y reanudación sin gasto duplicado. Mantener `plan_open_approach` fuera
del trabajador autónomo y distinguir ejecución correcta de éxito físico.

Los tests previos de integración y las auditorías de hashes tienen valor para
sus contratos concretos; no demuestran que el criterio de cosecha sea adecuado,
que exista agarre viable con el nuevo mesh ni que se haya aprendido la tarea.

Orden de actuación: corregir contrato y evidencia, completar herramientas y
validar el banco, integrar campaña y habilidades, después ejecutar desarrollo y
evaluación con ASPIRE. Los resultados históricos conservan su versión original.
