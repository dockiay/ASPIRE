# Trabajo completo del SO-101 y la fresa

Esta rama reúne las cinco aportaciones anteriores y el trabajo experimental que
faltaba: entornos, agentes, evaluación, aprendizaje de habilidades, ejemplos,
configuraciones y documentación histórica. Es una integración de desarrollo;
no acredita una política que complete la cosecha FruitGym.

## Contenido

- Control SO-101, modelo oficial, sensores virtuales, geometría, IK, planificación,
  percepción RGB-D y propuestas de agarre: [guía principal](so101.md).
- Lecciones de [aproximación](so101-fresa-aproximacion.md),
  [agarre](so101-fresa-agarre.md), [retención](so101-fresa-retencion.md),
  [transporte](so101-fresa-transporte.md) y
  [desprendimiento](so101-fresa-desprendimiento.md).
- [Escena FruitGym](so101-fruitgym.md) y bancos de casos sintéticos, con
  separación de desarrollo, validación y evaluación.
- Seguimiento visual RGB-D y evidencias de movimiento, con resultados inciertos
  cuando textura, profundidad, correspondencias o vistas no son suficientes.
- Campañas, agente de depuración, controladores Codex/API, revisión de procedencia,
  validación y promoción condicionada de habilidades:
  [perfil ASPIRE](so101-iterative-debugging.md).
- Planes, auditorías e historial del trabajo en `docs/`, y versiones de la
  biblioteca y sus comprobaciones en `configs/so101/skills/`.

Los informes históricos conservan los resultados y límites de sus revisiones
originales. Sus hashes y promociones no constituyen una validación automática
de esta integración: las campañas y habilidades deben verificar de nuevo la
identidad del entorno y del código antes de reutilizar resultados.

## Preparación

Trabajar desde un checkout con el entorno Linux Robosuite ya instalado:

```bash
bash scripts/bootstrap_so101.sh
python scripts/prepare_fruitgym_assets.py
```

El modelo oficial y los recursos FruitGym permanecen fuera de los commits. Los
preparadores fijan revisiones y verifican contenido; el manifiesto de FruitGym
conserva la procedencia y la declaración de licencia del proyecto original.
No hace falta instalar el entorno FruitGym externo.

Para usar una rueda instalada con estas configuraciones experimentales, indicar
el checkout que contiene `configs/`, `docs/`, los scripts y los recursos:

```bash
export CAP_HARNESS_SO101_WORKSPACE=/absolute/path/to/ASPIRE
export CAP_HARNESS_SO101_MODEL_ROOT=/absolute/path/to/ASPIRE/third_party/so_arm100
```

El control y los proveedores ya publicados conservan su instalación anterior.
Las campañas experimentales necesitan el checkout y sus archivos de procedencia.

La escena completa selecciona SAM3 por defecto. Preparar el servicio y consultar
[la configuración de percepción](so101.md#perception-and-geometric-grasp-proposals).
La alternativa local se selecciona expresamente:

```bash
export CAP_HARNESS_SO101_SEGMENTATION=color-rgbd
python -m cap_harness.cli run \
  --benchmark so101 --suite so101_fruitgym_harvest --task-id 0 --seed 0 \
  --program examples/robosuite/so101_fruitgym_scene_probe.py \
  --output-root outputs/so101-fruitgym-probe --max-steps 24 \
  --camera-width 320 --camera-height 240
```

Este programa comprueba la escena y el registro; se espera `task_success=false`.
Las variantes con liberación por tiempo son lecciones separadas del entorno de
cosecha, cuya liberación requiere carga y movimiento relativos medidos.

Para configurar el controlador local, copiar
`configs/so101/codex-local.example.json` a `configs/so101/codex-local.json` y editar
las rutas. El archivo local, los secretos del entorno, los vídeos y las salidas
de ejecución no forman parte del código publicado. El controlador API dispone
de `configs/so101/controller-api.example.json` y lee la clave por variable de
entorno. Los ejemplos de los primeros ejercicios usan coordenadas declaradas de
su lección; no deben usarse como políticas de evaluación independiente.

## Comprobaciones

```bash
python -m pytest tests/test_so101*.py -q
```

Las pruebas con escenas, contactos o cargas preparados por el test son fixtures
de ingeniería. No demuestran agarre autónomo, cosecha ni generalización biológica.
La documentación histórica mantiene esa distinción y sus resultados fallidos.
