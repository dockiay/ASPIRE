# Tareas para aprender a cosechar una fresa con ASPIRE

Objetivo inicial: un programa que desprenda y conserve una sola fresa en varios
casos reproducibles. La escena, el robot, los registros y el evaluador básicos
ya existen. El ciclo de mejora con Codex está conectado; las campañas completas
de mejora y la calibración biológica siguen pendientes.

Última actualización: 19 de octubre de 2026.

## Estado y siguiente tarea

| Fase | Estado |
|---|---|
| 1. Casos reproducibles | Completada |
| 2. Evaluación y diagnóstico | Completada |
| 3. Lanzador de campañas | Completada |
| 4. Controlador Codex y mejora | Aproximación visual verificada; agarre pendiente |
| 5. Biblioteca de habilidades | Pendiente |
| 6. Cosecha, transporte y depósito en un episodio | Pendiente |
| 7. Posiciones variables y visión | Visión básica lista; variaciones posteriores |
| 8. Calibración y robot real | Posterior |

**Siguiente tarea: alinear y cerrar la pinza para acreditar un agarre bilateral.**
La localización RGB-D y la aproximación abierta ya funcionan en la escena
FruitGym. Codex generó y ejecutó un programa desde las APIs públicas: terminó
a 63,62 mm del centro del fruto, con la pinza abierta y sin contactos prohibidos.
El error visual medido después del episodio fue 5,22 mm. Véase
[la aproximación visual](so101-visual-approach.md). Estos resultados son de un
caso fijo; todavía no acreditan agarre, cosecha ni generalización.

El perfil `iterative-debugging` adaptado añade
exploración visual, ejecución, consulta de diagnósticos y revisión de fotogramas
mediante seis herramientas MCP. Su guía está en
[Codex con herramientas](so101-iterative-debugging.md).
El agente abre ya por defecto el escenario de nuestra planta y recipiente;
`--suite so101_strawberry_detachment_cases` conserva la prueba anterior.

Los seis episodios anteriores conservan valor como referencia histórica de
ingeniería: inicial 1/2 y dos correcciones 0/2. Sus trayectorias preparadas offline
no se entregan al nuevo agente ni acreditan una solución generada desde sensores
públicos. No se ha completado desarrollo ni ejecutado validación o evaluación.

## 1. Casos reproducibles — completada

- [x] Crear un conjunto versionado de condiciones de fuerza y deformabilidad.
- [x] Separar desarrollo, validación y evaluación sin casos repetidos.
- [x] Hacer que la semilla seleccione un caso explícito y estable.
- [x] Registrar identidad, versión y parámetros físicos en las evidencias.
- [x] Mantener los parámetros fuera de los metadatos públicos y conservar la lección original.
- [x] Verificar repetibilidad, diferencias entre casos y rechazo de semillas desconocidas.
- [x] Ejecutar una comprobación de integración con casos de desarrollo.

Entrega: perfil `so101_strawberry_detachment_cases`, manifiesto versionado,
pruebas e instrucciones. La primera versión mantiene posición, tamaño, masa y
rozamiento fijos. Varía fuerza de separación y deformabilidad numérica de la unión.
Sus combinaciones son sintéticas, no mediciones de nuevos frutos.

Resultado: 12 casos de desarrollo, 6 de validación y 12 de evaluación, sin parejas
de parámetros repetidas. Las 20 pruebas nuevas pasan; la selección conjunta con
regresiones aprobó 60 pruebas. Tras añadir la copia del manifiesto al episodio
se repitieron las pruebas de casos y grabación, y las dos sondas registradas.
Los casos reservados no se ejecutaron. Véase [cómo usar los casos](so101-fresa-casos.md).

## 2. Evaluación y diagnóstico — completada

- [x] Fijar el contrato de éxito: separar y retener libre al menos 2 s.
- [x] Emitir motivos estructurados: sin agarre, sin separación, contacto inestable,
  caída, apoyo indebido, colisión o límites excedidos.
- [x] Asociar cada fallo a su instante, fase y evidencia visual o numérica.
- [x] Verificar que la API pública no exponga el informe ni la recompensa privilegiada.
- [x] Mantener el mismo criterio al comparar estrategias y parámetros físicos.

Entrega: [diagnóstico estructurado](so101-fresa-diagnostico.md), historial de
eventos físicos y resumen que separa errores de ejecución de resultados de tarea.
Se aprobaron 11 pruebas nuevas; una selección conjunta de regresiones aprobó 68
pruebas antes de las tres últimas pruebas adicionales. Se repitieron las 11
pruebas del diagnóstico tras los últimos ajustes. Se auditaron dos episodios
grabados, sus informes, hashes y referencias de vídeo. Los criterios de éxito
se conservan y los casos reservados siguen sin ejecutarse.

## 3. Lanzador de campañas — completada

- [x] Adaptar los procedimientos existentes al perfil `so101` y a WSLg/GLFW.
- [x] Ejecutar listas de casos con límites de pasos, tiempo e intentos.
- [x] Guardar código, manifiesto de casos, resultados e identidad de cada versión.
- [x] Permitir reanudar sin mezclar resultados de distintas versiones.
- [x] Reservar la evaluación final; no usar sus fallos para corregir el programa.

Entrega: [lanzador de campañas](so101-fresa-campanas.md), comparaciones, copias
del código y protocolo, auditoría de episodios y selección congelada para las
particiones reservadas. No llama al LLM ni mejora programas automáticamente.

Resultado: 20 pruebas del lanzador aprobadas. Una selección conjunta de casos,
diagnósticos y lanzador aprobó 50 pruebas antes del último refuerzo de cierre;
después se repitieron las 20 del lanzador. La demostración ejecutó dos programas
en los casos de desarrollo 101 y 102: la sonda obtuvo 0/2 y el programa actual
de desprendimiento 1/2. En 101 se registró contacto fruto-pedúnculo al liberarse;
102 cumplió desprendimiento y retención. Son dos casos de comprobación, no una
estimación de robustez ni una campaña de aprendizaje.

Se verificó la pausa tras un episodio, la continuación hasta cuatro y una nueva
invocación sin intentos adicionales, conservando hashes. También se comprobó el
rechazo de una campaña creada con código anterior. Los fallos físicos no se
repitieron; validación y evaluación siguen sin ejecutarse.

## 4. Mejora con Codex — ciclo conectado; campaña completa pendiente

### 4.1. Conectar y verificar el controlador — completada

- [x] Preparar contexto del robot, acciones disponibles y objetivo de la tarea.
- [x] Conectar Codex CLI con la sesión de ChatGPT, sin configurar claves de API.
- [x] Usar registros de desarrollo para proponer y comparar correcciones.
- [x] Ejecutar el ciclo programa → simulación → diagnóstico → corrección de Codex.
- [x] Fijar presupuesto de intentos y criterio de selección antes de empezar.
- [x] Conservar la mejor versión cuando una propuesta empeora los resultados.
- [x] Verificar pausa y reanudación sin duplicar propuestas ni episodios.

Entrega: [Codex como controlador](so101-fresa-codex.md), contexto de API pública,
propuestas JSON, ejecución por campañas y feedback de desarrollo para la siguiente
corrección. Usa Codex CLI con la sesión guardada de ChatGPT, sin configurar claves
de API. El modelo propone programas; ASPIRE ejecuta y verifica la física.

Se aprobaron 66 pruebas conjuntas: 15 del ciclo y del worker Codex, 20 del lanzador,
20 de casos y 11 de diagnósticos. La primera conexión real con Codex produjo una
respuesta estructurada sin invocar herramientas. La demostración de aprendizaje
se limita a desarrollo 101 y 102, con dos propuestas máximas. No es una campaña
completa de los 12 casos ni una evaluación final; las particiones reservadas
continúan separadas y no se ejecutan desde este ciclo.

Resultado de la demostración real: seis episodios, programa inicial 1/2, primera
propuesta Codex 0/2 y segunda 0/2. La primera provocó caídas; la segunda se
interrumpió por falta de precarga bilateral, con el fruto aún unido. Se conservó
la inicial como mejor versión. Se verificaron propuestas, episodios, pausa y
reanudación sin repetir llamadas ni ensayos. El ciclo está operativo; mejorar la
estrategia, completar desarrollo y congelar/evaluar el candidato siguen pendientes.

### 4.1.b. Adaptar `iterative-debugging` a un agente con herramientas — completada

- [x] Crear un perfil propio SO-101 conservando el flujo genérico de ASPIRE.
- [x] Permitir describir, explorar, ejecutar, inspeccionar, ver fotogramas y cerrar.
- [x] Entregar imágenes reales de ambas cámaras, diagnósticos filtrados y fuerzas finales.
- [x] Acotar programas, llamadas, casos, pasos, tiempo y selección del candidato.
- [x] Conservar programas y evidencias auditadas, sin ofrecer acceso a rutas arbitrarias.
- [x] Verificar el ciclo con Codex real y simulación nativa.
- [x] Reanudar sin nuevas llamadas al modelo ni nuevos episodios; auditar hashes.

La prueba de integración genera dos programas sin suministrar trayectorias
anteriores. El primero contiene un error de API deliberado y falla en 101/102.
Codex consulta el `NameError`, corrige la llamada y mantiene la postura medida
durante ocho ticks: ejecución correcta 2/2, cosecha 0/2. Son cuatro episodios y
ocho llamadas MCP, con un único lanzamiento del agente. Esto demuestra reparación
de código y circulación de evidencias, no mejora aprendida de la cosecha.
Se aprobaron 13 pruebas del perfil nuevo; las 66 regresiones existentes también
pasaron en la selección conjunta previa a las últimas cuatro pruebas del perfil.

El cierre registra un candidato experimental. La auditoría de procedencia sigue
`PENDING`; no certifica Stage 1, no promueve habilidades y no ejecuta casos
reservados. Las referencias históricas de 4.1 conservan su contexto offline.

Conexión al episodio completo: el mismo flujo admite ahora
`so101_fruitgym_harvest`, con protocolo propio y un caso fijo de desarrollo 0.
Se verificó con Codex real: ocho llamadas MCP, dos programas y dos episodios,
el segundo con ejecución correcta y cosecha no conseguida (prueba de API).
La reanudación no repitió el modelo ni los episodios. Pasaron 10 pruebas nuevas
y las 58 regresiones seleccionadas. No es una campaña de robustez.

### 4.2. Estrategia generada por ASPIRE — dirección actual

Decisión del operador: dejar de implementar manualmente las siguientes fases.
Las lecciones anteriores son pruebas de ingeniería. El trabajador de ASPIRE
recibe la cosecha completa y decide programas/correcciones con herramientas
generales. La demostración guiada de aproximación no acredita estrategia autónoma.

- [x] Habilitar la API compartida de percepción, IK, movimiento y pinza para SO-101.
- [x] Retirar la receta de fases del encargo predeterminado y restringir el
  solucionador de aproximación a su demostración explícita.
- [x] Retirar objetivos geométricos heredados de los metadatos públicos de la planta.
- [x] Exportar programa elegido, análisis y evidencia de desarrollo con hashes.
- [x] Ejecutar y revisar el primer ciclo autónomo sobre la cosecha completa:
  `outputs/so101-autonomous-harvest-v2`, cuatro programas propios, cuatro episodios
  válidos y 19 llamadas MCP. Ninguno completó la cosecha; el primer candidato se
  conservó por la regla fijada de puntuación/orden. Fuerza excesiva, liberación
  sin agarre y colisión motivaron correcciones del agente, sin recetas del host.
- [ ] Definir casos de desarrollo, unseen-check y held-out propios de la planta
  para completar el protocolo de campaña y verificar habilidades transferibles.

- [x] **4.2.1. Generar una política de aproximación desde observaciones públicas**:
  segmentación roja y profundidad de ambas cámaras, centro aproximado, cinemática
  calculada con el modelo del robot y aproximación con pinza abierta. Verificado
  con Codex real, sin copiar coordenadas observadas ni trayectorias offline.
- [ ] **4.2.2. Resolver el agarre desde el programa del agente**: hipótesis y
  correcciones decididas por ASPIRE a partir de las observaciones y resultados;
  no escribir una fase de agarre manual como próximo trabajo del desarrollador.
- [x] Incluir fuerzas finales por dedo y apertura en el feedback del nuevo agente,
  además de los máximos; conservar medidas ocultas fuera de sus herramientas.
- [ ] Formular una hipótesis concreta de corrección del agarre o movimiento,
  indicando qué medición confirmaría la mejora.
- [ ] Abrir una campaña nueva con presupuesto y regla de selección fijados;
  la demostración anterior agotó sus dos propuestas y debe conservarse intacta.
- [ ] Conseguir cosecha completa en la escena FruitGym, caso fijo 0, con un
  programa derivado de sensores públicos. Si se retoma la tarea anterior,
  evaluar 101 y 102 dentro de su propio protocolo, sin mezclar resultados.
- [ ] Definir variaciones y particiones propias para la escena nueva antes de
  evaluar robustez. Los 12 casos anteriores corresponden a la tarea de
  desprendimiento y no se transfieren automáticamente a esta planta.
- [ ] Añadir búsqueda de variantes solo si los resultados de la depuración
  iterativa justifican ampliar ese método y su presupuesto.

Los criterios y parámetros del protocolo se mantienen al comparar programas.
Si el análisis identifica un problema del modelo físico o del evaluador que
requiera corregirlos, documentarlo y versionar un protocolo nuevo antes de
repetir las comparaciones; conservar las evidencias del protocolo anterior.

### 4.3. Congelar y evaluar el candidato — pendiente

- [ ] Auditar independientemente la procedencia de objetivos y constantes;
  superar validación AST no certifica cumplimiento. El piloto queda `PENDING`.
- [ ] Completar la campaña de desarrollo de la versión elegida y congelar su código.
- [ ] Definir y ejecutar una comprobación unseen-check propia de la planta,
  una vez y sin usar sus fallos para depurar el mismo candidato.
- [ ] Fijar el candidato final y el criterio de aceptación antes de la evaluación.
- [ ] Ejecutar una evaluación final en la partición reservada propia de la planta.
- [ ] Informar éxitos, fallos y límites de generalización sin usar esos fallos
  finales para corregir el programa dentro del mismo protocolo de evaluación.

Los seis casos de validación y doce de evaluación del experimento anterior
pertenecen a `so101_strawberry_detachment_cases`. No son particiones de la
cosecha completa FruitGym y no deben reutilizarse como si lo fueran.

## 5. Biblioteca de habilidades — pendiente

- [ ] Documentar únicamente patrones respaldados por resultados reproducibles.
- [ ] Indicar condiciones de uso, sensores requeridos y límites de cada habilidad.
- [ ] Verificar que otro intento pueda reconstruir la solución desde la habilidad.
- [ ] Comprobar reutilización sin copiar una trayectoria específica como regla general.

## 6. Ciclo completo — pendiente

- [x] Disponer de ejercicios separados de desprendimiento/retención y de
  transporte/depósito; su existencia no demuestra la secuencia completa.
- [x] Crear el escenario `so101_fruitgym_harvest` con recursos FruitGym fijados
  por hash, la misma fresa física y el recipiente. Véase [la integración](so101-fruitgym.md).
- [x] Definir el evaluador continuo de agarre, liberación por carga, retención,
  transporte y depósito ordenados, conservando las tareas anteriores.
- [x] Conectar las seis herramientas del agente a ese escenario y sus diagnósticos,
  con selección de tarea, protocolo y recursos fijados por sesión; comprobarlo
  con Codex y simulación reales sin mezclar los casos anteriores.
- [ ] Generar y ejecutar una política que complete desprendimiento, retención,
  transporte y depósito en el mismo episodio de la planta FruitGym.
- [x] Conservar el mismo fruto y su estado físico al desprenderse, sin borrado ni
  sustitución; verificado en el escenario nuevo. Validar la política completa sigue pendiente.
- [ ] Verificar colocación estable y retirada de la pinza, además de separación.
- [ ] Evaluar recuperación de fallos sin borrar lo ocurrido ni reiniciar a escondidas.

## 7. Posiciones variables y visión — posterior

- [ ] Añadir variación reproducible de posición, orientación y obstáculos.
- [ ] Adaptar movimientos cartesianos/cinemática inversa a los cinco ejes del SO-101.
- [ ] Integrar SAM3 con profundidad y transformación al sistema de coordenadas del robot.
- [ ] Evaluar localización, agarre y desprendimiento por separado.

## 8. Calibración y futuro robot real — posterior

- [ ] Medir fuerza, desplazamiento, ángulo y punto de separación en frutos reales.
- [ ] Medir deformabilidad del pedúnculo y contacto de las futuras yemas.
- [ ] Evaluar daños y magulladuras; el límite didáctico de fuerza no los predice.
- [ ] Elegir cómo observar contacto y separación con los sensores disponibles.
- [ ] Validar de nuevo las habilidades bajo la física calibrada antes de transferirlas.
