# Planta FruitGym con SO-101

La tarea `so101_fruitgym_harvest` incorpora mallas y texturas reales de
[FruitGym](https://github.com/emlynw/fruit-gym), conservando el control público de
ASPIRE y el SO-101 original. Tiene una fresa madura, dos verdes, nueve hojas y un
recipiente. Es un escenario nuevo para integrar cosecha, transporte y depósito;
su existencia todavía no demuestra una política que complete la cosecha.

## Recursos y reproducción

Los recursos proceden del commit
`397abec4122f6ee5f52a3801a4cefb07a8fd6642`. El manifiesto
`configs/so101/fruitgym-assets-v1.json` fija cada archivo por SHA-256. Se descargan
solo tres mallas, cuatro texturas y los documentos de procedencia/plantillas;
no se instala FruitGym ni se cambian MuJoCo, Robosuite o sus dependencias.

Desde Ubuntu y `.venv-robosuite`:

```bash
python scripts/prepare_fruitgym_assets.py
export MUJOCO_GL=glfw
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
cap-harness run --benchmark so101 --suite so101_fruitgym_harvest \
  --task-id 0 --seed 0 \
  --program examples/robosuite/so101_fruitgym_scene_probe.py \
  --output-root outputs/so101-fruitgym-scene --max-steps 24 \
  --camera-width 800 --camera-height 600
```

El preparador admite `--source /ruta/al/checkout` para utilizar una copia local
del commit fijado. Comprueba hashes y preserva archivos modificados rechazando
su reutilización. Las copias originales quedan en `third_party/fruit_gym/`,
ignoradas por Git, junto con `ASPIRE-SOURCE.json`, README y pyproject originales.
El pyproject de origen declara MIT; no contiene un archivo LICENSE independiente
ni un inventario separado de licencias por recurso. Se conserva esa información
sin atribuirle condiciones adicionales inventadas.

## Qué se adapta

- Mallas `sb1.obj`, `calyx1.obj` y `leaf_1.obj`, texturas roja/verde, cáliz y hoja.
- Orientaciones del grupo de tres hojas de `leaves.xml`.
- Tamaño del fruto ajustado a 36 × 34 × 48 mm, más el cáliz; masa didáctica de 20 g.
- Disposición fija adaptada al alcance del SO-101. Los tallos y hojas son rígidos.
  No se importa el sistema completo de ramas elásticas de FruitGym.
- Colisión del fruto y hojas por envolventes convexas de sus mallas; cáliz visual.
  La representación de contacto sigue siendo una aproximación, sin tejido deformable.

La fresa objetivo es un cuerpo libre de MuJoCo con una unión puntual liberable.
Su movimiento relativo y carga accionan el proxy mecánico existente; esperar no
libera el fruto. Una vez separado sigue siendo el mismo cuerpo, con las mismas
mallas y velocidad física. No desaparece al agarrarlo, no se sustituye por otro
fruto en la pinza y no se recoloca al empezar transporte.

## Contrato del episodio

El evaluador exige en orden: agarre bilateral acreditado, liberación mecánica,
retención libre de 2 s, transporte de al menos 15 cm, parada de 0,25 s sobre el
recipiente, apertura, apoyo en su base y estabilidad de 1 s con la pinza abierta
y retirada al menos 8 cm. Los límites de fuerzas, penetración, deslizamiento,
colisiones y apoyos siguen activos. El apoyo del recipiente se permite durante
el depósito, no durante el transporte. La contención incluye el cáliz y usa los
vértices transformados de ambas mallas.

El informe `evaluation/so101-task.json` registra fase, sucesos de liberación,
retención, transporte y depósito, identidad del cuerpo, procedencia de recursos
y resultado físico. La etiqueta de tarea no se obtiene del diccionario `result`
del programa.

Verificación de esta integración: 10 pruebas del escenario nuevo aprobadas,
incluyendo espera más allá de 8 s, liberación con carga aplicada por el test
manteniendo cuerpo/mallas/visibilidad, orden de fases y rechazo de un depósito
sin cosecha. También pasaron las 21 pruebas existentes de transporte y
desprendimiento. La carga artificial de la prueba es solo del evaluador de tests;
no es una política de manipulación ni acredita cosecha.

El programa de ejemplo solo mantiene la postura medida durante ocho ticks para
comprobar carga, acciones e imágenes. **Se espera `program_ok=true` y
`task_success=false`.** Falta desarrollar y evaluar la política del ciclo completo.
Una ejecución real del programa produjo ese resultado. Sus evidencias y vídeos
están copiados en `outputs/local/so101-fruitgym-scene/`, y las dos vistas iniciales
en `outputs/local/so101-fruitgym-preview/`.

## Relación con el trabajo anterior

Este escenario usa `so101-fruitgym-harvest-v1`, con geometría y objetivo distintos
del protocolo `strawberry-detachment-cases-v1`. La semilla 0 del ejemplo pertenece
a esta tarea nueva; no es una ejecución reservada del protocolo anterior.
No se mezclan sus tasas de éxito ni se reutilizan sus campañas como validación.

El piloto MCP `debug_agent` abre ahora esta tarea por defecto. Puede elegirse
explícitamente con `--suite so101_fruitgym_harvest`; conserva la anterior mediante
`--suite so101_strawberry_detachment_cases`. El agente recibe el objetivo completo,
las dos cámaras, errores y progreso de retención/transporte/depósito. La suite,
el protocolo y los recursos quedan fijados por identidad de sesión; cambiar
de tarea requiere otra carpeta de resultados. Véase
[el lanzamiento con herramientas](so101-iterative-debugging.md).
La política que complete la cosecha sigue pendiente.
La unión y los contactos siguen sin calibración biológica ni validación en el
robot físico.
