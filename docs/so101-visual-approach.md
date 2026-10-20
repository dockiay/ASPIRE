# Localización y aproximación visual con pinza abierta

El SO-101 dispone de dos primitivas públicas nuevas. No leen el estado nativo del
fruto, los puntos preparados en lecciones anteriores ni la geometría de la planta.

- `so101.localize_ripe_fruit()` segmenta rojo en ambas imágenes públicas RGB-D,
  descarta candidatos por tamaño observado y profundidad espuria de bordes,
  transforma los puntos con la calibración pública y ajusta una esfera a las dos
  superficies. Devuelve centro aproximado, ajuste, cámaras y tiempo. Rechaza
  ausencia, ambigüedad o vistas incoherentes. No estima una pose 6D completa.
- `so101.plan_open_approach(point_m, clearance_m=0.065)` calcula el objetivo de
  aproximación a partir de ese centro durante la ejecución. Separa el TCP 65 mm
  hacia la base en el plano horizontal, orienta el eje X de la herramienta hacia
  el fruto y conserva aproximadamente el giro de muñeca. Resuelve cinemática con
  el modelo oficial del robot, respetando límites y comprobando el camino nominal
  contra el propio robot y el plano de trabajo. No mueve el robot.

El programa público ejecuta los puntos calculados con la pinza abierta, se
estabiliza y mantiene la postura. Su ejemplo está en
`examples/robosuite/so101_visual_open_approach.py`. No contiene coordenadas del
fruto ni puntos articulares de la escena. Los números fijos son filtros de
percepción y tolerancias/holguras de ingeniería, no datos copiados de exploración.

## Ejecutarlo mediante Codex y las herramientas MCP

Desde Ubuntu con `.venv-robosuite` y la configuración gráfica habitual:

```bash
python -m cap_harness.so101.debug_agent \
  --output outputs/so101-visual-approach-agent \
  --suite so101_fruitgym_harvest --approach-only \
  --max-programs 2 --max-calls 32 --max-steps 240 \
  --timeout-s 90 --agent-timeout-s 420 --width 640 --height 480
```

`--approach-only` fija la etapa de trabajo: localizar y aproximarse, sin cerrar,
agarrar, desprender o transportar. Es incompatible con `--smoke`, que introduce
un error de API deliberado. Codex escribe el programa sin recibir el ejemplo
anterior y lo ejecuta con las mismas herramientas controladas. Debe inspeccionar
los resultados y el último fotograma de ambas cámaras antes de cerrar.

`inspect_results` añade un informe público acotado del propio programa con el
ajuste visual y el plan. Se etiqueta como autoinforme y no establece éxito físico.
El evaluador de cosecha conserva su criterio completo; terminar esta aproximación
deja `task_success=false` y `grasp_not_qualified`, como corresponde a esta etapa.

## Verificación y límites

Las pruebas comprueban ajuste métrico en imágenes sintéticas desplazadas,
rechazo de ambigüedad, sincronización, datos de profundidad de fondo en bordes,
seguimiento de un fruto desplazado en la escena nativa, planificación sin mover
el robot y ejecución pública con pinza abierta, sin contactos ni liberación.

Resultado registrado con Codex y MuJoCo reales: un programa generado por el
agente, un episodio, 67 ticks y ocho llamadas MCP. Error visual respecto al
centro nativo usado solo para verificación posterior: 5,22 mm. Distancia medida
del TCP al centro del fruto al terminar: 63,62 mm. Error final del TCP respecto
al objetivo calculado: 0,35 mm. Pinza abierta, ningún contacto prohibido, sin
agarre ni desprendimiento. Se verificaron los últimos fotogramas de ambas cámaras
y la reanudación sin llamadas al modelo ni episodios adicionales.

Pasaron 37 pruebas de visión, aproximación, adaptador y herramientas: nueve
nuevas y 28 regresiones. También pasaron 74 pruebas de API, registro y runtime.
Las evidencias están en `outputs/local/so101-visual-approach-agent/`; la
verificación independiente está en `approach-verification.json` dentro de esa
carpeta. Las vistas finales están en
`outputs/local/so101-visual-approach-agentview.png` y
`outputs/local/so101-visual-approach-sideview.png`.

La detección por color es una primera solución para la fresa roja visible de
esta escena. No es un detector semántico general ni demuestra robustez frente a
oclusiones, iluminación distinta u otros objetos rojos. No necesita SAM3; su
integración queda para más adelante. El centro se aproxima con una esfera,
aunque la malla del fruto no es esférica.

El plan comprueba colisiones propias y plano de trabajo; no certifica un camino
libre entre obstáculos de una planta arbitraria. Las colisiones de la ejecución
real se verifican con el monitor físico del banco de pruebas. El modelo del
robot usado para cinemática no contiene planta ni fruto y solo cambia su propio
estado virtual durante el cálculo.

La unión, sensores táctiles y física vegetal siguen sin calibración real. Esta
etapa no recoge el fruto y la auditoría general de procedencia permanece
`PENDING`. Las comprobaciones de posición interna del fruto solo se usan después
de ejecutar o en tests, fuera del programa y del feedback del agente.
