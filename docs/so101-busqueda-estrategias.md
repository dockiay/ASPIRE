# Búsqueda de estrategias para el SO-101

Fecha: 20 de octubre de 2026.

Actualización de implementación: el protocolo diverso **v2** permite diagnóstico
de requisitos y refinamiento antes de completar cuatro familias; el presupuesto
es un máximo. La descripción 4+2 y su campaña de este documento corresponden al
v1 histórico. Véase [corrección de implementación](so101-correccion-implementacion.md).

La recomendación es una búsqueda evolutiva con un archivo de alternativas,
inspirada en MAP-Elites y en Evolution through Large Models (ELM). El controlador
propone programas; el simulador aporta resultados; se conservan ramas diferentes
y se decide cuáles modificar usando evidencia. Es una adaptación propuesta para
este banco, no una garantía de resolver la cosecha.

## Fundamento y alternativas

| Método | Aportación publicada | Aplicación a nuestro caso |
|---|---|---|
| [MAP-Elites, Mouret y Clune](https://arxiv.org/abs/1504.04909) | Archivo de soluciones con calidad y descriptores de comportamiento diferentes | Conservar alternativas; medir diversidad por lo que hace la fruta y el robot, no por nombres de estrategias |
| [ELM, Lehman et al.](https://arxiv.org/abs/2206.08896) | LLM como operador de modificación de programas, combinado con MAP-Elites | El LLM puede cambiar estructura y mecanismos del programa, además de sus constantes |
| [BOP-Elites, Kent et al.](https://arxiv.org/abs/2307.09326) | Modelos bayesianos de calidad y comportamiento para evaluaciones costosas | Interesante cuando fijemos una representación numérica y descriptores fiables; no equivale a modelar directamente cualquier programa Python |
| [TuRBO, Eriksson et al.](https://proceedings.neurips.cc/paper_files/paper/2019/hash/6c990b7aca7bc7058f5e98ea909e924b-Abstract.html) | Optimización bayesiana local con reparto de muestras entre regiones | Posible ajuste numérico de una familia de políticas; no implementado en esta entrega |

El [proyecto ASPIRE](https://research.nvidia.com/labs/gear/aspire/) ya plantea
búsqueda evolutiva sobre secuencias y programas. Su flujo local `evosearch` usa
K=8 y otras particiones. No hay que trasladar sus semillas, un programa base
anterior ni sus cifras de éxito al protocolo SO-101 v2.

## Diseño recomendado

1. Explorar mecanismos diferentes con un presupuesto explícito. El agente
   elige cambios sustanciales de geometría de agarre, maniobra y coordinación.
2. Conservar cada programa, su ascendencia, hipótesis, resultados en todos los
   casos asignados y vídeos. Un intento no desaparece porque el siguiente falle.
3. Separar calidad y diversidad. Éxito físico y ejecución correcta son las
   primeras comparaciones. Giro/desplazamiento real, acoplamiento, pérdida de
   contacto y motivo de parada describen comportamiento; no certifican cosecha.
4. Refinar ramas con progreso medido y mantener alternativas. Si una maniobra
   no llega a ejecutarse, corregir su limitación o cambiar de mecanismo; variar
   solo el ángulo solicitado no aporta evidencia sobre ángulos de la fruta.
5. Añadir más adelante un archivo MAP-Elites de comportamiento observado y
   selección automática de progenitores. Los descriptores deben manejar visión
   desconocida, incertidumbre, escenas diferentes y medidas no comparables.
6. Ajustar parámetros numéricos con búsqueda local/bayesiana solo cuando el
   programa y sus medidas permitan hacerlo. Validar el seleccionado por separado.

No se debe premiar girar una pinza vacía, acumular movimiento con deslizamiento
ni aprovechar un diagnóstico desconocido. Un programa fallido puede aportar
conocimiento experimental, pero no se convierte por ello en una skill verificada.

## Primera implementación comprobada

`cap_harness.so101.skill_learning --search-mode diverse` conserva el límite de
seis herramientas para Codex y API. Las primeras cuatro propuestas son familias
distintas; el resto son refinamientos con un progenitor inspeccionado. La
hipótesis es JSON dentro del argumento existente `hypothesis`, con `phase`,
`family`, `dimensions`, `parent_candidate_id`, `rationale`, `expected_evidence`.

El servidor exige cambios declarados en al menos dos de tres dimensiones,
estructura distinta tras normalizar constantes/nombres, resultados inspeccionados
y un fotograma de cada candidato anterior registrado. Conserva registros de
estrategia inmutables y los vuelve a comprobar al cerrar. Rechazar una hipótesis
consume una llamada; un programa aceptado consume su presupuesto habitual.

La selección maximiza el mismo éxito físico y después `program_ok`. Entre
empates deja elegir al controlador con justificación basada en resultados;
el tamaño del AST deja de decidir. La promoción conserva el contrato físico y
el verificador independiente. La revisión independiente evalúa además si las
fuentes son materialmente diferentes y qué diversidad llegó a ejecutarse.

Esto es un primer modo de exploración/refinamiento auditado, **no una
implementación completa de MAP-Elites, BOP-Elites o TuRBO**. El filtro de código
no demuestra diversidad física; una rama puede detenerse antes de su maniobra.
La selección entre empates sigue siendo juicio del controlador, no una función
de adquisición bayesiana ni una clasificación automática de cercanía al éxito.

Las pruebas de búsqueda, herramientas, contexto, contratos parciales, procedencia
y coordinador suman 81 casos aprobados con artefactos sintéticos. No son nuevos
episodios físicos ni evidencia de cosecha.

## Cómo comprobar si el sistema de búsqueda mejora

Comparar búsqueda secuencial y búsqueda diversa con iguales límites de programas,
casos, sensores y física. Medir éxito físico, familias cuya maniobra distintiva
llegó a ejecutarse, progreso de contacto/acoplamiento respaldado por medidas y
coste de evaluación. Separar fallos de percepción, cierre, alcance y maniobra.
Más nombres de estrategias o más giro solicitado no son mejoras. La división
inicial de cuatro exploraciones y dos refinamientos es una decisión de presupuesto,
no una proporción óptima demostrada por los artículos.

Si casi todas las alternativas se detienen antes de su maniobra, la siguiente
mejora del buscador debe separar factibilidad y calidad: mantener las primitivas
verificadas que correspondan, comprobar la nueva geometría con APIs públicas y
registrar qué impide alcanzar cada rama. El agente sigue siendo autor del programa.
Un archivo no debe clasificar como «mejor giro» una rama sin medición válida ni
mezclar observaciones desconocidas con desplazamiento cero. Los casos reservados
se usan después de congelar la selección, nunca para elegir mutaciones.

## Ensayo de la primera adaptación

La campaña `so101-partial-diverse-search-20261020` terminó con cuatro familias
y dos refinamientos, doce episodios en desarrollo 0/1001. Procedencia PASS;
el revisor independiente confirmó fuentes materialmente diferentes. También
advirtió que la diversidad planificada superó la ejecutada:

| Propuesta | Resultado en las dos escenas |
|---|---|
| Giro axial con renovación de cierre | Detección ambigua; no llegó a moverse |
| Pinza en plano vertical y tracción hacia abajo | Colisión durante cierre; no llegó a tirar |
| Agarre inferior y flexión con centro fijo | Agarra, pero giro TCP de 0,146°/0,158° y pérdida de contacto |
| Aproximación oblicua y tracción diagonal con nuevos cierres | Colisión durante cierre; no llegó a tirar |
| Refinamiento con pivote medido, IK de punto/dirección y precarga | Giro TCP de 4,286°/0,919°; contacto continuo máximo 3,412/0,904 s; sin liberar |
| Refinamiento del giro alrededor del centro medido | Movimiento relativo en visión y colisión posterior al intentar sostener |

El quinto programa queda seleccionado: mantiene `program_ok=2/2`, como su
progenitor, y ofrece más contacto y movimiento medidos. Ya no lo descarta el
desempate por tamaño del AST. Es una preferencia experimental del agente;
la visión del quinto sigue siendo insuficiente para acreditar giro acoplado.
Liberación y retención libre: 0/12 episodios. No se propuso ni promovió skill.
Solo cuatro episodios terminaron sin error de programa; las colisiones y los
fallos se conservan. No se evaluaron casos reservados ni hardware.

La reanudación exacta no alteró 58 archivos de recibos ni la biblioteca.
La comparación y los vídeos quedan en
[`strategy-search-review-v2.json`](../outputs/local/so101-partial-diverse-search-20261020/strategy-search-review-v2.json)
y la [galería local](../outputs/local/galeria-pruebas/index.html).
Los registros no demuestran todavía mayor eficiencia frente a otro buscador.
El siguiente desarrollo recomendado es T28, empezando por la factibilidad de
agarre/maniobra para que más familias puedan evaluarse físicamente.

## Campaña con las herramientas corregidas (T31)

`so101-retain-corrected-codex-sam3-20261020` se ejecutó después de la reparación
de control, calibración, propuestas de agarre y planificación. Se usaron Codex,
SAM3 real con sus pesos fijados, imágenes 1280×960 y la biblioteca congelada de
dos habilidades. El objetivo registrado fue `retain_ripe_fruit_v1`: agarre
acreditado, liberación mecánica y dos segundos de retención libre. Se mantuvieron
los requisitos físicos y las guardas existentes.

El aprendiz generó **ocho programas y ejecutó 16 episodios** en desarrollo
0/1001, con 33 llamadas a las herramientas controladas. Inspeccionó los resultados
de todos los candidatos y los fotogramas relevantes. Se alcanzó el presupuesto;
ningún episodio acreditó agarre, desprendimiento o retención, y ninguno terminó
con `program_ok=true`.

| Programa | Cambio principal | Resultado en desarrollo |
|---|---|---|
| 1 | Agarre radial histórico y tracción recta prevista | Detección SAM3 ambigua; cero pasos |
| 2 | Consulta semántica específica para fresa roja madura | Colisión durante el cierre en ambas escenas |
| 3 | Inspección de propuestas geométricas del robot | Diagnóstico deliberado sin movimiento; no ensayó el agarre |
| 4 | Aproximación basada en propuesta geométrica | Colisión en una escena y rechazo de planificación en la otra |
| 5 | Centrado propio con IK de punto/dirección y preparación remota de pinza | Rechazó una terminación normal de la preparación por interpretar mal `stop_reason` |
| 6 | Corrigió esa interpretación | Otro fallo de proyección/agarre y una colisión; había tratado `check_joint_path.ok` como si significara `path_clear` |
| 7 | Agarre inferior y flexión con retirada previstas; comprobación correcta de `path_clear` | La aproximación quedó rechazada antes del agarre |
| 8 | Planificación con obstáculos para la aproximación final | Objetivo obstruido en la pinza en ambas escenas; preparación remota sin colisión, 89/91 pasos |

El octavo programa, `c-f098d7406ea025de`, fue seleccionado entre los empates como
candidato experimental: corrige las dos interpretaciones de resultados y evita
la colisión registrada en variantes anteriores, pero sigue sin completar el
agarre. Los ocho códigos, sus fallos y sus vídeos se conservan. La selección no
constituye una solución ni una habilidad aprendida.

La revisión independiente de procedencia dio **PASS**: los objetivos proceden de
SAM3/RGB-D y estado público, sin coordenadas copiadas de la escena, acceso privado
ni cambios de física. Encontró diferencias sustanciales de código, pero no cuatro
mecanismos de separación realmente probados. No se ejecutó ninguna llamada a
`compare_visual_motion`: las ramas estaban escritas y sus requisitos no se
alcanzaron (`branches_unexercised`). No se acredita corrección visual en marcha.

No se propuso ni promovió ninguna skill; la biblioteca conserva el hash
`eb9f03a79dfe4c279e285602fe7d287f37b2c26e3505dff3a26d25a80776754a`.
Al no haber propuestas, no se lanzó un verificador de reproducción. Esta campaña
parcial no ejecutó validación ni evaluación reservadas y no demuestra
generalización. El bloqueo medido sigue en la geometría y ejecución del agarre;
las hipótesis de desprendimiento quedaron sin evaluar.

Se auditaron los manifiestos de los 16 episodios y se conservaron **32 vídeos**.
Los dos vídeos del candidato seleccionado se comprobaron mediante decodificación
de su primer fotograma: H.264, 1280×960 y 20 fps.

- [Resumen con resultados y hashes](../outputs/local/so101-retain-corrected-codex-sam3-20261020/campaign-review.json)
- [Galería de los 32 vídeos](../outputs/local/so101-retain-corrected-codex-sam3-20261020/videos.html)
- [Revisión independiente](../outputs/local/so101-retain-corrected-codex-sam3-20261020/learner/independent-provenance/audit.json)

## Campaña con referencias publicadas (T32)

Se conectaron cinco documentos originales de ASPIRE mediante un bloque congelado
`skill_references`, separado de las skills locales verificadas. El manifiesto
`configs/so101/published-skill-references.json` fija contenido, revisión de GitHub,
hashes y notas de adaptación. La conexión sirve para Codex y el controlador API;
esta campaña utilizó Codex y SAM3 real, sin fallback por color.

Bucle cerrado, también a petición del usuario: **12 programas, 24 episodios de
desarrollo 0/1001, 54 llamadas y 48 vídeos**. **Cero agarres acreditados, cero
liberaciones y cero retenciones**. No se propuso ni promovió ninguna skill.
No se ejecutaron casos reservados. Auditoría independiente de procedencia: PASS.

La revisión confirmó reutilización de `upstream-localize` para la descripción
específica de la fresa y el tratamiento de superficies visibles, y de
`upstream-grasp` para aproximaciones por etapas y comprobación de errores.
Las ideas de flexión/tracción de `upstream-manipulation` quedaron en ramas no
alcanzadas. El agente descartó aplicar las convenciones de `upstream-mobile-grasp`
y las recetas de `upstream-transport` a esta ejecución.

Se escribieron cuatro familias distintas, pero ninguna pudo evaluar físicamente
su maniobra de desprendimiento. El candidato seleccionado
`c-127800e14c45511d` ejecutó 198/196 pasos sin contacto prohibido: corrigió el
tiempo mínimo de cierre para alcanzar las aperturas solicitadas y se detuvo
al rechazarse el siguiente barrido de cierre. Las fuerzas de ambas puntas fueron
cero. Las comparaciones visuales posteriores al agarre nunca se ejecutaron.
Esto no prueba que todos los agarres sean imposibles: sigue sin resolverse la
aproximación y el cierre factibles con contacto exclusivamente en las almohadillas.

La integración pasó 63 pruebas específicas. La suite amplia obtuvo 454 aprobadas
y tres fallos en fixtures históricos de color que no seleccionaban su backend;
se corrigió sólo el fixture con `monkeypatch` y sus nueve pruebas pasaron.
Se conservan ambos informes, sin cambiar el runtime de SAM3 durante la campaña.

- [Resultados auditados](../outputs/local/so101-published-skills-codex-sam3-20261020/campaign-review.json)
- [Aplicación de referencias y procedencia](../outputs/local/so101-published-skills-codex-sam3-20261020/learner/independent-provenance/audit.json)
- [Vídeos de todos los intentos](../outputs/local/so101-published-skills-codex-sam3-20261020/videos.html)
- [Validación de la conexión](../outputs/local/so101-published-skills-codex-sam3-20261020/connection-validation.json)
