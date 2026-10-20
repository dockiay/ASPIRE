# Plan vigente: sistemas ASPIRE con SO-101, fresas y SAM3

Actualizado: 20 de octubre de 2026.

El objetivo de esta entrega es adaptar **el ciclo, las herramientas, la percepción,
la evaluación y la biblioteca de ASPIRE** a nuestro SO-101 y al benchmark de fresas.
Codex o una API deben poder proponer programas, ejecutarlos, observar fallos y
corregirlos bajo el mismo contrato. **Completar correctamente la cosecha no es
un requisito de integración.** Un episodio fallido es un resultado válido.

El agente decide la estrategia de cosecha, transporte y depósito. La adaptación
proporciona sensores públicos, acciones generales y criterios de evaluación;
no entrega una secuencia manual de movimientos como política inicial.

## Estado de las tareas

| ID | Entrega | Estado y evidencia |
|---|---|---|
| T01 | Contrato y evaluador versionados | Implementados en v2: se puntúa el resultado físico sin imponer las poses del tutorial |
| T02 | Diagnóstico temporal y estados de ejecución | Implementados; se distinguen errores del programa, acciones detenidas y fracaso físico; informes extensos conservan el error |
| T03 | Geometría general de la pinza | Publicada y comprobada contra el modelo del robot |
| T04 | Cierre supervisado | Implementado; verifica contactos y fuerza en subpasos, comunica máximos y motivo de parada |
| T05 | Comprobación de banco y primitivas | Tres casos de desarrollo sin contactos iniciales prohibidos; fixtures positivos/negativos verificados. No demuestra que la tarea completa sea resoluble |
| T06 | Desarrollo, validación y evaluación separados | Tres casos de desarrollo, dos de validación y tres finales; variaciones sintéticas registradas |
| T07 | Coordinador, controladores y procedencia | Codex probado con una campaña real; transporte API probado mediante servidor HTTP de prueba; revisión independiente PASS |
| T08 | Biblioteca y verificador | Implementados y comprobados con una primera habilidad parcial generada por Codex, aplicada por un verificador independiente y promovida con evidencia nativa |
| T09 | Ciclo autónomo de desarrollo | Completado: ocho programas generados por el agente y 24 episodios de desarrollo |
| T10 | Evaluación congelada y reanudación | Completadas: dos episodios de validación y tres finales; reanudar no repitió episodios ni llamadas al modelo |
| T11 | Transferencia al robot real | Trabajo posterior; requiere hardware, calibración y sensores reales |
| T12 | Percepción con SAM3 | Comprobada con los pesos reales en la RTX 4090: seis consultas, detecciones en cinco, 15 proyecciones 3D y cero pasos de movimiento. Se conservan la ausencia de detección y las estimaciones contaminadas; no equivale a exactitud validada de todas las instancias |
| T13 | Evaluación de habilidades parciales | Siete contratos registrados; `skill_success` separado de `task_success`, verificación individual y revisión de aplicación. Primera skill de localización aprobada en 2/2 escenas, con cosecha 0/2 |
| T14 | Aprendizaje de agarre usando localización | Completado con Codex y SAM3: segundo programa del aprendiz 2/2; verificador independiente 2/2; habilidad promovida. La fruta permanece unida a la planta |
| T15 | Diagnóstico y límites del evaluador parcial | Corregidos después de congelar T14: tolerancia numérica del testigo, rechazo de apoyos no permitidos y métricas de contacto posteriores al episodio |
| T16 | Primer aprendizaje de desprendimiento y retención | Ejecutados ocho programas en 16 episodios: ninguna liberación mecánica; procedencia PASS, ninguna skill propuesta ni promovida. Evidencia conservada |
| T17 | Replanteamiento con observaciones públicas congeladas | Cuatro programas y ocho episodios terminados: ninguna liberación ni skill nueva; procedencia PASS y reanudación sin episodios adicionales. Función de contexto comprobada con 72 pruebas |
| T18 | IK genérica adecuada a cinco ejes | Herramienta pública de punto y dirección implementada; 56 pruebas aprobadas. Cuatro programas y ocho episodios: sin desprendimiento; el último termina limpio en ambas escenas, pero pierde contacto. Procedencia PASS y reanudación sin episodios adicionales |
| T19 | Supervisión durante el movimiento del brazo | Implementada y probada con Codex/SAM3: seis programas y 12 episodios, sin liberación. Una variante mantiene contacto continuo 13,67/6,25 s y contacto final en ambas escenas. Procedencia PASS; ninguna skill nueva |
| T20 | Diagnósticos públicos y límites explícitos | Implementados después de cerrar T19: límites visibles antes de ejecutar y resumen automático de paradas, errores y llamadas sin movimiento. 59 pruebas aprobadas; revisión retrospectiva de tres trazas nativas |
| T21 | Comprobar transmisión del movimiento a la fruta | Herramienta RGB-D implementada; 100 pruebas y comprobación con FruitGym/SAM3. Seis programas, 12 episodios y nueve comparaciones; ninguna liberación. Auditoría QUARANTINED conservada por conflicto interpretativo sobre reutilizar la biblioteca. Sin promoción |
| T22 | Usar la comparación visual durante la maniobra | Completada la conexión: dos programas y cuatro episodios. La segunda variante consulta imágenes y se detiene por giro insuficiente en 2/2 escenas, con contacto final bilateral. Procedencia PASS; desprendimiento 0/2 y ninguna skill nueva. Reanudación sin modificar 34 recibos ni biblioteca |
| T23 | Probar giro y tracción tras agarrar | Ejecutados cuatro programas y ocho episodios con SAM3. Seis episodios llegaron a tracción tras el giro; correcciones de momento de retirada, renovación del cierre y dirección. Ocho episodios sin error de programa, cero liberaciones/retenciones. Procedencia PASS; ninguna skill nueva |
| T24 | Conservar acoplamiento durante giro y tracción | Pendiente: diagnosticar pérdida de presión/contacto y movimiento relativo. Comprobar el mando de pinza durante el movimiento; rechazar `contact_lost` aunque `target_reached` sea verdadero. La retención libre de 2 s sigue siendo requisito de promoción |
| T25 | Calcular referencias de recogida humana y aplicarlas a flexión mayor | Completada investigación y ensayo: 3,175 N de media en seis muestras de flexión/tracción; referencias robóticas de 20° y 70° con alcances diferentes. Tres programas y seis episodios: objetivo de 40° sin alcanzar; última variante gira el TCP 3,94°/7,97° y se detiene por movimiento relativo. Procedencia PASS; ninguna liberación ni skill nueva |
| T26 | Medir tracción y par mediante sensores públicos | Pendiente antes de usar N o N·m como consigna de cosecha: las fuerzas normales de los dedos no equivalen a carga del pedúnculo. Requiere instrumentación y calibración públicas, sin consultar la reacción privada de la unión como sensor del controlador |
| T27 | Explorar estrategias amplias antes de ajustes finos | Implementado y ejecutado: 81 pruebas aprobadas; cuatro familias y dos refinamientos, doce episodios. Auditor independiente confirma diferencias sustanciales en fuente, pero tres familias se detienen antes de la maniobra. Ninguna liberación ni skill nueva. Se selecciona el quinto programa por evidencia entre empates físicos, sin preferir menor AST. Reanudar conserva 58 recibos y biblioteca |
| T28 | Archivo de diversidad de comportamiento y elección de ramas | Pendiente: separar factibilidad de calidad, mantener descriptores medidos con incertidumbre y seleccionar progenitores automáticamente. Diseño inspirado en MAP-Elites/ELM documentado; el filtro actual de código no constituye MAP-Elites completo |
| T29 | Corregir la implementación antes de nuevas iteraciones | Implementada y validada con 215 pruebas: control coordinado de pinza/brazo, continuidad entre APIs, barrido de mandíbula, contacto limitado a almohadillas, visión por componente, revisión de decisiones y reparación de requisitos dentro de búsqueda diversa. A/B final: cuatro movimientos, estados iniciales iguales por pareja; el cierre coordinado retrasa la pérdida de contacto pero alcanza el límite de fuerza. No acredita desprendimiento ni control estable de fuerza. Véase `so101-correccion-implementacion.md` |
| T30 | Reparar la paridad de control y conectar proveedores SO-101 | Completada con 423 pruebas: cancelación y cierre pendiente entre APIs, marco de proyección, entradas, velocidades por tiempo, calibración RGB-D, propuestas de agarre y desvíos ante obstáculos. SAM3 real en FruitGym produce un agarre propuesto y un plan de preagarre desde cada cámara; ejecutor estándar verificado con movimiento de control grabado. No acredita cosecha ni promueve skills. [Informe](so101-correccion-implementacion.md) |
| T31 | Nueva campaña de agarre, desprendimiento y retención con herramientas corregidas | Terminada: Codex + SAM3, ocho programas y 16 episodios de desarrollo 0/1001, 33 llamadas y 32 vídeos. Procedencia independiente PASS. Cero agarres acreditados, liberaciones y retenciones; ninguna skill propuesta ni promovida. La selección se detiene ante un objetivo de agarre obstruido en ambas escenas. Las ramas visuales no se ejecutaron. [Resultados](../outputs/local/so101-retain-corrected-codex-sam3-20261020/campaign-review.json) |
| T32 | Conectar referencias publicadas y aprender su adaptación al SO-101 | Conexión implementada: cinco referencias congeladas, separadas de las skills verificadas y accesibles con Codex/API. Bucle cerrado: 12 programas, 24 episodios, cero agarres acreditados, liberaciones o retenciones. No se propone ninguna skill. Localización y estructura de aproximación reutilizadas; cierre válido pendiente. Procedencia y aplicación de referencias auditadas: PASS; 48 vídeos conservados. [Resultados](../outputs/local/so101-published-skills-codex-sam3-20261020/campaign-review.json). |

La implementación corregida en T29 y la integración de T30 quedan comprobadas.
Las campañas anteriores conservan sus imágenes, fuentes y resultados; no se
reinterpretan con la nueva calibración. La próxima campaña podrá
retomar habilidades propuestas y corregidas por el controlador, con atención
al mantenimiento del agarre bajo carga y las decisiones visuales ejecutadas. El
desprendimiento sigue sin aprenderse. Hay mejores herramientas de movimiento
y diagnóstico, pero el contacto prolongado no acredita giro de la fruta ni
liberación. T21 registró correcciones entre intentos, conservadas en cuarentena;
T22 ya usa las imágenes dentro del episodio para detener la maniobra cuando
el giro es insuficiente para concluir. Las ramas de reajuste por deslizamiento
están escritas, pero todavía no se han ejecutado ni validado en esa campaña.
La compatibilidad visual entre dos instantes tampoco certifica agarre continuo
ni desprendimiento. Se conserva el criterio físico de liberación y retención.
En T23 el controlador ya probó giro seguido de tracción. Renovar el cierre
permitió retirar más el TCP, pero la fruta no acompañó ese desplazamiento
suficientemente y permaneció unida a la planta. La siguiente búsqueda debe
comparar mecanismos y agarres distintos, con movimientos de escala significativa
y acoplamiento medido, antes de afinar otra variante casi idéntica. T27 introduce
esa exploración; el [diseño de búsqueda](so101-busqueda-estrategias.md) distingue
lo implementado del archivo y optimizador todavía pendientes.
El robot real y la calibración biológica siguen fuera de esta etapa.

## Resultado registrado

La [campaña real](../outputs/runs/so101-strawberry-v2-20261019/progress.md)
completó **29 episodios**, 35 llamadas de herramientas y revisión independiente
de procedencia PASS. El programa seleccionado obtuvo **0/3 cosechas completas**
en evaluación final y se ejecutó correctamente en los tres episodios.

El estado `done` significa que el protocolo experimental terminó. El campo
`full_harvest_solved=false` conserva el resultado físico. Esta campaña utilizó
la heurística por colores anterior y **no demuestra funcionamiento de SAM3**.
Su fuente exacta se conserva; no se reinterpretan sus resultados con código nuevo.

En aquella campaña no hubo propuestas de habilidades. La prueba posterior de
aprendizaje parcial sí generó y verificó una skill; los resultados se mantienen
separados y los episodios de la campaña anterior no se reclasifican.

## Integración de visión comprobada

1. Login de Hugging Face verificado y checkpoint de 3,45 GB descargado.
2. SAM3 original de ASPIRE iniciado en `http://127.0.0.1:8114`, sobre CUDA.
3. Prueba sin movimiento completada: imágenes públicas → máscaras SAM3 →
   proyección RGB-D → geometría visible → registros y overlays.
4. Los filtros opcionales de proyección declaran una erosión de un píxel y
   rango de observación de 0,1–2 m. Son parámetros de ingeniería explícitos;
   no una calibración física ni una sustitución de la máscara detectada.

El [resultado con SAM3 real](../outputs/local/so101-sam3-live-20261019-r3/verification.json)
conserva seis consultas y 15 instancias proyectadas. La fresa roja se detecta en
ambas cámaras. `container` no devuelve detección en `agentview` y sí en `sideview`.
Algunas estimaciones siguen mezclando fondo/superficies: una fresa verde y una
hoja tienen extensión 3D excesiva. El agente debe gestionar esa incertidumbre;
no se ha exigido recoger la fruta ni alcanzar detección perfecta.

SAM3 es el backend predeterminado del benchmark completo. La heurística por
colores requiere selección explícita para comparar resultados. No hay sustitución
automática cuando falla SAM3. Cada campaña congela proveedor, checkpoint, código,
umbral, fuentes, protocolo y presupuestos antes de llamar al controlador.

Las cámaras y su profundidad siguen siendo simuladas; las superficies rígidas y
la unión liberable no están calibradas para plantas reales. Usar SAM3 real no
convierte la escena en una captura de una cámara física.

## Primera habilidad parcial aprendida y aplicada

La [prueba de aprendizaje](../outputs/local/so101-partial-localization-learning-20261019/result.json)
terminó con `verified`. Codex propuso
[`two-view-ripe-fruit-localization.md`](../configs/so101/skills/two-view-ripe-fruit-localization.md)
y otro proceso lo aplicó desde esa skill, sin recibir el archivo del programa
proponente. Una revisión independiente confirmó procedencia y aplicación.

El contrato `localize_ripe_fruit_v1` exige error de centro ≤20 mm, marco y tiempo
correctos, llamadas de percepción públicas y cero pasos de control. Entre
escenas exige error de desplazamiento ≤10 mm, para rechazar una coordenada fija
que por casualidad caiga dentro de ambas tolerancias absolutas.

En los casos de desarrollo 0 y 1001, aprendiz y verificador obtuvieron errores
de **4,91 y 5,12 mm**, con error de desplazamiento **0,29 mm**. Ambos registraron
`skill_success=2/2` y `task_success=0/2`. Son mediciones de este simulador, no
calibración de una cámara física ni generalización a casos reservados.

Se guardaron seis episodios: dos programas del aprendiz y uno del verificador,
cada uno sobre dos escenas. Se conserva el segundo programa fallido del aprendiz.
Reanudar verificó los registros sin crear episodios ni peticiones nuevas al
modelo. La biblioteca versionada contiene ahora esta primera habilidad.

## Segunda habilidad: agarre a partir de visión

La [campaña de agarre](../outputs/local/so101-partial-grasp-learning-20261019/result.json)
terminó con `verified`. Codex recibió la biblioteca de localización, generó un
primer programa que agotó el tiempo del cierre antes de contactar y, tras revisar
resultados e imágenes, aumentó el tiempo permitido. El segundo programa obtuvo
`skill_success=2/2`; otro proceso aplicó la habilidad propuesta y también obtuvo
2/2. La revisión independiente confirmó procedencia y aplicación.

La nueva skill es
[`geometry-centered-slow-opposing-grasp.md`](../configs/so101/skills/geometry-centered-slow-opposing-grasp.md).
Los contactos bilaterales continuos duraron **0,640 y 0,624 s**, superando el
umbral de 0,5 s. El contacto seguía calificado al finalizar y no hubo apoyos no
permitidos ni violaciones registradas en los cuatro episodios aprobados. La
fruta permaneció unida a la planta: no se acredita desprendimiento ni cosecha.

Se conservaron seis episodios, incluidos los dos fallidos del primer programa,
22 recibos de herramientas, cuatro procesos del modelo y las 156 fuentes exactas
en `inputs/runtime-source.zip`. La reanudación mantuvo los 46 archivos de recibos
y el hash de biblioteca sin cambios. Son los mismos dos casos de desarrollo;
esta prueba no midió generalización ni usó las particiones reservadas.

Las grabaciones están disponibles en la
[galería local](../outputs/local/galeria-pruebas/index.html), en «Nuevo · aprendizaje
de agarre», con dos cámaras y animaciones alternativas.

La auditoría detectó dos defectos del evaluador: diferencias de redondeo alrededor
de 0,5 s y omisión de apoyos no permitidos en el filtro parcial. Se corrigieron
después de terminar y comprobar la reanudación de esta campaña; también se
añadieron medidas posteriores al episodio para diagnosticar el contacto. Los
cuatro agarres aprobados superaban 0,623 s y no tenían esos apoyos. Sus registros
y puntuaciones originales se conservan; las próximas campañas usarán el código
corregido y una identidad nueva.

Las correcciones del evaluador superaron 88 pruebas en el entorno instalado;
el [informe](../outputs/local/so101-grasp-evaluator-review/applied-tests.xml)
incluye los casos de redondeo, apoyo no permitido y filtrado de datos privados.

La [guía de ejecución](so101-iterative-debugging.md) contiene los comandos.
El [informe de validación](so101-validacion-sistemas-v2.md) distingue pruebas
reales, fixtures y limitaciones pendientes.

Se conservan la [auditoría inicial](auditoria-so101-aspire-2026-10-19.md),
su [lista de tareas original](historial-plan-so101-fresas-auditoria-2026-10-19.md)
y el [plan anterior](historial-plan-so101-fresas-2026-10-19.md).
