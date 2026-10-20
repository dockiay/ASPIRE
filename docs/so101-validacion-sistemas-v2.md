# Validación de los sistemas ASPIRE / SO-101

Fecha: 19 de octubre de 2026. El criterio acordado es que funcionen las
herramientas, el controlador, la evaluación y la gestión de conocimientos.
El robot puede fallar la prueba de cosecha.

## Campaña real con Codex

Registro: [so101-strawberry-v2-20261019](../outputs/runs/so101-strawberry-v2-20261019/progress.md).
Es una ejecución real del simulador y del controlador Codex, con segmentación
por colores. No se presenta como una ejecución de SAM3.

| Medición | Resultado |
|---|---|
| Programas propuestos por el agente | 8 |
| Episodios de desarrollo | 24: tres casos por programa |
| Episodios de validación del seleccionado | 2 |
| Episodios finales del seleccionado | 3 |
| Total de episodios registrados | 29 |
| Recibos de herramientas del controlador | 35 |
| Revisión independiente de procedencia | PASS |
| Código del seleccionado ejecutado correctamente | 3/3 en desarrollo, 2/2 en validación, 3/3 en evaluación |
| Cosechas completas del seleccionado | 0/3, 0/2 y 0/3 respectivamente |
| Reanudación de la campaña terminada | Sin episodios ni llamadas nuevas al modelo |
| Propuestas de habilidades en esta campaña | Ninguna; biblioteca sin promociones |

El seleccionado es `c-c1c55eb01d02eaed`, SHA-256
`c1c55eb01d02eaed94d23cbd70da832f0f47eea19b50bdb767ec99cb7478d8a7`.
Se aplicó la regla fijada antes de ejecutar: éxitos físicos, ejecuciones correctas,
menor AST y orden de envío. Algunas variantes lograron agarre cualificado, pero
ninguna completó la separación, transporte y depósito. No se altera la regla
retrospectivamente para seleccionar un resultado parcial más vistoso.

El proceso terminó con `status=done` y `full_harvest_solved=false`. Esto es coherente:
el evaluador detecta el fracaso y conserva sus evidencias.

La fuente exacta de aquella ejecución está en `inputs/runtime-source.zip` y su
manifiesto, dentro de la campaña. SHA-256 del archivo:
`fe876f07fcadf69e710c458c43d72d29096864919bca176c65012e1cd6a62533`.
Los cambios posteriores de diagnóstico, transporte API y SAM3 requieren una
identidad nueva; no modifican los episodios históricos.

## Qué está probado y con qué alcance

- Codex: prueba real de corrección de un error de API, campaña completa,
  revisión independiente y reanudación sin repetir llamadas.
- API Responses: servidor HTTP de prueba, credencial en entorno, funciones,
  imágenes, informe estructurado y recuperación sin duplicados. No se ha
  realizado una llamada a un proveedor comercial con una credencial del usuario.
- Coordinador y habilidades: pruebas de particiones, selección congelada,
  progreso, verificador aislado, rechazo/promoción y biblioteca versionada.
  Las promociones de los tests utilizan resultados sintéticos explícitos.
- Robot y banco: fixtures nativos de geometría, contactos, fuerza transitoria,
  parada de acciones y condiciones positivas/negativas de evaluación. No prueban
  calibración física ni éxito general de cosecha.
- SAM3: selección del proveedor original, preflight y procedencia del modelo,
  protocolos HTTP y composición con profundidad pública probados. Entorno
  `.venv-sam3`, PyTorch 2.9.1/CUDA 12.8 y RTX 4090 comprobados. Login, descarga
  de pesos e inferencia real completados; véase el registro siguiente.

Tras conectar SAM3 y añadir los filtros explícitos de proyección pasaron
**289 pruebas y una quedó omitida**, cubriendo flujo, diagnóstico, percepción,
geometría, ejecutor restringido, transporte API y protocolo canónico. El
[informe JUnit actual](../outputs/local/so101-sam3-live-tests.xml) conserva los casos.
El [informe anterior](../outputs/local/so101-systems-v2-tests.xml) conserva las
206 pruebas de la comprobación previa.
Se mantienen además las comprobaciones previas de primitivas; no se suman
ejecuciones repetidas como cobertura adicional.

La campaña completa se conserva también como
[archivo ZIP](../outputs/runs/so101-strawberry-v2-20261019.zip), acompañado de su
[manifiesto y SHA-256](../outputs/runs/so101-strawberry-v2-20261019.archive.json).
El original de Ubuntu permanece intacto; las rutas nativas de sus recibos
siguen refiriéndose a `/home/sergio/src/ASPIRE`.

## Percepción y realismo

La [prueba real de SAM3](../outputs/local/so101-sam3-live-20261019-r3/verification.json)
completa seis consultas (`strawberry`, `leaf`, `container`, en dos cámaras), con
detecciones en cinco y 15 instancias proyectadas, sin errores de proyección ni
pasos de movimiento. La ausencia de detección de `container` en `agentview`
queda registrada; la otra vista sí lo detecta. La fresa roja aparece en ambas.
Esto valida el recorrido de inferencia, no la exactitud de todas las máscaras.

El checkpoint es `facebook/sam3`, revisión
`3c879f39826c281e95690f02c7821c4de09afae7`, SHA-256
`9999e2341ceef5e136daa386eecb55cb414446a00ac2b55eb2dfd2f7c3cf8c9e`.
La inferencia usa el servicio de ASPIRE y el submódulo SAM3 fijado en
`6fe87d64a5beb9084923d7a9e002741178635b09`. No se recurrió al proveedor por colores.

El primer intento, `so101-sam3-live-20261019`, se detuvo por usar una reducción
NumPy incompatible con el importador restringido. Se corrigió el programa de
comprobación para operar sobre listas con los builtins permitidos. El segundo
intento (`-r2`) evidenció contaminación de la profundidad en bordes de máscaras:
la PCA devolvía tamaños de decenas de metros al incluir el fondo lejano.
El tercero (`-r3`) utiliza los nuevos parámetros opcionales de la API compartida
`erosion_pixels=1` y `depth_range_m=[0.1, 2.0]`. Los valores predeterminados de
las proyecciones anteriores permanecen sin filtros. Se mantienen los tres
intentos y las máscaras originales se representan en los overlays.

Los filtros excluyen retornos lejanos y muchos píxeles del contorno. Todavía
quedan candidatos contaminados, como una fresa verde y una hoja con cajas 3D
excesivas. Se documenta esa limitación en vez de interpretar todas las cajas
PCA como posiciones fiables. Los centros visibles de la fresa roja difieren
aproximadamente 13 mm entre vistas; esa diferencia de superficies visibles no
es una medición de error respecto a la posición verdadera.

El recorrido es cámara pública → RGB a SAM3 → instancias y confianza → máscara
con profundidad calibrada → nube de puntos → geometría de superficies visibles.
ASPIRE registra llamadas, imágenes y overlays. No se consultan poses nativas
para orientar al agente. No detección, ambigüedad, profundidad inválida y servicio
caído son situaciones explícitas. La estimación no garantiza la forma completa
del fruto ni seguimiento persistente entre vistas.

Las imágenes y profundidad siguen siendo renderizadas; no se ha validado una
cámara física ni ruido calibrado. Las plantas son rígidas y los sensores de
contacto son virtuales. Un modelo de visión real y una escena fotorrealista son
propiedades distintas.

La [guía de ejecución](so101-iterative-debugging.md) y el
[plan vigente](plan-so101-fresas.md) describen cómo usar los sistemas.

## Adaptación de habilidades parciales

La [ejecución adicional de aprendizaje](../outputs/local/so101-partial-localization-learning-20261019/result.json)
ha producido la primera skill de la biblioteca:
[`two-view-ripe-fruit-localization.md`](../configs/so101/skills/two-view-ripe-fruit-localization.md).
La propuso Codex tras inspeccionar su programa y la aplicó otro proceso de Codex
a partir del fragmento de la skill, sin recibir el archivo de programa inicial.
La revisión independiente de procedencia y aplicación terminó en PASS.

Se midieron 4,91 y 5,12 mm de error de centro y 0,29 mm de error de desplazamiento
entre los dos casos de desarrollo. Aprendiz y verificador obtuvieron 2/2 en la
habilidad y 0/2 en cosecha completa, con cero pasos de control. El criterio
registrado requiere ≤20 mm absolutos, ≤10 mm entre escenas, marco/tiempo
correctos y evidencia de percepción pública.

La ejecución conserva seis episodios y 22 recibos de herramientas; hubo dos
programas del aprendiz (uno falló) y uno del verificador. Cuatro procesos del
modelo cubren aprendizaje, verificación y sus dos revisiones independientes.
La [prueba de reanudación](../outputs/local/so101-partial-localization-learning-20261019/resume-verification.json)
confirma que no se crearon episodios ni peticiones adicionales. Las 156 fuentes
de esa ejecución están congeladas en `inputs/runtime-source.zip` dentro de su
carpeta. La biblioteca conserva el hash anterior y el recibo de verificación.

Tras la adaptación pasaron **305 pruebas y una quedó omitida**; véase el
[informe JUnit](../outputs/local/so101-partial-skills-tests.xml). Incluye casos
negativos para coordenadas fijas, movimiento, marco/tiempo incorrectos, fallo
de escena, uso de una skill sin confirmación independiente, verificación por
propuesta y reanudación con registros alterados. Los fixtures sintéticos
permanecen diferenciados de la ejecución nativa con SAM3 y Codex.

La habilidad está verificada en esos dos casos de desarrollo reutilizados.
Esto acredita aplicación independiente, no una mejora causal frente a una
línea base, evaluación reservada ni rendimiento sobre plantas reales.

## Aprendizaje y verificación del agarre

La [campaña parcial de agarre](../outputs/local/so101-partial-grasp-learning-20261019/result.json)
usó Codex, SAM3 y la biblioteca de localización congelada. Se presupuestaron
seis programas y 80 llamadas; el aprendiz necesitó dos programas. El primero
falló en ambas escenas por agotar el tiempo del cierre antes de contactar. El
segundo, `c-8ca0a3467a7570ec`, consiguió agarre válido en 2/2. El verificador
independiente, `c-996b473199780e38`, aplicó la skill y repitió 2/2. La procedencia
y la aplicación obtuvieron PASS; la skill se incorporó a la biblioteca.

| Medida | Caso de desarrollo 0 | Caso de desarrollo 1001 |
|---|---:|---:|
| Instante del agarre acreditado | 4,710 s | 4,776 s |
| Contacto bilateral continuo máximo | 0,640 s | 0,624 s |
| Fuerza final, dedo fijo / móvil | 2,078 / 2,352 N | 1,174 / 1,326 N |
| Contacto final calificado | Sí | Sí |
| Cosecha completa | No | No |

Las medidas coinciden entre el programa seleccionado y el verificador; no hubo
violaciones ni apoyos no permitidos. La unión a la planta sigue activa. Se
conservan seis episodios (dos fallidos, cuatro con agarre), 22 recibos de
herramientas y cuatro procesos del modelo. No se utilizaron casos reservados.

La biblioteca terminó con hash
`eb9f03a79dfe4c279e285602fe7d287f37b2c26e3505dff3a26d25a80776754a` y contiene
localización y agarre. La [reanudación](../outputs/local/so101-partial-grasp-learning-20261019/resume-verification.json)
verificó 46 archivos de recibos sin cambios y no añadió episodios ni peticiones.
El archivo de las 156 fuentes de la campaña tiene SHA-256
`67aa210b2777f077bc2302f31dc4e88e9795aa0e0bb8f4778a56adbd79813491`.

Después del cierre y de la reanudación se corrigió el evaluador para las próximas
ejecuciones: tolerancia de redondeo de 1e-9 s, igual a la del testigo nativo;
rechazo de `non_finger_support_contacts`; y métricas escalares de contacto en el
informe posterior al episodio. El umbral sigue siendo 0,5 s. Las posiciones,
centros y vectores privados no se exponen. Las puntuaciones de la campaña
congelada no se reescribieron y sus fuentes originales están archivadas.

La comprobación de las correcciones en el entorno instalado terminó con
**88 pruebas aprobadas**, incluidas regresiones de redondeo, apoyos prohibidos,
filtrado de geometría privada y pruebas físicas de retención. Ruff y
`git diff --check` también pasan. El [informe JUnit](../outputs/local/so101-grasp-evaluator-review/applied-tests.xml)
conserva esta ejecución; las pruebas de ingeniería no se suman a los seis
episodios de aprendizaje.

## Intentos de desprendimiento con retención

Las campañas `so101-partial-detach-retain-learning-20261019` y
`so101-partial-detach-retain-rethink-20261019` terminaron respectivamente con
ocho programas/16 episodios y cuatro programas/ocho episodios. Ningún episodio
registró liberación mecánica y retención libre; no se propuso ni promovió una
skill nueva. Las revisiones de procedencia pasaron. Se conservan los fallos y
sus vídeos, sin modificar sus puntuaciones ni usar particiones reservadas.

Ambas reanudaciones conservaron los recibos y la biblioteca sin cambios.
Los directorios de Windows incluyen programas, medios e informes; los ZIP
hermanos contienen todos los registros nativos, incluidas imágenes originales.

Se añadió después una IK genérica de punto y dirección, con giro axial libre,
para expresar cinco restricciones sobre los cinco ejes del SO-101. Las pruebas
verifican objetivos calculados por cinemática directa, diferentes aperturas y
ejes, límites articulares, rechazos tipados y acceso desde el ejecutor
restringido sin pasos de simulación. La IK de pose completa permanece igual.
El conjunto instalado pasó **56 pruebas**: [cinemática y contexto](../outputs/local/so101-point-axis-tests.xml)
y [flujo de habilidades](../outputs/local/so101-point-axis-workflow-tests.xml).
Ruff y `git diff --check` pasan. Estos resultados de ingeniería no son éxitos
físicos ni una habilidad aprendida.

Un diagnóstico aislado empleó el punto nativo de unión para comparar soluciones
geométricas en una escena clonada: encontró más muestras nominales con la
restricción parcial. No ejecutó movimiento posterior al agarre y no valida
fuerzas, desprendimiento o continuidad de trayectorias. Sus puntos, orientaciones
y resultados privados no se entregaron al controlador. La campaña posterior
`so101-partial-detach-retain-point-axis-20261019` recibe únicamente la API
genérica y el resumen público congelado de los fallos anteriores.

Esta campaña de punto y dirección terminó con cuatro programas y ocho
episodios, `no_proposals`: **cero liberaciones y cero retenciones libres**.
El programa seleccionado, `c-d0212fe19c0c2cf5`, terminó sin error y sin
violaciones registradas en ambas escenas, pero perdió el contacto y dejó la
unión activa. Otros intentos registraron colisión con una zona no permitida
de la pinza, cierre limitado por duración, exceso de fuerza o IK no alcanzable.
La revisión independiente de procedencia fue PASS; ninguna skill fue propuesta
ni promovida. La biblioteca conserva localización y agarre inicial.

La [reanudación](../outputs/local/so101-partial-detach-retain-point-axis-20261019/resume-verification.json)
comprobó 43 archivos de recibos sin cambios y no creó episodios ni llamadas
al modelo. El hash de biblioteca permaneció
`eb9f03a79dfe4c279e285602fe7d287f37b2c26e3505dff3a26d25a80776754a`.
Las 156 fuentes están en `inputs/runtime-source.zip`, con SHA-256
`c37f02a608afaf1b3452f9b8d783a19e21695e188a1ebf8cfd0821a1e41561c9`.
El [resultado](../outputs/local/so101-partial-detach-retain-point-axis-20261019/result.json)
conserva el fracaso físico; los ZIP completos y vídeos permiten revisarlo.

La siguiente prioridad identificada es supervisar fuerzas y contacto mientras
se mueve el brazo. Actualmente el cierre tiene vigilancia por subpasos; las
trayectorias posteriores pueden aumentar la fuerza o perder la fruta aunque
el cierre inicial haya sido válido. No se han cambiado los límites del banco
ni el criterio de éxito para hacer pasar estos episodios.

## Movimiento del brazo supervisado por sensores públicos

Se implementó `so101.command_joints`: limita la velocidad de las consignas,
mantiene la apertura medida y vigila fuerza/contacto antes de comenzar y en
cada subpaso físico. Un umbral solicitado puede parar la acción sin alcanzar
su objetivo; la inercia puede sobrepasarlo y la herramienta no oculta una
violación nativa. No resetea posiciones ni velocidades, no contiene geometría
de fresas ni una política de cosecha. Los sensores virtuales leen contactos
en las puntas contra cualquier objeto, igual que la API pública; no se usa
una señal privada de agarre a la fruta.

Las [16 pruebas nativas](../outputs/local/so101-guarded-joint-tests.xml)
comprueban un pico de sensor de 2 ms ya ausente al devolver el resultado,
parada por pérdida de contacto y corrección posterior, conservación de
violaciones terminales, tiempo agotado, alcance de una posición pequeña,
apertura, entradas inválidas y llamada desde el ejecutor restringido.
Los picos son fixtures de ingeniería explícitos; no son episodios de cosecha.
Las [36 pruebas del flujo](../outputs/local/so101-guarded-workflow-tests.xml)
también pasan. Ruff y la igualdad de fuentes Windows/Linux están comprobados.

La campaña `so101-partial-detach-retain-guarded-20261019` inicia un experimento
nuevo con seis programas como máximo, contexto congelado y el mismo contrato
`retain_ripe_fruit_v1`. Las 157 fuentes están archivadas con SHA-256
`50c7738c3e4cc3e2ceff83f79530a06c969890b186245a8be507bb36e7c69d19`.
Los éxitos de estas pruebas de software no se suman al resultado físico.

La campaña supervisada terminó con **seis programas y doce episodios**, todos
registrados, sin liberación mecánica ni retención libre. La quinta variante
`c-24669c86ffdc91f8` terminó limpia en ambas escenas y conservó contacto final;
el contacto bilateral continuo máximo fue **13,67 y 6,252 s**. Sus 20 órdenes
supervisadas de brazo en la escena 0 alcanzaron sus objetivos; eso no prueba
rotación solidaria de la fruta. La última variante de tracción perdió el
contacto en ambas escenas y tampoco liberó la unión. La selección final
conserva puntuación parcial y cosecha 0/2; no se propuso ni promovió una skill.

La revisión independiente de procedencia fue PASS. La
[reanudación](../outputs/local/so101-partial-detach-retain-guarded-20261019/resume-verification.json)
verificó **60 archivos de recibos sin cambios**, sin añadir llamadas al modelo
ni episodios; la biblioteca conserva el hash anterior. El ZIP completo contiene
7.112 archivos, con SHA-256
`23961995a5b6a53a673894d6ff17c56d5201bcf71727a7c0a2f3e572183d46b7`.
La [galería](../outputs/local/galeria-pruebas/index.html) conserva los doce
episodios en «Nuevo · movimiento supervisado», junto a los intentos anteriores.

## Corrección del diagnóstico después de cerrar la campaña

Se publicaron los rangos de las peticiones en `describe_task` y
`so101.get_controller_metadata()['action_limits']`. El cuarto programa había
pedido 12 s a una acción limitada a 10 s, que se rechazó antes de mover.
Los mensajes inválidos ahora incluyen rangos explícitos. También se corrigió
la consulta de metadatos en el banco básico `so101_control`, que no define
`task_name` en el entorno: se usa el contexto registrado de la tarea.

`inspect_results` devuelve automáticamente un resumen acotado de resultados
de acciones públicas: motivos de parada, errores, fuerzas máximas, llamadas
con cero pasos y objetivos articulares alcanzados. Lee sólo salidas de acciones
autorizadas y comprueba sus hashes contra el manifiesto. No devuelve entradas,
coordenadas objetivo, imágenes, detalles arbitrarios ni estado del evaluador;
una acción correcta no se convierte en éxito físico.

Las [59 pruebas posteriores](../outputs/local/so101-public-action-feedback-tests.xml)
incluyen rechazo de trazas alteradas, filtrado de datos no autorizados,
acotación de historial, fronteras reales de duración y las regresiones del
control y del flujo. Ruff y `git diff --check` pasan. Una
[revisión retrospectiva](../outputs/local/so101-public-action-feedback-review.json)
aplicó el extractor a tres trazas inmutables: recuperó el motivo concreto de
colisión que el programa resumía como `pressure correction failed` y las
órdenes alcanzadas de la quinta variante. No ejecutó episodios ni cambió
puntuaciones, peticiones o respuestas históricas. Las campañas congeladas
conservan su código; futuras campañas deben usar otro directorio.

La galería final contiene 60 episodios y 120 vistas de cámara entre todas las
campañas conservadas. Se verificaron 458 archivos y respuestas HTTP 200 para
MP4, imágenes, máscaras y animaciones alternativas. La reproducción del MP4
supervisado se comprobó también en el navegador de la aplicación; la
[captura](../outputs/local/galeria-pruebas/movimiento-supervisado-verificado.png)
muestra reproducción a los 3,7 s. Es evidencia de reproducción, no de cosecha.
## Comparación visual del giro: integración y comprobación de ingeniería

El nuevo `so101.compare_visual_motion` compara textura visible en máscaras
SAM3 entre dos observaciones RGB-D públicas. Estima movimiento rígido mediante
correspondencias y lo contrasta con la pose medida del TCP. Nunca consulta
poses nativas de la fruta ni condiciones privadas de liberación. Las cámaras
contradictorias, la textura insuficiente y la incertidumbre producen resultados
desconocidos; no se sustituyen por el giro del robot o una orientación PCA.

La [suite de integración](../outputs/local/so101-visual-motion-workflow-tests.xml)
aprobó **100 pruebas**: giros y traslaciones conocidos, fruta inmóvil con pinza
girando, ejes incompatibles, puntos atípicos, pérdida de profundidad, oclusión,
capturas desincronizadas, cámaras contradictorias, acceso desde el programa
restringido, conservación de registros y contratos previos. Estas pruebas de
software no son episodios de cosecha. Una revisión independiente reprodujo y
permitió corregir una falsa compatibilidad al promediar cámaras contradictorias.

La [comprobación con FruitGym](../outputs/local/so101-visual-motion-calibration-20261019/calibration-results.json)
usa diez capturas renderizadas a 1280 × 960, SAM3 real y dos pruebas de máscaras
insuficientes. Son transformaciones conocidas inyectadas en un fixture, con
cero pasos físicos, para medir el sensor; sus poses no se suministran al
controlador. Los giros de 8° alrededor de tres ejes producen errores de
orientación de 0,84–1,03°. El caso de 16° tiene un error de 5,68°. La fruta
inmóvil con pinza girando se reconoce como movimiento relativo; las máscaras
insuficientes quedan desconocidas.

Las pruebas positivas de movimiento conjunto de ese fixture todavía reciben
resultados conservadores o desconocidos: no demuestran sensibilidad suficiente
durante un agarre ocluido. La identidad y vigencia de las máscaras siguen
dependiendo del controlador. Los umbrales y la incertidumbre son heurísticas
de ingeniería, no una calibración de cámaras físicas ni validación biológica.
El estimador comprobado tiene SHA
`6222e82fa38323a503102bae663c6dd3aaab3065984d7c3428fce4d11bdac227`.

## Primera campaña con comparación visual: resultado histórico y cuarentena

La campaña `so101-partial-detach-retain-visual-motion-20261019` terminó con
**seis programas, doce episodios y nueve comparaciones visuales ejecutadas**.
Nueve episodios acabaron sin error de programa; ninguno desprendió la fresa ni
cumplió `retain_ripe_fruit_v1`, que exige liberación mecánica y dos segundos de
retención libre. La selección conservada es `c-348b8b8f76521104`, con ejecución
correcta 2/2 y éxito físico 0/2. No hubo propuestas ni promoción de skills.

La [revisión independiente del ciclo visual](../outputs/local/so101-visual-cycle-review.json)
comprobó que las máscaras comparadas proceden de llamadas SAM3 frescas y que
sus capturas coinciden con los tiempos de observación y del robot. También
inspeccionó cuatro superposiciones de máscaras de una variante. Esa comprobación
no certifica la identidad visual de todos los objetos en todos los episodios:
las máscaras carecen de marca temporal propia y de identidad persistente.

Las nueve comparaciones devolvieron cinco casos de movimiento relativo, uno
compatible con movimiento conjunto, uno de movimiento demasiado pequeño y dos
desconocidos. En `c-97847b5876d15a35`, escena 0, la estimación fue de 3,70° para
la fruta y 3,99° para el TCP, con discrepancia angular de 0,75° e incertidumbre
heurística de 1,47°. La compatibilidad se refiere únicamente a esos dos instantes
observados; carece de confirmación independiente de orientación desde ambas
cámaras y no demuestra agarre continuo, desprendimiento ni retención libre.
No se consultó orientación nativa para medir el error absoluto del estimador
durante estos episodios. Un resultado desconocido no significa giro cero.

**Ninguno de los seis programas decidió su siguiente movimiento a partir del
resultado visual dentro del episodio.** Imprimieron la comparación después de
la maniobra. ASPIRE sí revisó imágenes y mediciones para corregir programas
entre intentos; las decisiones durante la ejecución dependieron de acciones,
contacto y fuerza. Por tanto, esta campaña demuestra uso de la percepción para
depurar entre versiones, pero deja pendiente la corrección visual durante la
maniobra solicitada por el usuario.

La [auditoría canónica de procedencia](../outputs/local/so101-partial-detach-retain-visual-motion-20261019/learner/independent-provenance/audit.json)
quedó **QUARANTINED**. El revisor interpretó el código de agarre proporcionado
en la biblioteca congelada como un programa previo prohibido, aunque el flujo
declaraba permitida la reutilización de skills. Señaló expresamente que los
objetivos se obtenían de SAM3 RGB-D y distinguió el fallo físico de esa objeción
de procedencia. Registramos el conflicto de interpretación sin sustituir su
veredicto por PASS. La revisión visual posterior tampoco lo modifica ni
habilita promoción.

La [reanudación bajo las mismas fuentes](../outputs/local/so101-partial-detach-retain-visual-motion-20261019/resume-verification.json)
preservó la cuarentena y **71 archivos de recibos sin cambios**, sin añadir
episodios ni solicitudes al modelo. La biblioteca mantuvo SHA-256
`eb9f03a79dfe4c279e285602fe7d287f37b2c26e3505dff3a26d25a80776754a`.
El [archivo de entradas](../outputs/local/so101-partial-detach-retain-visual-motion-20261019/inputs/archive.json)
conserva 160 fuentes en `inputs/runtime-source.zip`, SHA-256
`5093df03fc6649d7a2c86f90b7340e70ee7371bf082e143b6f999bd9974029f6`.
El ZIP completo contiene 6.494 archivos y tiene SHA-256
`67e2fdedb75046dfcae0e57df17f1c7c48a374260ed20384f6448f55d2996ff7`.
La carpeta expandida de Windows contiene programas, resultados, recibos y
medios; el ZIP conserva además los artefactos nativos completos.

## Aclaración de procedencia posterior al archivo de la campaña

Después de archivar ese experimento se aclaró en los mensajes del trabajador
y del revisor que pueden reutilizarse patrones de código de la biblioteca
congelada. Cada objetivo de la tarea debe seguir derivándose de observaciones
públicas actuales. Continúan prohibidos los objetivos o píxeles copiados,
otros programas previos no autorizados, el estado privado, las ramas por
semilla y los cambios de física. Una etiqueta de skill verificada no exime
de revisar sus constantes ni certifica éxito en un episodio nuevo.

La auditoría ahora comprueba el hash canónico de la biblioteca, los hashes de
cada contenido y la presencia del snapshot exacto en el prompt que recibió el
trabajador. Registra un descriptor acotado de los miembros permitidos y rechaza
manipulaciones antes de llamar al revisor. El revisor conserva la decisión de
procedencia: una biblioteca válida no fuerza PASS. Los registros históricos
permanecen intactos y los cambios requieren otra identidad experimental.

Las [53 pruebas posteriores de procedencia y regresión](../outputs/local/so101-skill-provenance-tests.xml)
pasaron, incluidas 15 específicas de integridad de biblioteca, permiso recibido,
conservación de QUARANTINED, código seleccionado y auditorías inmutables. Son
pruebas con respuestas de revisión simuladas; no demuestran comprensión
semántica de un revisor real ni éxito de cosecha. Este conjunto comparte
regresiones con las 100 pruebas anteriores: **no se contabilizan como 153
pruebas únicas**. El criterio físico y la biblioteca de habilidades no se
modificaron para aceptar los episodios fallidos.

## Decisiones visuales dentro del episodio: campaña posterior

La campaña `so101-partial-detach-retain-visual-gated-20261019` congeló una
identidad nueva tras aclarar la biblioteca permitida. Codex escribió dos
programas, cada uno ejecutado en las dos escenas de desarrollo. No se modificó
el entorno, la unión liberable, los límites de contacto ni el contrato
`retain_ripe_fruit_v1`. No se usaron las particiones reservadas.

El primer programa dejó la comparación visual después de un recorrido articular
largo: acabó por contacto prohibido o pérdida de contacto antes de llegar a ella.
Sus dos episodios tienen cero comparaciones. El controlador revisó las imágenes
y resultados, cambió a una orientación completamente especificada, rechazó
saltos articulares grandes y situó la comparación después de cada segmento.

El segundo programa, `c-0dd5a71aa06668bd`, sí consultó la visión durante ambos
episodios. Los giros estimados fruta/pinza fueron 0,573°/0,944° y 0,497°/0,940°;
la incertidumbre angular fue 7,765° y 1,603°. Los dos resultados fueron
`motion_too_small`. El programa tomó efectivamente la rama de parada por
evidencia insuficiente: no hubo acciones del brazo, pinza ni pasos físicos
posteriores a esas comparaciones. Por tanto, se demuestra una parada decidida
por visión, pero no una corrección visual de deslizamiento: esa rama existe
en el código y no se alcanzó en estos episodios.

La variante seleccionada tiene `program_ok=2/2`, contacto bilateral final en
ambas escenas y cero desprendimientos o retenciones libres. El contacto continuo
máximo fue 1,098/1,090 s; estos tiempos no prueban liberación. No propuso ni
promovió habilidades. La revisión independiente de procedencia fue `PASS`
tras inspeccionar también el contenido completo de las dos skills reutilizadas;
este dictamen no cambia la cuarentena de la campaña anterior.

La [reanudación](../outputs/local/so101-partial-detach-retain-visual-gated-20261019/resume-verification.json)
conservó 34 archivos de recibos y el hash de biblioteca. Se archivaron 1517
archivos en un ZIP completo con SHA
`d0b54a8bc69447813f7f7b0f99466588cbdb7118ac2d5374edcb3c888b7f5aed`.
Las 160 fuentes congeladas tienen SHA de archivo
`4a768da67be8baf2be7f53b68f12fb3d768bac5a843405ffd57461f52f22e3cc`.
Los [resultados visuales](../outputs/local/so101-partial-detach-retain-visual-gated-20261019/visual-motion-review.json)
y la [revisión del flujo ejecutado](../outputs/local/so101-visual-gated-cycle-review.json)
separan decisiones observadas, ramas no ejecutadas y resultado físico pendiente.

La galería reúne ahora 76 episodios y 152 vistas, con 580 archivos comprobados
y respuestas HTTP 200 para vídeos, imágenes, máscaras y animaciones. Se comprobó
la reproducción del segundo programa en el navegador de la aplicación: la
[captura](../outputs/local/galeria-pruebas/decision-visual-reproduccion-verificada.png)
muestra el vídeo a los 4,0 de 5,4 s. La pestaña «Nuevo · decidir con la visión»
incluye las cuatro pruebas y las medidas de giro desplegables; «Comprobar el
giro» mantiene visible la cuarentena de la campaña anterior.

## Giro y tracción solicitados por el operador

El 20 de octubre, la campaña `so101-partial-twist-pull-20261019` completó
cuatro programas y ocho episodios en los mismos dos casos de desarrollo.
El operador pidió girar y tirar tras agarrar. El coordinador transmitió ese
objetivo y observaciones públicas anteriores; Codex eligió incrementos, ejes,
direcciones, ventanas visuales, recuperación y límites. Se conservaron las
fuentes, la física y el contrato `retain_ripe_fruit_v1` de la campaña anterior.

| Variante | Cambio propuesto por el controlador | Movimiento conseguido en las escenas 0 / 1001 |
|---|---|---|
| 1: `c-c4a59eed842ad3e8` | Giro axial por etapas antes de retirar | Giro del TCP 10,79° / 11,93°; movimiento relativo detectado; no comenzó la tracción |
| 2: `c-b3e45a50ebee3f86` | Retirar después del primer giro corto | Giro del TCP ~5,96°; desplazamiento durante tracción 1,78 / 0,88 mm; parada por pérdida de contacto |
| 3: `c-1f35753e2a4c8a7c` | Renovar el cierre antes de cada retirada | Desplazamiento del TCP 5,92 / 5,33 mm; fruta estimada 2,27 / 1,63 mm; movimiento relativo |
| 4: `c-17fd77085d2dfae6` | Cambiar la retirada radial por tracción hacia abajo | Desplazamiento del TCP 8,10 / 5,74 mm; fruta estimada 0,90 / 1,57 mm; movimiento relativo y pérdida de contacto |

Los desplazamientos son normas de transformaciones entre imágenes durante la
fase de tracción, que también incluye renovación del cierre; no son recorridos
puros certificados ni distancias de desprendimiento. Los ángulos son medidas
del TCP. Las estimaciones de fruta tienen incertidumbre y varias dependen de
una vista o puntos agrupados sin confirmación independiente de ambas cámaras.

Hubo 22 comparaciones públicas: cuatro compatibles, seis con movimiento relativo,
siete `motion_too_small` y cinco desconocidas. Las decisiones visuales se usaron
dentro de los episodios, incluyendo continuación de sondeos limitados ante
incertidumbre y parada de la maniobra ante movimiento relativo. Las revisiones
entre episodios cambiaron el momento de retirar, la renovación del cierre y
la dirección de tracción. Las seis pruebas de las variantes 2–4 llegaron a
la fase de giro y tracción; la variante 1 no llegó a retirar.

Los ocho episodios terminaron con `program_ok=true`, sin contactos prohibidos
registrados, pero con **cero liberaciones y cero retenciones libres**. La
[auditoría independiente](../outputs/local/so101-partial-twist-pull-20261019/learner/independent-provenance/audit.json)
dio `PASS`. La biblioteca conserva las dos habilidades anteriores; no se
propuso ni promovió ninguna nueva. El resultado `no_proposals` no acredita
que se haya aprendido a desprender ni transferibilidad al hardware.

Todos empataron en resultado físico y ejecución; la regla congelada eligió
la variante 1 por menor AST. Esa selección no la convierte en una solución
de giro y tracción ni demuestra mejora física de las variantes posteriores.
Se conservan todas para inspección. El [informe del coordinador](../outputs/local/so101-partial-twist-pull-20261019/twist-pull-review.json)
vincula fuente y salidas públicas por hashes; es una revisión de registros,
separada de la auditoría independiente del modelo, sin nueva simulación.

Se encontró una limitación del programa generado: `guarded` decide con
`target_reached` y no rechaza explícitamente todos los motivos de parada.
En la variante 4, escena 0, hubo `contact_lost` junto a `target_reached=true`.
La comparación visual de ese mismo punto detuvo la tracción, pero una política
futura debe rechazar la pérdida de contacto aunque esté cerca del objetivo.
Esta observación no modifica retrospectivamente el código ni sus puntuaciones.

La reanudación exacta conservó 50 archivos de recibos y el hash de biblioteca
`eb9f03a79dfe4c279e285602fe7d287f37b2c26e3505dff3a26d25a80776754a`.
No se cambiaron herramientas de movimiento ni evaluadores en este ensayo:
la comprobación nueva son los episodios reales y sus registros, no otra suite
de pruebas de software ni una calibración agrícola.

Se archivaron 5850 archivos completos en el ZIP con SHA
`2e84bbac5c7adb56646d6a3fa5e36e18d6818f05e8bc41261b4b57680e07b4e8`;
las 160 fuentes congeladas se guardaron con SHA de archivo
`c95a7c0bacac29e62421da12e1e79fa8b11cf87d206d24b919ec1f5d8373727e`.
La copia de Windows se verificó por hash. La galería reúne 84 episodios y
168 vistas; se comprobaron 644 archivos y respuestas HTTP 200 de cada tipo
de recurso. «Nuevo · girar y tirar» muestra primero la variante 4, por ser
la más reciente, y conserva las cuatro variantes sin cambiar la selección
experimental. La [captura de reproducción](../outputs/local/galeria-pruebas/girar-tirar-reproduccion-verificada.png)
muestra el vídeo de esa variante a los 9,6 de 10,2 s en el navegador.

## Referencias humanas y flexión más amplia

La [nota de investigación](so101-referencia-recogida-humana.md) y sus
[cálculos reproducibles](../outputs/local/strawberry-picking-research-20261020/calculations.json)
distinguen fuerza de separación, presión de agarre, momento ilustrativo y
definiciones de ángulo. No se encontró una media poblacional de ángulo humano
o recorrido de retirada. Los 20° y 70° citados proceden de robots distintos;
no son un intervalo validado para el SO-101 ni ángulos críticos universales.

La campaña `so101-partial-bend-pull-research-20261020` transmitió al controlador
esas referencias bibliográficas y observaciones públicas. Codex propuso tres
programas sobre los mismos dos casos de desarrollo: seis episodios, todos con
`program_ok=true`, todos con agarre inicialmente calificado y ninguno con
desprendimiento o retención libre. No se modificó el runtime, las fuerzas de
rotura, los materiales, la física ni el evaluador. El guardián nominal elegido
por los programas siguió en 8 N de normal de dedo; no se convirtió la carga
de separación bibliográfica en presión de cierre ni en un par de motor.

| Variante | Cambio del controlador | Giro medido del TCP, escena 0 / 1001 |
|---|---|---|
| `c-6102eae42c372ea8` | Pivote en superficie superior observada; dirección de herramienta por IK de punto/eje | 0,24° / 0,59°; primera petición de 5° interrumpida por fuerza/contacto |
| `c-7c70f4ace04bbcbd` | Orientación completa y espera de asentamiento de 0,4 s tras el cierre | 1,32° / 1,04°; pérdida de contacto durante la primera transición |
| `c-b5c8d2946c4a3277` | Pivote entre contactos públicos, incrementos de 0,5°, cierre renovado y ventanas visuales de 4° | 3,94° / 7,97°; parada por movimiento relativo |

El techo experimental de 40° fue una hipótesis elegida por Codex, no una media
humana ni una amplitud conseguida. Ninguna variante llegó a la retirada que
había previsto después de completar la flexión. Hubo siete comparaciones:
cuatro `motion_too_small`, una desconocida y dos de movimiento relativo. El
último programa tomó la parada visual en ambas escenas. Las similitudes entre
magnitudes de ángulo de fruta y pinza no prueban rotación compartida: el error
de orientación relativa incluye ejes y sentidos.

En la última variante, las estimaciones de giro de fruta fueron 5,16°/8,75°,
con incertidumbre heurística 1,56°/9,91° y confirmación incompleta entre cámaras.
No son ángulos nativos de la fruta ni prueba de que haya alcanzado la consigna.
El contacto final estaba calificado en ambos casos, pero se registraron pérdidas
y recuperaciones transitorias; esto tampoco establece agarre continuo ni éxito.

La [auditoría independiente](../outputs/local/so101-partial-bend-pull-research-20261020/learner/independent-provenance/audit.json)
dio `PASS`. Se conserva la variante inicial por empate físico/de ejecución y
menor AST, según la regla congelada. No se propuso ni promovió ninguna skill;
no se evaluaron casos reservados. Los [registros del coordinador](../outputs/local/so101-partial-bend-pull-research-20261020/twist-pull-review.json)
son una revisión de datos públicos y resultados, distinta de esa auditoría.

La reanudación exacta conservó 40 archivos de recibos y la biblioteca anterior.
El ZIP completo contiene 3969 archivos, SHA
`9c76943163e4571a90a0139f1f4eacd9af0b4a136c5ea46cf82f423234bc6912`.
Las 160 fuentes congeladas se archivaron con SHA de archivo
`60713ff485278f3fde1b83f3724403b71bc431532df53046fe1b7f92d20afa51`.
Los cálculos y el PDF oficial se guardan como investigación de apoyo; el
trabajador recibió el contexto textual congelado, no archivos adicionales
fuera de su frontera de herramientas. Estas ejecuciones comprueban la
aplicación de la consigna experimental, no una cosecha resuelta ni un control
calibrado de tracción o par. No se añadieron cambios de software de movimiento.

La galería reúne ahora 90 episodios y 180 vistas de cámara; se comprobaron
692 archivos y respuestas HTTP 200 para cada tipo de recurso. La pestaña
«Nuevo · flexión más amplia» conserva los seis episodios, mostrando primero
la última variante. Se verificó su reproducción en el navegador de la
aplicación y se guardó esta [captura](../outputs/local/galeria-pruebas/flexion-investigada-reproduccion-verificada.png).

## Búsqueda diversa antes de refinamiento — 20 de octubre de 2026

Se añadió `skill_learning --search-mode diverse`, conservando las seis herramientas
de Codex/API y los contratos físicos. Congela cuatro propuestas de exploración
antes de refinamientos con progenitores inspeccionados. Exige cambios declarados
en dos dimensiones, distinta estructura normalizada de código y revisión de
resultados/fotogramas previos. Entre empates de éxito físico y ejecución deja
elegir por evidencia; no favorece menor AST. La revisión independiente analiza
diversidad de fuente y diversidad realmente ejecutada por separado.

Los tests de búsqueda, herramientas, contexto, contratos parciales, procedencia
y coordinador terminaron con **81 aprobados**, más Ruff sin incidencias.
Son pruebas con artefactos sintéticos; la evidencia física se registra aparte.
No se cambió el control de movimiento, SAM3, la física ni el criterio de éxito.

La [campaña](../outputs/local/so101-partial-diverse-search-20261020/strategy-search-review-v2.json)
ejecutó seis programas y doce episodios en desarrollo 0/1001: cuatro episodios
sin error de programa, ninguna liberación ni retención libre. La revisión de
procedencia dio PASS y confirmó fuentes materialmente diferentes. Tres familias
no llegaron a su maniobra distintiva: ambigüedad de percepción o colisión en cierre.
La flexión inicial obtuvo giro TCP de 0,146°/0,158°. Su refinamiento seleccionado
`c-a1a5c5988f230ecd` obtuvo 4,286°/0,919°, con contacto continuo máximo
3,412/0,904 s. La visión sigue siendo insuficiente para acreditar acoplamiento.
El último refinamiento detectó movimiento relativo y terminó con colisión al
intentar sostener tras perder contacto. Se conservan estos fallos y regresiones.

No hubo propuestas ni promociones de skills, ni acceso a particiones reservadas.
La reanudación conservó **58 recibos** y la biblioteca SHA
`eb9f03a79dfe4c279e285602fe7d287f37b2c26e3505dff3a26d25a80776754a`.
Las 161 fuentes congeladas tienen SHA de archivo
`de6bc7455eb9e7f2d17af74ebffa13d3a7d6ee66bd55dfaeb6c3afef43c90ebf`.
El ZIP completo contiene 4362 archivos, SHA
`707a26fa148f4f77ff3aa8e09980b4f6c397b8f988ff11e8a77fbe41cd3ab42d`.
La revisión derivada v2 añade índices y etiquetas de casos al resumen posterior;
el ZIP conserva el resumen inicial y los artefactos canónicos originales.

El campo histórico `submission.failure_mode` registra el fallo del programa
anterior que motivó la propuesta, no el diagnóstico de esa propuesta. El revisor
señaló que su etiqueta `robot_collision` discrepaba con el resultado seleccionado;
el diagnóstico y la puntuación nativos de este último son `junction_not_released`.
No se reinterpretan ni corrigen sus resultados retrospectivamente.

La [comparación de métodos](so101-busqueda-estrategias.md) recomienda búsqueda
evolutiva con archivo, inspirada en MAP-Elites/ELM, y separar factibilidad de
calidad. El modo actual es una primera exploración/refinamiento: no implementa
MAP-Elites completo ni optimización bayesiana, ni demuestra aún mayor eficiencia.

La galería suma **102 episodios y 204 vistas**; se comprobaron 782 recursos y
respuestas HTTP 200 por tipo. «Nuevo · estrategias distintas» muestra los doce
episodios y sus hipótesis. Se verificó reproducción nativa del programa seleccionado
y se guardó esta [captura](../outputs/local/galeria-pruebas/estrategias-distintas-reproduccion-verificada.png).
