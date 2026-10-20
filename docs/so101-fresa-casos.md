# Casos reproducibles para aprender a desprender una fresa

La tarea `so101_strawberry_detachment_cases` selecciona un caso por semilla,
usando `configs/so101/strawberry-detachment-cases-v1.json`. Conserva el SO-101,
las cámaras, los contactos, la geometría fija y la condición de retener el fruto
libre durante 2 s de la [prueba de desprendimiento](so101-fresa-desprendimiento.md).
La lección original `so101_strawberry_detachment` conserva su caso nominal.

## Primera versión

El conjunto contiene 30 combinaciones únicas de dos parámetros:

- Fuerzas de referencia: 1,57; 2,31; 2,78; 3,53; 3,76 y 5,10 N.
- Constante de tiempo de la restricción `solref`: 0,008; 0,009; 0,010; 0,011 y 0,012 s.

Las seis fuerzas proceden de la tabla experimental citada en la guía anterior.
Las cinco constantes de tiempo son hipótesis de deformabilidad del simulador.
Las combinaciones son **casos mecánicos sintéticos**, no 30 frutos medidos ni
una distribución biológica calibrada. Compartir una fuerza entre particiones
no equivale a repetir un caso: la pareja fuerza/deformabilidad es siempre distinta.
Esta partición mide combinación de condiciones conocidas; no acredita generalización
a nuevas variedades, posiciones, materiales o familias de parámetros.

Se mantienen fijos: fruto rígido de 20 g en `(0.365, 0, 0.24)` m, geometría y
rozamiento, puerta angular provisional de 70°, tracción recta de referencia
13,9367 N, extensión mínima numérica de 0,1 mm y `solimp=(0.9,0.9,0.001,0.5,2)`.
No se cambia el robot ni se debilitan los criterios de éxito en función del caso.

## Particiones

| Uso | Semillas | Casos | Cuándo utilizarlos |
|---|---|---:|---|
| Desarrollo | 101–112 | 12 | Investigar fallos y corregir programas |
| Validación | 201–206 | 6 | Comprobar una vez el programa seleccionado, sin depurar sus fallos |
| Evaluación | 1–12 | 12 | Medir el resultado final sin usar sus fallos para corregirlo |

Cada partición incluye las seis fuerzas. Desarrollo y evaluación contienen dos
valores de deformabilidad distintos por fuerza; validación contiene uno.
Las semillas y condiciones son disjuntas. No se usa el azar global para escoger
un caso. Semillas no declaradas, como 0, 13 o 113, producen un error explícito.

La partición queda registrada; el lanzador de campañas que controlará cuándo
ejecutar cada grupo pertenece a la siguiente fase de integración. Este cambio
no ejecuta campañas de aprendizaje ni mide resultados de las particiones reservadas.

## Identidad de un intento

`evaluation/so101-task.json` añade un registro `case` con:

- Identificador, semilla y partición.
- Versión del protocolo y SHA256 del manifiesto completo.
- Fuerza de referencia y constante de tiempo aplicadas.
- SHA256 del registro del caso.

El episodio conserva además el manifiesto completo en
`evaluation/so101-case-protocol.json`, tomado al construir el entorno. Se incorpora
al inventario de artefactos del episodio y permite recomprobar su hash incluso
si el archivo de configuración del proyecto cambia después.

Los hashes usan JSON canónico: cambiar espacios o saltos de línea entre Windows
y Linux no cambia la identidad. Cambiar cualquier contenido del manifiesto sí.
Conservar el archivo versionado y su hash permite detectar resultados mezclados;
las condiciones nuevas deben publicarse deliberadamente como otra revisión.
La reproducción física exige además la misma versión del código, dependencias
y modelo del robot, que ya identifica el registro de ejecución de ASPIRE.

El entorno aplica esos parámetros antes de avanzar la física y los restaura al
reiniciar. La fuerza de rotura y la deformabilidad no se incluyen en los metadatos
de la API pública para el programa. Permanecen en la evaluación; el programa recibe
imágenes, articulaciones y contactos virtuales. Esto separa observaciones de
evaluación, sin convertir el ejecutor en una frontera de seguridad.

## Comprobarlo desde Ubuntu

Usar el entorno y variables WSLg ya configurados para las otras lecciones.

```bash
python scripts/inspect_so101_strawberry_cases.py \
  --output outputs/local/so101-strawberry-cases/protocol-inspection.json
python -m pytest -q tests/test_so101_cases.py

cap-harness run --benchmark so101 --suite so101_strawberry_detachment_cases \
  --task-id 0 --seed 101 \
  --program examples/robosuite/so101_strawberry_case_probe.py \
  --output-root outputs/local/so101-strawberry-cases --max-steps 100 \
  --camera-width 320 --camera-height 320
```

La inspección muestra las identidades de desarrollo y los intervalos reservados,
sin ejecutar episodios. La sonda mantiene el brazo y la pinza abiertos durante
0,4 s: se espera `program_ok=true` y `task_success=false`, porque comprueba la
inicialización y el registro, no intenta cosechar. Se puede repetir con 102 para
comprobar otro caso de desarrollo. Las imágenes iniciales son similares porque
esta versión varía la unión, no la posición ni el aspecto del fruto.

Las pruebas físicas ejecutan únicamente casos de desarrollo. Comparan el estado
tras restablecer el mismo caso, verifican cambios físicos entre dos casos, comprueban
los parámetros efectivos de MuJoCo y que la lección nominal conserva su significado.

## Validación realizada

El 19 de octubre de 2026 se aprobaron 20 pruebas nuevas y una selección conjunta
de 60 pruebas con regresiones. Después de incorporar la copia del manifiesto se
repitieron las pruebas de casos y grabación, y se verificaron dos ejecuciones
completas de la sonda con las semillas de desarrollo 101 y 102.

Ambas terminaron sin errores, con 8 pasos y 9 fotogramas por cámara. Aplicaron
`solref=(0.008,1)` y `(0.009,1)` respectivamente, conservando la fuerza de 2,78 N.
Sus identificadores son distintos y sus copias de manifiesto coinciden con el hash
`d3c6f34a85e767de2f51c85f9a817f455db385993859aa0e7704dfeafa6a9a5b`.

Los registros copiados a Windows están en `outputs/local/so101-strawberry-cases/`.
`probe-verification.json` recoge la auditoría de las sondas y
`protocol-inspection.json` el inventario del protocolo. Estas comprobaciones no
miden éxito de cosecha ni ejecutan las particiones reservadas.

La siguiente entrega añade el [diagnóstico de cada intento](so101-fresa-diagnostico.md),
con fases, instantes y evidencia. Sus informes se guardan fuera de la API pública
y mantienen el criterio de éxito de esta tarea.
