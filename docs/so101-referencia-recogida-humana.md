# Referencias de giro y tracción para recoger fresas

20 de octubre de 2026. Objetivo: orientar ensayos de ASPIRE con datos publicados,
sin confundir una consigna de movimiento con una medida de fuerza ni modificar
el criterio de desprendimiento del simulador.

En las fuentes revisadas no aparece una media poblacional de ángulo de muñeca,
par de torsión axial o recorrido de retirada de una «persona normal» recogiendo
fresas. Sí hay observaciones de trabajadores y cargas de separación medidas,
además de experimentos robóticos con inclinaciones concretas.

## Carga medida al imitar técnicas humanas

[Dimeas et al., Robotica](https://doi.org/10.1017/S0263574714001155), sección 2.2,
tabla 1 ([postprint del autor](https://www.researchgate.net/publication/269516901_Design_and_fuzzy_control_of_a_robotic_gripper_for_efficient_strawberry_harvesting)):

| Técnica | Frutos | Cargas medidas, N | Media, N |
|---|---:|---|---:|
| Tirar recto | 3 | 22,00; 10,00; 9,81 | 13,9367 |
| Doblar y tirar | 6 | 2,78; 3,76; 2,31; 1,57; 5,10; 3,53 | 3,1750 |

Son grupos distintos, pequeños y no pareados, de una variedad no identificada.
La relación descriptiva de medias es 4,39; no aísla un efecto causal ni representa
la fuerza de todas las personas. La segunda media equivale a unos 0,324 kgf:
es una equivalencia de fuerza, no el peso del fruto ni la presión de la pinza.
Los trabajadores observados doblaban el pedúnculo y después retiraban la mano.
El estudio no mide una torsión axial humana universal.

## Ángulos medidos en sistemas robóticos distintos

| Referencia | Resultado pertinente | Alcance |
|---|---|---|
| [Yamamoto et al., JARQ 2014](https://doi.org/10.6090/jarq.48.261), pp.263/266 | Ensayos a 0°, 45° y 90° de tracción; robot con inclinación de 70° por espacio disponible | Beni hoppe, 50 mm/min en el ensayo mecánico; ni 70° ni 90° son medias humanas o ángulos críticos universales |
| [Yang et al., IEEE RA-L 2026](https://doi.org/10.1109/LRA.2025.3630528), sección IV-D ([texto del artículo](https://www.researchgate.net/publication/397405450_High-Tolerance_Soft-Rigid_Gripper_for_Low-Damage_Robotic_Strawberry_Harvesting)) | Óptimo reportado de 20°, carga de separación 6,3 N para Monterey; 60 pruebas por ángulo de 0° a 30° | Pinza envolvente blanda/rígida bajo control manual; aumentar el ángulo también aumentó caídas/deslizamiento |

Las definiciones de ángulo y las pinzas difieren. No se deben mezclar los dos
valores en una curva universal ni afirmar que una persona gira normalmente 70°.
El PDF oficial de Yamamoto se conserva con su hash en los cálculos adjuntos.

## Cálculo de un momento ilustrativo

Con una fuerza perpendicular de 3,175 N y un brazo **supuesto** de 20 mm:

`M = F × r_perpendicular = 3,175 × 0,020 = 0,0635 N·m`.

Es un ejemplo de momento de flexión. No es una medición de par axial humano,
del motor del SO-101 ni del pedúnculo de nuestra escena. Si la dirección de
la fuerza o el brazo cambian, el momento también cambia. El mismo supuesto
con 6,3 N daría 0,126 N·m. No se introduce ninguno como consigna de motor.

Los [cálculos reproducibles](../outputs/local/strawberry-picking-research-20261020/calculations.json)
conservan datos, medias, dispersión, unidades, supuestos y referencias; el
[script](../outputs/local/strawberry-picking-research-20261020/calculate_references.py)
usa sólo aritmética descriptiva.

## Aplicación al ensayo

Se entrega al controlador una referencia pública para explorar **flexión más
amplia seguida de retirada**, eligiendo su propia geometría y límites factibles.
Se medirán por separado ángulo solicitado, giro del TCP, giro estimado de fruta,
movimiento relativo y contacto. Una orden de 70° no demuestra que la fruta haya
girado 70°. Las imágenes pueden quedar inciertas o mostrar deslizamiento.

El límite de fuerza de las herramientas actuales supervisa fuerzas normales de
los dedos; no controla directamente la tracción del pedúnculo ni el par de muñeca.
No hay todavía una medida calibrada de esas dos magnitudes en este ensayo.
El banco sigue siendo provisional: ningún dato bibliográfico convierte su
unión sintética en un modelo biológico calibrado. Sus criterios y física se
mantienen; la biblioteca sólo crecerá con evidencia física e independiente.

La [aplicación registrada](so101-validacion-sistemas-v2.md) terminó con tres
programas y seis episodios. El controlador planteó hasta 40° de flexión, pero
la última variante llegó a 3,94°/7,97° del TCP y paró por movimiento relativo.
No hubo desprendimiento, retirada posterior ni skill nueva. Esto identifica
una limitación de acoplamiento/control; no demuestra que falte simplemente
otro número mayor de ángulo o de presión.
