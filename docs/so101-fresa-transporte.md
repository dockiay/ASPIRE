# Cuarta tarea: transportar la fresa y depositarla

El SO-101 toma la fresa, la retiene después de liberarse la fijación a los 8 s,
la retira de la planta y la lleva sobre un recipiente. Después baja, abre,
retira la pinza y deja el fruto entero dentro, apoyado y estable. Esta lección
mantiene el fruto rígido de 20 g y el contacto torsional de la lección anterior.
La separación biológica del pedúnculo sigue pendiente de otro experimento.

## Ejecutar en la terminal Ubuntu

```bash
cd ~/src/ASPIRE
source .venv-robosuite/bin/activate
export MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID
cap-harness run --benchmark so101 --suite so101_strawberry_transport \
  --task-id 0 --seed 1 \
  --program examples/robosuite/so101_strawberry_transport.py \
  --output-root outputs/local/so101-transport --max-steps 1000 \
  --camera-width 640 --camera-height 640
```

El [programa](../examples/robosuite/so101_strawberry_transport.py) utiliza la API
pública de ASPIRE. Los puntos articulares se calcularon previamente para esta
escena fija, usando el modelo importado. No hay un proveedor general de cinemática
inversa configurado para el SO-101 ni localización visual de la fresa o el recipiente.

## Qué cambia al transportar

El agarre de la lección anterior sostenía el fruto quieto, pero al trasladarlo
perdía presión y acababa soltándolo. Esta tarea añade un ajuste del cierre a 20 Hz
mediante `so101.get_finger_contacts()`: reduce la apertura normalizada en 0,00025
cuando algún dedo mide menos de 1,5 N y la aumenta en 0,0001 si algún dedo supera
3 N. Conserva el límite didáctico de 12 N por dedo y una apertura acotada entre
0,20 y 0,26. El evaluador sigue comprobando fuerzas y penetración cada 2 ms.

Esas lecturas son **sensores virtuales**, disponibles en este simulador. El SO-101
de serie no incluye estos sensores; transferir este controlador al robot real
exigirá decidir cómo medir o estimar el contacto y calibrar sus límites.

La secuencia lleva el fruto hacia atrás, gira sobre el recipiente y baja por
puntos articulares interpolados. Al final abre y vuelve a la postura inicial.
La fruta queda libre bajo gravedad y contactos durante toda la operación:
no se añade una unión con la pinza ni se corrigen sus posiciones o velocidades.

## Recipiente y contacto con el fondo

El recipiente mide 16 × 15 cm por fuera y tiene cinco piezas de colisión: fondo
y cuatro paredes. Su interior tiene 14 × 13 cm, centrado en `(0.245, -0.16)` m
en el plano de la escena. El suelo interior está a 16 mm y el borde a 96 mm.
La altura declarada del centro del fruto al abrir es 130 mm.

El contacto del fruto con los dedos conserva `condim=4`, con fricción
`1 0.005 0.0001`. Para el fondo se declara prioridad 2 y `condim=6`, con los mismos
coeficientes y `solref=0.004 1`: activa resistencia a la rodadura además del
rozamiento tangencial y torsional. En los ensayos sin esa resistencia el fruto
quedaba apoyado, pero seguía rodando y no cumplía la estabilidad exigida. Reducir
el paso físico de 2 a 1 ms no lo resolvió; la versión final mantiene 2 ms.

El coeficiente de rodadura es 0,0001 m y el torsional es 0,005 m; sus unidades
son de longitud, no coeficientes adimensionales ni radios medidos. Todos estos
valores son **hipótesis sin calibrar**. El resultado acredita el ejercicio bajo
este modelo de contacto; no valida que una fresa real quede intacta ni que la
pinza de serie y un recipiente cualquiera reproduzcan esas propiedades.
MuJoCo describe estos modelos en su
[guía de contacto y deslizamiento](https://mujoco.readthedocs.io/en/3.3.0/modeling.html#preventing-slip).

## Evidencia necesaria para completar la tarea

1. Contactos opuestos del agarre y dos segundos de retención libre después de
   desactivar la fijación con la planta.
2. Transporte de al menos 15 cm, sin apoyos externos ni desplazamiento relativo
   del fruto respecto a la pinza superior a 8 mm.
3. Llegada sobre el centro del recipiente, con contactos de ambos dedos y
   postura estable durante 0,25 s. Solo entonces una orden de apertura autoriza
   la transferencia de apoyo al recipiente.
4. Fruto completo dentro de los límites del recipiente, apoyado en el fondo con
   al menos 0,05 N; pinza abierta, sin contactos con los dedos y a más de 8 cm.
5. Velocidad lineal menor de 0,02 m/s y angular menor de 0,15 rad/s durante al
   menos un segundo continuo. El estado final debe seguir cumpliendo esas relaciones.

Abrir antes de llegar, sostener la fresa encima del recipiente, dejarla rodando
o tocar el suelo exterior no completa el ejercicio. Los contactos prohibidos y
las violaciones quedan registrados aunque después desaparezcan. La geometría
de contención incluye la punta, el cáliz y las semillas, además del centro del fruto.

El informe `evaluation/so101-task.json` guarda tiempos de las etapas, contactos,
fuerzas, dimensiones reales de contacto, límites geométricos, velocidades y
trayectoria. `program_ok=true` acredita que el código terminó; `task_success=true`
acredita estas relaciones físicas simuladas.

## Verificar y revisar

```bash
pytest -q tests/test_so101_transport.py
```

Las cinco pruebas cubren la secuencia completa, pérdida de estabilidad después
de un éxito, un contacto breve con el suelo exterior, reinicio, retención sin
transporte, apertura prematura, fruto todavía agarrado sobre el destino y pérdida
del fruto al desactivar el ajuste del cierre. En estas pruebas físicas se evita
renderizar repetidamente imágenes que el programa no usa. La ejecución completa
grabada con ASPIRE comprueba las imágenes y los vídeos reales del simulador.

Los resultados se conservan en `outputs/local/so101-transport-demo/`, con el vídeo
`transporte-y-deposito.mp4`, las dos grabaciones originales, el programa y las
trazas. La auditoría se guarda en `validation-artifacts/setup/transport-review.json`.

## Resultado medido

Ejecución completa del 19 de octubre de 2026, semilla 1:

- `program_ok=true` y `task_success=true`; 629 pasos, 31,45 s simulados.
- Distancia neta máxima del fruto transportado: 231,74 mm.
- Desplazamiento relativo máximo respecto a la pinza: 5,282 mm, por debajo de 8 mm.
- Retención libre verificada a los 10,000 s; destino estable a los 22,272 s;
  apertura a los 23,002 s y apoyo en el fondo a los 23,136 s.
- Colocación estable durante los últimos 3,418 s. Distancia final entre el
  extremo de la pinza y el fruto: 226,49 mm; pinza abierta y sin contactos con él.
- Fuerza final de apoyo en el fondo: 0,1962 N, coherente con 20 g bajo gravedad.
- Máximos de fuerza por dedo en el episodio: 2,792 y 5,427 N; penetración
  máxima del modelo: 0,398 mm. Sin contactos prohibidos ni violaciones.

El resultado completo se conserva en
`outputs/local/so101-transport-demo/run-20261019T084305.327312Z-72fdc0d9/`.
Las dos grabaciones originales tienen 630 fotogramas cada una a 640 × 640.
El vídeo conjunto conserva su velocidad y añade rótulos de las etapas.

Validación terminada: cinco pruebas nuevas y 30 de regresión aprobadas, además
de Ruff y comprobación de espacios de Git. Se decodificaron por completo ambas
grabaciones originales y el vídeo conjunto. Las copias del código en Windows
y Ubuntu coinciden.

Estos resultados corresponden a una sola disposición fija y a los parámetros
de contacto declarados. No representan una tasa de éxito sobre plantas variadas.

## Próximo ejercicio

Variar la posición del recipiente y repetir la tarea con casos de evaluación
definidos. Después podremos introducir visión para localizarlo y estudiar el
desprendimiento por giro y tracción con sus propias condiciones de separación.
