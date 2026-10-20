# Primer ejemplo local: Windows + WSL2 + RTX 4090

Objetivo inicial cumplido: ejecutar LIBERO-Pro y grabar un ejemplo en simulación.
Objetivo de aprendizaje actualizado: crear simulaciones con ASPIRE y Robosuite
para un futuro SO-101 que coseche fresas y las deposite en un recipiente.
Evaluaremos sujetar, girar y desprender frente a sujetar y cortar el pedúnculo.
Seguir la [guía de aprendizaje SO-101 y fresas](aprendizaje-so101-fresas.md).
Una sola ejecución por ejemplo; no es una campaña de entrenamiento ni un benchmark.

## Ejemplo verificado en este PC

Ubuntu 24.04 / WSL2, usuario `sergio`, checkout `/home/sergio/src/ASPIRE`,
entorno `.venv-libero` con Python 3.11.17, PyTorch 2.9.1 y CUDA 12.8.
Se verificó un cálculo CUDA en la RTX 4090 y renderizado MuJoCo con
`D3D12 (NVIDIA GeForce RTX 4090)` a través de WSLg.

Desde PowerShell, repetir el ejemplo que abre, cierra y vuelve a abrir la pinza:

```powershell
wsl -d Ubuntu-24.04 -- bash /mnt/d/AI/Aspire/scripts/run_wsl_example.sh
```

El lanzador usa `MUJOCO_GL=glfw`, `GALLIUM_DRIVER=d3d12` y
`MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA`, sin `PYOPENGL_PLATFORM` ni
`EGL_PLATFORM`. No se instala un controlador NVIDIA Linux.

Resultados comprobados el 17 de octubre de 2026:

- Escena inicial: `program_ok=true`, 20 pasos.
- Pinza: `program_ok=true`, 24 pasos; apertura normalizada 0,968 → 0,050 → 0,950.
- Dos vídeos MP4 verificados, 512×512, 25 fotogramas a 20 fps.
- Copia Windows del último ejemplo: `D:\AI\Aspire\outputs\local\gripper-demo`.
- Vídeo principal: `media/videos/agentview.mp4`; cámara de muñeca: `robot0_eye_in_hand.mp4`.
- 44 pruebas relacionadas aprobadas en Linux.

`task_success=false` es esperado: el ejemplo mueve la pinza, pero no coloca la lata
en la cesta. No requiere servicios de modelos, credenciales ni llamadas a un LLM.

El diagnóstico oficial pasa el reinicio de la escena y las comprobaciones de
paquetes/GPU, pero **sigue fallando su requisito específico de EGL NVIDIA**.
La configuración WSLg comprobada aquí usa GLFW/D3D12 y no satisface ese requisito.
No interpretar el diagnóstico completo como aprobado ni modificarlo para ocultarlo.

Se corrigió además un fallo del adaptador al evaluar un array de estados como
booleano (`elif not init_states`): ahora comprueba `len(init_states) == 0`.
La corrección y dos casos de regresión están tanto en el checkout Windows como
en el checkout Linux; no se han creado commits.

## Robosuite preparado y verificado (17 de octubre de 2026)

La preparación oficial se completó en Ubuntu. El script confirmó después que el
entorno ya estaba actualizado, y se verificaron sus imports y una ejecución real:
Python 3.11.17, Robosuite 1.4.0 y MuJoCo 3.3.0 en `.venv-robosuite`.

En una terminal Ubuntu, activar el entorno y el renderizado usado en este PC:

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
```

El comando `source` selecciona el Python del entorno. Las variables `export`
configuran el renderizado para esta sesión de terminal. `glxinfo -B` confirmó
renderizado acelerado D3D12 en la RTX 4090.

La prueba reutiliza el programa de pinza de LIBERO porque usa la API pública
compartida de ASPIRE; ahora se ejecuta en una tarea de Robosuite:

```bash
cap-harness run --benchmark robosuite --suite cube_lifting \
  --task-id 0 --seed 1 --program examples/libero/gripper_demo.py \
  --output-root outputs/local/robosuite-first --max-steps 200 \
  --camera-width 512 --camera-height 512
```

Resultado: `program_ok=true`, 90 pasos, apertura normalizada
0,9877 → 0,0148 → 0,9852. `task_success=false` es esperado porque el programa
no intenta levantar el cubo. Se decodificaron los dos vídeos completos, con
91 fotogramas cada uno, y se comprobó que contienen movimiento.

Copia Windows: `outputs/local/robosuite-demo`; vídeo principal:
`outputs/local/robosuite-demo/media/videos/agentview.mp4`.
El informe está en `validation-artifacts/setup/robosuite-review.json`.
La ventana visible «ASPIRE Robosuite» muestra los comandos enviados y su salida;
el registro de esa sesión está referenciado en
`validation-artifacts/setup/visible-robosuite-current.json`.

Esto verifica el entorno y control de pinza del Panda. El modelo SO-101 también
se ha importado y verificado; consultar [la guía de importación](so101-import.md).
Su integración con la API de acciones está verificada mediante el perfil `so101`:
consultar [SO-101 con ASPIRE](so101-aspire.md). Las tareas de
[aproximación a la fresa](so101-fresa-aproximacion.md) y
[contacto con ambos dedos](so101-fresa-agarre.md) ya están verificadas.
La [lección de retención](so101-fresa-retencion.md) añade fruta libre y compara
el mismo programa con contactos puntuales y con rozamiento torsional. Conserva
los resultados de ambas hipótesis sin extrapolarlos al robot real.
El [transporte y depósito](so101-fresa-transporte.md) también está implementado:
ajusta el cierre mientras lleva la fresa al recipiente y verifica que queda
apoyada y estable después de retirar la pinza.
El diagnóstico EGL NVIDIA sigue sin
cumplirse, aunque esta ejecución GLFW/D3D12 sí funciona.

## Equipo y comprobaciones iniciales (17 de octubre de 2026)

- Windows 11 Home, compilación 26200; virtualización habilitada en firmware.
- RTX 4090: 24.564 MiB de VRAM, controlador 610.88; RAM: 64 GB.
- Repositorio Windows: `D:\AI\Aspire`.
- Commit de partida: `fa00f0ef2bc1d91d594b9aa502c22133c9f538f7`.
- Entorno Windows `.venv-dev`: Python 3.11.9, instalación editable del núcleo.
- Pruebas iniciales: 42 aprobadas (adaptador con entorno falso, registro, codec y
  validación de programas). No prueban MuJoCo, CUDA, renderizado ni éxito de tareas.
- La CLI importa `resource`, disponible en Linux; no usar `.venv-dev` como runtime
  del simulador. El lock oficial también restringe la plataforma a Linux x86_64.

La primera instalación de WSL falló con `14098`: almacén de componentes de Windows
dañado al habilitar `VirtualMachinePlatform`. La reparación DISM/SFC y el reintento
de WSL se autorizaron en esta conversación. Consultar su resultado actual en:

```powershell
Get-Content D:\AI\Aspire\validation-artifacts\setup\windows-repair-status.json
Get-Content D:\AI\Aspire\validation-artifacts\setup\wsl-install-status.json
Get-Content D:\AI\Aspire\validation-artifacts\setup\windows-repair.log -Tail 25
Get-Content D:\AI\Aspire\validation-artifacts\setup\wsl-install.log -Tail 25
```

Resultado a las 14:12 (Europe/Madrid): DISM terminó correctamente (código 0) y SFC
terminó con código 0, sin infracciones de integridad. El nuevo intento de WSL
volvió a fallar con `14098 / 0x80073712`. CBS identifica un estado de compresión
inesperado en el recurso español `vmwp.exe.mui` de Hyper-V. Por tanto, WSL/Ubuntu
todavía no están operativos y ninguna simulación real de ASPIRE se ha ejecutado.

El usuario reinició Windows manualmente a las 15:22. El reintento de WSL a las
15:23 volvió a fallar con `14098 / 0x80073712`. CBS ahora registra
`MissingFileSystemResource` para el mismo recurso `vmwp.exe.mui`: el directorio
existe, pero falta ese archivo. El reinicio no resolvió el bloqueo.

El usuario completó la reparación de la versión actual de Windows y reinició
a las 16:56. El reintento de instalación WSL de las 17:00 terminó con código 0:
`VirtualMachinePlatform` se instaló correctamente y el error `14098` no reapareció.
Windows solicitó otro reinicio para aplicar esta nueva característica. El usuario
reinició a las 17:03 y `CBSRebootPending` pasó a `false`.

Ubuntu 24.04 ya está instalado y su arranque se ha verificado: kernel
`6.18.54.1-microsoft-standard-WSL2`. Dentro de Ubuntu, `nvidia-smi` detecta la
RTX 4090, 24.564 MiB y controlador 610.88. Las dependencias apt del paso 2 ya se
han instalado, junto con `libglfw3` y `mesa-utils`. El usuario normal `sergio` está
creado y el entorno Python/simulador ya está instalado. Los resultados actuales
están en «Ejemplo verificado en este PC» al principio de esta guía.

No ejecutar otra reparación mientras haya una activa. Los scripts no reinician Windows.
Si los registros solicitan reinicio, guardar el trabajo y reiniciar manualmente antes
de continuar. Si DISM falla por falta de archivos de origen, conservar los registros
y resolver ese error antes de repetir la instalación.

## 1. Terminar WSL y crear el usuario de Ubuntu

Después de que la instalación termine correctamente y de cualquier reinicio requerido:

```powershell
wsl --list --verbose
wsl -d Ubuntu-24.04
```

Crear el usuario y la contraseña de Linux en la terminal interactiva cuando Ubuntu
lo solicite. Si Ubuntu todavía no está instalado, ejecutar en PowerShell como
administrador el script `D:\AI\Aspire\scripts\install_wsl.ps1`.

## 2. Preparar Ubuntu y el checkout Linux

Ejecutar dentro de Ubuntu. Usar el sistema de archivos Linux para el código y los
entornos: el checkout Windows usa CRLF en los scripts Bash y no se debe ejecutar
directamente como si fuera el checkout Linux.

```bash
sudo apt-get update
sudo apt-get install -y git curl build-essential python3 libegl1 libgl1 libglib2.0-0 libopengl0 libosmesa6
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/aspire-install-uv.sh
sh /tmp/aspire-install-uv.sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.11
mkdir -p "$HOME/src"
git -c core.autocrlf=false clone --branch main https://github.com/NVlabs/ASPIRE.git "$HOME/src/ASPIRE"
cd "$HOME/src/ASPIRE"
git checkout --detach fa00f0ef2bc1d91d594b9aa502c22133c9f538f7
cp /mnt/d/AI/Aspire/examples/libero/scene_smoke.py examples/libero/scene_smoke.py
cp /mnt/d/AI/Aspire/examples/libero/gripper_demo.py examples/libero/gripper_demo.py
cp /mnt/d/AI/Aspire/src/cap_harness/libero/adapter.py src/cap_harness/libero/adapter.py
sed -i 's/\r$//' src/cap_harness/libero/adapter.py
export CAP_HARNESS_PYTHON="$(uv python find 3.11)"
export CAP_HARNESS_PROFILE=rtx4090
export CAP_HARNESS_CUROBO_GPU=0
nvidia-smi
```

WSL utiliza el controlador NVIDIA de Windows. No instalar un controlador gráfico
NVIDIA Linux dentro de WSL. Que CUDA funcione no acredita que EGL funcione: este
proyecto comprueba también el proveedor NVIDIA EGL, que puede faltar en WSL.
El procedimiento EGL siguiente se conserva como referencia del proyecto: falla
su requisito de proveedor NVIDIA en este WSL. Para ejecutar aquí, usar el
lanzador GLFW/D3D12 verificado al principio de esta guía.

## 3. Instalar solo el simulador y comprobar el renderizado

```bash
scripts/bootstrap_libero.sh --python "$CAP_HARNESS_PYTHON"
source .venv-libero/bin/activate
export LIBERO_CONFIG_PATH="$PWD/.libero"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl EGL_PLATFORM=device
export CUDA_VISIBLE_DEVICES=0 MUJOCO_EGL_DEVICE_ID=0
cap-harness doctor --skip-services --reset \
  --reset-suite libero_object_swap --reset-task-id 0 --seed 1 \
  --output validation-artifacts/local/doctor-reset.json
```

El bootstrap usa los submódulos y el lock del repositorio. No actualizar paquetes
del runtime individualmente para resolver errores. El primer bootstrap descarga
dependencias grandes; todavía no se ha medido su duración en este equipo.

## 4. Grabar la escena sin credenciales ni servicios de modelos

```bash
cap-harness run --benchmark libero-pro --suite libero_object_swap \
  --task-id 0 --seed 1 --init-mode saved \
  --program examples/libero/scene_smoke.py \
  --output-root outputs/local/scene-smoke --max-steps 40 \
  --camera-width 512 --camera-height 512
```

El programa mantiene la postura inicial durante 20 ticks (un segundo simulado,
no un segundo de tiempo real) y permite comprobar las cámaras y la grabación.
Esperar `program_ok=true` en `outcome.json`; `task_success=false` es normal porque
este programa no intenta colocar la lata. La prueba ya pasó con GLFW/D3D12.

Si WSL no ofrece el dispositivo EGL necesario, una prueba alternativa para esta
escena es el renderizado por CPU de MuJoCo (OSMesa). `libosmesa6` se instala en
el paso 2. Es una alternativa experimental para esta combinación de ASPIRE y WSL,
todavía sin probar aquí:

```bash
MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
  cap-harness run --benchmark libero-pro --suite libero_object_swap \
  --task-id 0 --seed 1 --init-mode saved \
  --program examples/libero/scene_smoke.py \
  --output-root outputs/local/scene-smoke-osmesa --max-steps 40 \
  --camera-width 256 --camera-height 256
```

El `doctor` oficial seguirá exigiendo EGL NVIDIA; esta alternativa no convierte
ese diagnóstico en aprobado. Conservar el diagnóstico y verificar la ejecución
y el vídeo por separado. No modificar el diagnóstico para ocultar el fallo.

## 5. Referencia opcional: manipulación con SAM3 y PyRoki

Esta ruta para manipular una lata queda como referencia. No es un requisito para
las primeras lecciones de control y creación de escenas del proyecto de fresas.

Solicitar primero acceso a [SAM3 en Hugging Face](https://huggingface.co/facebook/sam3), según
[host-setup.md](host-setup.md). No pegar tokens en el chat ni guardarlos en el repo.
El ejemplo preescrito no requiere una clave de API de un modelo de lenguaje.

```bash
scripts/bootstrap_sam3.sh --profile rtx4090
scripts/bootstrap_pyroki.sh --profile rtx4090
uvx --from huggingface_hub hf auth login
scripts/supervise_services.sh --profile rtx4090 --providers sam3,pyroki
```

Dejar esa terminal abierta. SAM3 atiende en `127.0.0.1:8114` y PyRoki en
`127.0.0.1:8116`. El supervisor no acredita por sí solo que se haya cargado el
modelo: la primera solicitud de SAM3 puede descargar pesos o fallar por acceso.
El programa `object_swap_seed1.py` utiliza percepción e IK; no llama a
Contact-GraspNet ni a cuRobo. No son necesarios para este ejemplo concreto.

En otra terminal Ubuntu, desde el checkout Linux:

```bash
cd "$HOME/src/ASPIRE"
source .venv-libero/bin/activate
export LIBERO_CONFIG_PATH="$PWD/.libero"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl EGL_PLATFORM=device
export CUDA_VISIBLE_DEVICES=0 MUJOCO_EGL_DEVICE_ID=0
cap-harness doctor --providers sam3,pyroki --reset \
  --reset-suite libero_object_swap --reset-task-id 0 --seed 1 \
  --output validation-artifacts/local/doctor-providers.json
cap-harness run --benchmark libero-pro --suite libero_object_swap \
  --task-id 0 --seed 1 --init-mode saved \
  --program examples/libero/object_swap_seed1.py \
  --output-root outputs/local/object-swap --max-steps 2000 \
  --camera-width 800 --camera-height 512
```

Confirmar `program_ok=true` y `task_success=true` en el `outcome.json` generado.
Conservar los vídeos de `media/videos/`, trazas y `run.json`. El resultado de este
ejemplo en este equipo todavía no está verificado. No extrapolar una semilla a
una tasa de éxito general. Instalación, primera descarga de pesos y ejecución
tienen duraciones distintas; no hay una medida local todavía.

## Referencias

- [Instalación y opciones WSL](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
- [Reparación DISM y SFC](https://support.microsoft.com/es-es/windows/experience/backup-recovery/using-system-file-checker-in-windows)
- [CUDA en WSL: limitaciones y controladores](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
- [Microsoft: selección de GPU en WSLg](https://github.com/microsoft/wslg/wiki/GPU-selection-in-WSLg)
- [Mesa: controlador D3D12](https://docs.mesa3d.org/drivers/d3d12.html)
- [MuJoCo: EGL y renderizado por CPU con OSMesa](https://mujoco.readthedocs.io/en/3.3.7/programming.html)
- [Guía oficial de LIBERO-Pro](libero-pro.md)
- [Ejemplos oficiales](../examples/README.md)
