# Diagnóstico de intentos con una fresa

Los perfiles `so101_strawberry_detachment` y
`so101_strawberry_detachment_cases` añaden un informe estructurado del estado de
la tarea. El registro permite revisar qué condición falta, en qué fase se observó
una incidencia y qué mediciones la respaldan. El monitor sólo observa: no mueve
el robot, no libera uniones y no modifica el evaluador ni sus tolerancias.

## Contrato de éxito conservado

Se debe acreditar el agarre, liberar la unión física y conservar el fruto libre
durante **2 s continuos al finalizar**, con contacto bilateral válido, sin apoyos
externos, colisiones ni violaciones registradas. El deslizamiento relativo no
puede exceder 8 mm. Se mantienen los límites didácticos de 12 N por dedo y
1,5 mm de penetración, que no predicen daño en fruta real.

El contacto bilateral mantiene los mismos predicados del evaluador existente:
al menos 0,1 N por dedo, normales con producto escalar no mayor que −0,5,
contactos en lados opuestos respecto al centro y separación mínima de 20 mm.
El agarre inicial exige 0,5 s de permanencia. La fuerza necesaria para separar
es una propiedad del caso, no un criterio que el diagnóstico pueda rebajar.

Un intervalo exitoso pasado no basta si el estado final dejó de cumplir la tarea.
Una interrupción del contacto reinicia el intervalo válido; si después se recupera
y cumple los 2 s, el historial de esa interrupción no añade una prohibición nueva.

## Archivos de cada episodio

- `evaluation/so101-task.json`: evidencia física existente y campo `diagnostics`.
- `evaluation/so101-diagnostics.json`: copia independiente del informe para leerlo.
- `evaluation/so101-case-protocol.json`: manifiesto del caso, cuando corresponde.
- `outcome.json`: estado de ejecución, errores del programa y resultado de tarea.

Los archivos de evaluación se escriben al terminar y forman parte del inventario
del episodio. Los diagnósticos no se registran como herramientas ni se añaden a
las observaciones o metadatos públicos del programa. La API pública de `step`
conserva la ocultación de la recompensa nativa y los datos privados. Esta separación
de interfaces no es un aislamiento de seguridad del proceso de Python.

## Cómo interpretar el informe

`schema_version` identifica `so101-strawberry-diagnostics-v1`. `task_success`
coincide con el evaluador existente; `status` describe la evidencia disponible:

| Estado | Significado |
|---|---|
| `completed` | El estado final satisface la tarea |
| `incomplete` | Falta un predicado al finalizar, sin una violación física permanente observada |
| `failed` | Hay una violación física registrada que bloquea el éxito del episodio |

`incomplete` no significa que el proceso siga ejecutándose. Un programa puede
terminar sin errores y dejar una tarea incompleta. Los errores del código o del
proveedor se leen en `outcome.json`, por separado del diagnóstico físico.
Si no existe informe físico, el resumen indica `unavailable` y conserva el error
de ejecución; no inventa un fallo de agarre o una caída.

`primary_finding` es el bloqueo observado de mayor prioridad; no demuestra una
causa raíz. `findings` conserva todos los tipos de violación observados. La
prioridad es: colisión, fuerza, penetración, física no permitida, caída, apoyo
indebido, deslizamiento, cierre prematuro y liberación sin agarre acreditado.

| Código | Evidencia que lo respalda |
|---|---|
| `robot_collision` | Pareja de contacto prohibida, instante y estado del fruto |
| `finger_force_limit_exceeded` | Fuerza medida y máximo acumulado por dedo |
| `penetration_limit_exceeded` | Penetración máxima observada |
| `invalid_physics` | Violación registrada: reactivación de unión, fuerzas externas o gravedad modificada |
| `fruit_dropped` | Descenso de al menos 30 mm respecto a la liberación, sin contacto de los dedos, con velocidad descendente mayor de 0,05 m/s o contacto actual con la mesa |
| `unexpected_support` | Contacto del fruto libre con un apoyo no permitido |
| `relative_slip_exceeded` | Desplazamiento respecto a la referencia de liberación mayor de 8 mm |
| `early_closure` | Cierre antes de acreditar aproximación con pinza abierta |
| `released_without_qualified_grasp` | Liberación sin agarre acreditado previamente |
| `grasp_not_qualified` | No se acreditó el agarre antes de finalizar |
| `junction_not_released` | El fruto continúa unido al finalizar |
| `unstable_bilateral_contact` | El contacto bilateral final no satisface el predicado existente |
| `retention_duration_short` | Contacto final válido pero intervalo continuo menor de 2 s |
| `unresolved_task_predicate` | Respaldo conservador si queda un predicado sin explicar |

Los umbrales de la etiqueta de caída son una regla de descripción geométrica,
no una medición de tejido ni una modificación del criterio de éxito. Superar
8 mm de deslizamiento por sí solo no acredita una caída: ambos hechos se
registran por separado cuando existe evidencia suficiente.
La etiqueta de caída sólo se considera un bloqueo permanente cuando el evaluador
existente también ha registrado deslizamiento o un apoyo indebido. El historial
del monitor no introduce criterios adicionales.

## Instantes y evidencia

Los eventos se observan después de cada paso físico de 2 ms y también al completar
el paso de control. Se registran transiciones y primeras incidencias, no una copia
de todos los contactos en cada paso. El historial incluye aproximación, agarre,
liberación, pérdida/recuperación de contacto e intervalos de retención.

Cada evento tiene identificador, tiempo simulado, fase, mediciones y una referencia
al vídeo. Las fases son `approach_and_grasp`, `detachment` y `free_retention`.
Las referencias indican las cámaras y los fotogramas que rodean el instante.
Las cámaras se registran a 20 Hz: una incidencia de 2 ms puede no ser visible en
ningún fotograma. Las mediciones numéricas conservan ese hecho; una oclusión no
se interpreta como ausencia de contacto. Las rutas de vídeo se resuelven en los
episodios grabados, no en pruebas unitarias sin grabación.

Las violaciones permanentes conservan el primer instante aunque se restaure
después la postura. Las condiciones incompletas se etiquetan como predicados
no cumplidos **al finalizar**, sin inventar un instante previo de fallo. El estado
final incluye fuerzas y geometría de contactos, tiempos, posiciones y velocidad.

## Revisar un intento

```bash
python scripts/summarize_so101_strawberry_run.py RUTA_AL_EPISODIO \
  --output outputs/local/diagnostico-resumen.json
python -m pytest -q tests/test_so101_diagnostics.py
```

El resumen combina ejecución y diagnóstico físico. Se escribe fuera del episodio
finalizado para no modificar sus artefactos y hashes. Las pruebas comprueban
tareas incompletas, recuperación de contacto, caída posterior a un éxito,
colisión o apoyo de un único paso, sobrecierre físico y separación entre la API
pública y el evaluador. Los casos reservados no se necesitan para estas pruebas.

## Resultados comprobados

El 19 de octubre de 2026 se aprobaron 11 pruebas nuevas, incluida la clasificación
de errores de ejecución sin evidencia física. La selección conjunta inicial
aprobó 68 pruebas; tras añadir las tres últimas se repitieron las 18 pruebas de
diagnóstico y grabación y después las 11 del diagnóstico con el ajuste final.
Ruff sin incidencias.

Se grabaron y auditaron dos ejemplos, ambos con `program_ok=true` y
`task_success=false`, distinguiendo tarea incompleta de violación observada:

| Ejemplo | Diagnóstico | Evidencia |
|---|---|---|
| Caso de desarrollo 109 | `incomplete`, `junction_not_released` | Fruto unido al final, carga máxima 4,454 N frente a umbral del caso de 5,10 N; 29,55 s simulados |
| Sobrecierre deliberado en la lección nominal | `failed`, `finger_force_limit_exceeded` | Primer exceso a los 6,514 s, con evidencia adicional de penetración máxima de 2,372 mm |

La sonda de sobrecierre es una prueba de fallo del simulador, no una estrategia
de cosecha. También se verificó en pruebas una ejecución correcta, la recuperación
de contacto y la pérdida posterior del fruto. No se probaron casos reservados.

Las copias Windows están en `outputs/local/so101-diagnostics/`:
`diagnostic-verification.json` recoge la auditoría; los archivos `*-summary.json`
combinan diagnóstico y ejecución. Los episodios completos incluyen dos cámaras,
592 fotogramas por cámara para el caso 109 y 137 para el sobrecierre. Los hashes
de los informes coinciden con los inventarios de los episodios, y los instantes
referenciados quedan dentro de los vídeos grabados.
