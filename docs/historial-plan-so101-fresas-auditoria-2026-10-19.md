# Plan vigente: ASPIRE con SO-101 para cosechar fresas

Actualizado: 19 de octubre de 2026.
Base: [auditoría del adaptador, herramientas y cuatro episodios](auditoria-so101-aspire-2026-10-19.md).
El [plan anterior](historial-plan-so101-fresas-2026-10-19.md) se conserva como histórico.

## Objetivo y reparto de responsabilidades

Usar el ciclo `iterative-debugging` de ASPIRE para que Codex genere, ejecute,
revise y mejore un programa que **coseche una fresa, la conserve durante el
transporte y la deposite en un recipiente en un único episodio**, con el SO-101
y los recursos de planta FruitGym. Después medir su comportamiento en situaciones
nuevas y conservar únicamente habilidades que otro agente pueda reproducir.

Nos corresponde construir el entorno, los criterios de éxito, las herramientas
generales del robot y el protocolo de evaluación. Al agente le corresponden la
estrategia, los movimientos y las correcciones a partir de observaciones.
La verificación de primitivas puede usar objetos/fixtures de prueba; sus
trayectorias y datos nativos no se entregarán como receta de cosecha al agente.

Comprar un SO-101 y transferir lo aprendido a plantas reales sigue siendo el
objetivo posterior. Esta fase usa simulación y sensores virtuales declarados.

## Estado comprobado

| Parte | Estado real |
|---|---|
| SO-101, recursos FruitGym y ejecución en WSL | Integrados |
| Generar → ejecutar → revisar → corregir con Codex | Comprobado en cuatro candidatos sobre dev0 |
| Programa de cosecha completa exitoso | Pendiente; 0/4 episodios exitosos |
| Contrato/evaluador de cosecha | Necesita corrección: conserva condiciones de ejercicios anteriores |
| Geometría pública de pinza y control durante el cierre | Incompletos |
| Diagnóstico temporal de cosecha | Necesita reparación |
| Casos de cosecha separados en desarrollo y reservados | Pendientes; solo existe dev0 |
| Campaña canónica, procedencia, verificador y biblioteca | Integración parcial; sin habilidades promovidas |
| Física calibrada y transferencia al robot real | Posteriores |

Los casos, campañas y éxitos del antiguo ejercicio de desprendimiento conservan
su valor histórico. No completan estas tareas para la escena FruitGym.
Las pruebas de software aprobadas no equivalen a cosechas exitosas.

## Orden de trabajo

**Siguiente tarea: T01, corregir y versionar el contrato de cosecha.**
No iniciar otra campaña puntuable antes de cerrar T01–T08. Las pruebas de
infraestructura necesarias para cada tarea sí pueden ejecutarse durante ellas.

T02 y T03 pueden avanzar en paralelo una vez acordadas las reglas de T01;
T04 utiliza sus contratos y resultados.
T06 y el diseño de T07–T08 pueden prepararse mientras se valida el banco.
Toda campaña futura usará una identidad nueva; los episodios históricos no se
reclasificarán con un evaluador distinto.

| ID | Prioridad | Tarea | Depende de |
|---|---|---|---|
| T01 | P0 | Evaluar resultados físicos sin imponer la receta anterior | Auditoría completada |
| T02 | P0 | Reparar diagnósticos y estados de ejecución | Contrato T01 |
| T03 | P0 | Publicar y verificar la geometría de la pinza | Contrato T01 |
| T04 | P0 | Controlar el cierre y devolver sus límites/resultados | T02, T03 |
| T05 | P1 | Verificar que el banco y las primitivas permiten la tarea | T01–T04 |
| T06 | P1 | Crear protocolo propio con casos nuevos y reservados | T05 |
| T07 | P1 | Completar el coordinador ASPIRE y la auditoría de procedencia | T02, T06 |
| T08 | P1 | Conectar biblioteca de habilidades y verificador | T07 |
| T09 | P1 | Ejecutar desarrollo autónomo de la cosecha completa | T01–T08 |
| T10 | P1 | Evaluar el programa congelado y las habilidades | T09 |
| T11 | Posterior | Preparar transferencia al SO-101 real | Evidencia T10 y hardware/mediciones |

## T01 — Contrato y evaluador de cosecha

Responsable: infraestructura. Estado: pendiente.

- [ ] Especificar públicamente las relaciones exigidas: agarre acreditado,
  desprendimiento mecánico con retención, transporte, liberación dentro del
  recipiente, apoyo estable y retirada de la pinza. Declarar restricciones
  y tiempos de comprobación, incluido el mantenimiento libre exigido.
- [ ] Separar esas relaciones de la preparación fija `ready_step` y del
  desplazamiento heredado de 21 mm. Cerrar antes de una pose pedagógica no debe
  invalidar por sí solo un agarre físicamente válido.
- [ ] Evaluar depósito por contención, soporte, liberación y estabilidad dentro
  de la región útil; retirar la exigencia de una única coordenada de apertura.
- [ ] Mantener comprobaciones de caída, desprendimiento sin sujeción, contactos
  prohibidos, fuerzas y penetraciones. Distinguir límites de operación públicos
  de parámetros biológicos privados usados para variar el banco.
- [ ] Versionar contrato, configuración y resultados. Conservar las lecciones
  antiguas bajo su protocolo anterior.
- [ ] Añadir pruebas positivas con distintas poses de agarre y regiones válidas
  de depósito, junto con negativos por cada restricción relevante.

**Aceptación:** ninguna dependencia residual de un waypoint/espera secretos
impide acreditar relaciones válidas. Los casos negativos siguen rechazándose.
No basta eliminar una bandera ni rebajar umbrales para obtener un éxito.

## T02 — Diagnóstico temporal y estados coherentes

Responsable: infraestructura. Estado: pendiente.

- [ ] Conservar el primer instante y fase real de cada infracción, comando
  activo, medición/pico, par de contacto y referencias a imágenes antes/después.
- [ ] Separar medición instantánea y máximo durante la acción.
- [ ] Distinguir ejecución del código, aborto de acción, resultado declarado por
  la política y validez/éxito físico del episodio. Una excepción capturada por la
  política no convierte su objetivo en exitoso.
- [ ] Definir fallos irreversibles, condiciones de parada y errores recuperables;
  devolverlos de forma que el agente pueda supervisar y decidir la recuperación.
- [ ] Preservar el filtro de información privilegiada al publicar diagnósticos.
- [ ] Usar registros existentes cuando contengan el evento original; cuando no
  lo contengan, crear regresiones con tiempos conocidos sin inventarlos.

**Aceptación:** un pico transitorio o una colisión aparecen con su momento y
acción, aunque al terminar hayan desaparecido. Un estado terminal impide
movimientos posteriores; un error recuperable permite recuperación explícita.

## T03 — Contrato general del efector SO-101

Responsable: adaptador del robot. Estado: pendiente.

- [ ] Describir TCP, ejes, dedo fijo/móvil y superficies útiles de contacto.
- [ ] Exponer apertura métrica y relación con el comando normalizado.
- [ ] Definir y verificar la región/marco de agarre en función de la apertura.
- [ ] Comprobar transformaciones contra FK y geometría con objetos genéricos.
- [ ] Entregar esta información por las APIs públicas usadas por el agente.

**Aceptación:** un cliente puede situar un objeto entre los dedos con la
información pública del efector, sin conocer offsets específicos de la fresa
ni leer el modelo nativo del entorno.

## T04 — Primitivas de cierre y movimiento supervisables

Responsable: adaptador/controlador. Estado: pendiente.

- [ ] Añadir control general de duración/velocidad del cierre y límites
  configurados de contacto/fuerza en el perfil de simulación.
- [ ] Comprobar y detener dentro de la acción, con resolución suficiente para
  detectar picos entre observaciones del agente.
- [ ] Devolver motivo de parada, movimiento medido, máximos y contactos.
- [ ] Propagar estados de T02 y evitar continuar acciones tras una parada
  terminal. No ocultar una violación con un `ok=true` ambiguo.
- [ ] Declarar qué depende de sensores virtuales y qué podría soportar la
  futura pinza física.

**Aceptación:** una prueba con un pico entre lecturas activa la parada prevista
y deja evidencia. La herramienta sigue siendo general: no incluye «agarrar
fresa», una trayectoria preparada ni la estrategia de desprendimiento.

## T05 — Verificación del banco con el mesh FruitGym

Responsable: infraestructura y validación independiente. Estado: pendiente.

- [ ] Comprobar espacio libre, geometría de contacto bilateral y retención con
  las primitivas; incluir un caso positivo y negativos controlados.
- [ ] Verificar alcanzabilidad y límites de cinco ejes. Soportar, si hace falta,
  objetivos de posición/dirección con orientación libre explícita; no relajar
  silenciosamente una pose 6D solicitada.
- [ ] Incorporar validación general de trayectorias frente a obstáculos
  observables, con contactos permitidos y márgenes. No confundir IK válida con
  recorrido libre de colisiones.
- [ ] Medir incertidumbre de localización, centro del fruto y región útil del
  recipiente frente a las holguras disponibles, con oclusión y distintas vistas.
- [ ] Comprobar coherencia de fricción, unión liberable y sensibilidad numérica;
  declarar el perfil como sintético y los parámetros aún sin calibrar.
- [ ] Mantener fixtures y datos privilegiados de ingeniería separados del
  contexto del agente autónomo.

**Aceptación:** evidencia positiva de capacidad de las primitivas con esta
geometría, márgenes medidos y fallos explicables. No se exige escribir una
política de cosecha completa como prueba. Si aparece una incompatibilidad
mecánica, se corrige y versiona antes de evaluar al agente.

## T06 — Casos y protocolo propios de cosecha completa

Responsable: diseño del experimento. Estado: pendiente.

- [ ] Definir variaciones reproducibles de ubicación/orientación del fruto,
  acceso, oclusión, recipiente y propiedades físicas dentro del perfil viable.
- [ ] Separar desarrollo, comprobación de casos nuevos (`unseen-check`) y
  evaluación final reservada. Fijar tamaños según coste y cobertura.
- [ ] Conservar dev0 como referencia histórica de integración; no reutilizar
  los resultados ni las particiones del antiguo desprendimiento.
- [ ] Registrar hashes, configuración, aleatoriedad, horizonte y renderer.
- [ ] Fijar presupuesto por modo de fallo y total, criterio de selección,
  desempate y condiciones de parada antes de ejecutar.
- [ ] Reservar casos al coordinador; cada candidato se ejecuta en todos los
  casos de desarrollo asignados.

**Aceptación:** variación física/visual comprobada, grupos disjuntos y
reproducibles. El trabajador no accede a semillas ni parámetros reservados.

## T07 — Coordinador canónico y procedencia

Responsable: integración ASPIRE. Estado: pendiente.

- [ ] Integrar registro SO-101, horizonte y entorno WSLg/GLFW en el coordinador
  existente; declarar y comprobar la concurrencia soportada.
- [ ] Implementar transiciones verificadas `pending → stage1-done → done`,
  congelación del programa y ejecución reservada por el coordinador.
- [ ] Añadir revisión independiente de procedencia: fuente, constantes,
  observaciones, prompt y traza; estados PASS/QUARANTINED con razones.
- [ ] Auditar la secuencia: observación inicial, propuesta, ejecución,
  inspección de resultados, hipótesis de corrección y selección.
- [ ] Conservar caché por hash, presupuesto consumido y reanudación. Un cambio
  de protocolo/runtime exige sesión nueva.
- [ ] Probar el ciclo del coordinador en una fixture identificada como prueba
  de infraestructura, sin presentarla como cosecha resuelta.

**Aceptación:** una entrega válida puede avanzar y una contaminada queda en
cuarentena. Reanudar no repite episodios ni llamadas al modelo. Los estados
reflejan evidencia, no solo que existan archivos de salida.

## T08 — Habilidades reutilizables y verificador independiente

Responsable: integración ASPIRE. Estado: pendiente.

- [ ] Cargar una instantánea versionada de la biblioteca aplicable, con hash.
  Puede empezar vacía.
- [ ] Recibir del agente un informe real de habilidades consultadas,
  útiles/fallidas y propuestas ligadas a evidencias.
- [ ] Eliminar el informe incondicionalmente vacío generado por el host.
- [ ] Verificar propuestas con otro agente, sin código de solución ni
  trayectorias del autor, siguiendo las reglas del flujo canónico.
- [ ] Promover/rechazar con resultados reproducibles y mantener historial.
  Reservar la evaluación final para evitar que sirva de material de aprendizaje.

**Aceptación:** una propuesta puede recorrer el mecanismo completo y ser
aceptada o rechazada con evidencia. Guardar un programa no cuenta como
habilidad verificada; ninguna promoción se afirma antes de ejecutarla.

## T09 — Desarrollo autónomo de la cosecha completa

Responsable: trabajador Codex supervisado por ASPIRE. Estado: pendiente.

- [ ] Abrir una sesión limpia, con objetivo completo, contrato corregido,
  biblioteca permitida y observaciones públicas. El trabajador no hereda
  esta auditoría con datos internos, políticas anteriores ni waypoints.
- [ ] Dejar que proponga tanto la estrategia inicial como sus correcciones.
- [ ] Ejecutar cada versión en desarrollo, inspeccionar fallos y fotogramas,
  registrar hipótesis y comprobar regresiones.
- [ ] Mantener éxito completo como métrica principal. Usar progreso seguro
  solo como diagnóstico y aplicar el desempate ya fijado.
- [ ] Exportar programa, evidencias, limitaciones e informe de habilidades.

**Aceptación:** ciclo trazable y auditado hasta selección o presupuesto agotado.
El objetivo físico solo se marca logrado si se verifica cosecha, retención,
transporte, depósito estable y retirada en el mismo episodio. Un bloqueo
demostrado vuelve a la tarea de infraestructura correspondiente.

## T10 — Comprobar generalización y cerrar la campaña

Responsable: coordinador/verificador independiente. Estado: pendiente.

- [ ] Congelar código y biblioteca seleccionados antes de casos nuevos.
- [ ] Ejecutar `unseen-check` y evaluación final conforme al protocolo.
- [ ] Informar denominadores, éxitos completos, fallos por modo, costes y
  diferencias entre desarrollo y casos reservados.
- [ ] Verificar y promover habilidades según T08 sin contaminar la medición
  final. Una nueva corrección posterior abre otra campaña y protocolo de uso
  de casos; no convierte los casos ya vistos en reservados otra vez.
- [ ] Conservar una demostración visual junto a los registros reproducibles.

**Aceptación:** resultado medido en casos no usados para ajustar el programa.
Si hay fallos, quedan descritos sin declararlo robusto ni transferible al robot
real. El cierre del proceso experimental y el éxito físico se informan por separado.

## T11 — Transferencia física, después de la fase de simulación

- [ ] Definir pinza, sensórica realmente disponible, calibración y límites del
  SO-101 que se vaya a comprar.
- [ ] Medir contacto, fricción, sujeción, daño y separación en muestras reales.
- [ ] Ajustar el perfil físico y repetir evaluación con incertidumbre.
- [ ] Preparar pruebas físicas graduales y supervisadas con el hardware.

**Aceptación:** los supuestos utilizados para pasar al robot tienen mediciones
y límites documentados. SAM3 y modelos vegetales más detallados se incorporarán
cuando una necesidad de percepción o física medida lo justifique.

## Regla para actualizar este plan

Marcar una tarea completada únicamente con sus archivos/resultados de aceptación.
Separar siempre: herramienta implementada, ejecución comprobada, éxito físico y
generalización. Mantener el historial de protocolos y resultados originales.
