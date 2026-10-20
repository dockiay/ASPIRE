# SO-101: modelo importado y verificado

El 17 de octubre de 2026 se importÃ³ el modelo oficial del SO-101 follower en una
escena construida con `MujocoWorldBase` de Robosuite y compilada con MuJoCo 3.3.0.
Se comprobaron los cinco ejes del brazo y el motor de la pinza mediante movimientos
simulados y mediciones. DespuÃ©s se aÃ±adiÃ³ el adaptador de cinco ejes para
`cap-harness run`: consultar [SO-101 controlado desde ASPIRE](so101-aspire.md).
La escena de fresas sigue pendiente.

## QuÃ© se ha importado

- Origen: [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100).
- RevisiÃ³n fijada: `a758567c3978dfeefe282ede0500085a48fe8f78`.
- Archivo: `Simulation/SO101/so101_new_calib.xml`, con 13 geometrÃ­as de malla.
- Se conservan el URDF, los originales del fabricante y su licencia Apache-2.0.
- UbicaciÃ³n Ubuntu: `/home/sergio/src/ASPIRE/third_party/so_arm100`.
- La configuraciÃ³n reproducible estÃ¡ en [src/cap_harness/configs/robots/so101.json](../src/cap_harness/configs/robots/so101.json).

El **MJCF/XML** describe los cuerpos, articulaciones, geometrÃ­as y motores que
MuJoCo simula. Las mallas STL proporcionan las formas. El URDF tambiÃ©n se descarga
para una futura integraciÃ³n de cinemÃ¡tica; esta prueba utiliza el MJCF.

El modelo incluye clases de parÃ¡metros anidadas que el cargador XML de Robosuite
1.4 no expande directamente. [so101_model.py](../src/cap_harness/robosuite/so101_model.py)
usa `MjSpec.attach` de MuJoCo para incorporarlo al mundo de Robosuite conservando
esos parÃ¡metros. Resuelve las rutas de las mallas para poder guardar y reabrir la
escena desde otra carpeta. Los originales del fabricante permanecen sin cambios.

## Repetir los pasos en la terminal Ubuntu

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
bash scripts/bootstrap_so101.sh
```

El Ãºltimo comando descarga Ãºnicamente la parte del repositorio que necesitamos y
selecciona la revisiÃ³n fijada. Si ya existe, verifica su origen y rechaza cambios
locales antes de intentar actualizarla.

Para mover cada eje, probar la pinza y grabar un vÃ­deo:

```bash
python examples/robosuite/so101_model_smoke.py
```

Este ejemplo es un **programa de comprobaciÃ³n del modelo**, ejecutado con Python
en el host de simulaciÃ³n. Utiliza directamente los motores del modelo. Para
ejecutar acciones pÃºblicas del framework se usa ahora el perfil `so101` y
`examples/robosuite/so101_aspire_control.py`, como explica la guÃ­a enlazada arriba.

Para abrir el visor 3D y girar la cÃ¡mara con el ratÃ³n:

```bash
python examples/robosuite/so101_model_smoke.py --view
```

El visor muestra una postura estÃ¡tica y permite inspeccionar la geometrÃ­a. Cerrar
esa ventana termina el visor. La terminal Â«ASPIRE RobosuiteÂ» puede mantenerse
abierta para continuar las lecciones.

## Evidencia de la importaciÃ³n

Las pruebas `tests/test_so101_model.py` pasan en `.venv-robosuite` y comprueban:

1. ConservaciÃ³n de lÃ­mites y ejes articulares, masas, inercias, amortiguamiento,
   fricciÃ³n, parÃ¡metros de motores y propiedades de contacto del modelo original.
2. Guardado y reapertura de la escena exportada con sus mallas.

AdemÃ¡s, el ejemplo completÃ³ doce fases: movimiento y retorno de cada uno de los
cinco ejes, mÃ¡s cierre y apertura de la pinza. La tolerancia fue 0,025 rad; el mayor
error final observado fue aproximadamente 0,00060 rad. Es una mediciÃ³n del modelo
simulado, no una especificaciÃ³n de precisiÃ³n del robot fÃ­sico.

La ejecuciÃ³n generÃ³ 12 segundos simulados y 240 fotogramas a 20 fps.
Su copia Windows estÃ¡ en `D:\AI\Aspire\outputs\local\so101-import-demo`:

- `preview.png`: primera imagen.
- `motion.mp4`: movimientos de los cinco ejes y la pinza.
- `scene.xml`: escena exportada, con rutas a las mallas del checkout Ubuntu.
- `report.json`: revisiÃ³n, hash del XML original, lÃ­mites, objetivos y mediciones.

## Detalles que necesitaremos despuÃ©s

La pinza usa un Ã¡ngulo nativo en radianes. El fabricante advierte que su modelo
todavÃ­a no implementa directamente el mapeo de apertura 0â€“100 de LeRobot. TambiÃ©n
retirÃ³ algunas colisiones de la base; habrÃ¡ que revisar esa representaciÃ³n antes
de evaluar colisiones alrededor de una planta. VÃ©ase el
[README oficial](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md).

Los contratos y el adaptador de cinco ejes ya estÃ¡n integrados y se verificÃ³ un
primer programa pÃºblico mediante el perfil de simulaciÃ³n `so101`. El informe de
la primera importaciÃ³n conserva el estado histÃ³rico de aquella comprobaciÃ³n;
la ejecuciÃ³n posterior de ASPIRE tiene su propio informe y vÃ­deos.
DespuÃ©s aÃ±adiremos una fresa y un pedÃºnculo simplificados para aprender
aproximaciÃ³n, agarre y desprendimiento.
