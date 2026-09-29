# PlacaBasePro 1.2

Diseño y verificación de placas base para perfiles **W, HSS cuadrado/rectangular,
HSS circular y Pipe**, con dibujo paramétrico, anclajes ACI 318-19, llave de corte,
rigidizadores, soldadura y análisis de elementos finitos.

Normas: **AISC 360-22**, **AISC Design Guide 1 (2ª Ed.)**, **ACI 318-19 Cap. 17**.

**Unidades configurables**: longitud en in / ft / mm / cm / m, fuerza en kip / lbf /
kN / N / tonf / kgf, momento y esfuerzo por separado. Se aplican a las entradas, a la
tabla de resultados y a los reportes. El cálculo interno siempre corre en in-kip-ksi,
que son las unidades nativas de AISC v14 y de los pernos en pulgadas.

## Novedades de la 1.2

| Cambio | Dónde |
|---|---|
| **Memoria detallada**: cada ecuación con su símbolo, fórmula, sustitución numérica y resultado, al estilo CalcPad | Pestaña Memoria detallada, y anexo en PDF y Word |
| El **análisis 3D se ejecuta y se ve dentro del programa**: Gmsh y CalculiX corren en segundo plano y el resultado se dibuja en 3D | Pestaña Modelo 3D |
| Los **pernos van etiquetados P1, P2…** en planta, en los mapas del FEA y en la tabla de reacciones | Planta, Elementos finitos |
| **Todo** sale en las unidades elegidas: también la columna de observaciones, los ejes de los dibujos y los títulos | Toda la aplicación |
| **Descripción de cada dato de entrada** en un panel al pie de cada pestaña, más la convención de signos de las cargas | Los 65 campos de entrada |

## Validacion cruzada 2D vs 3D y convergencia de malla (PB-01, W14X90, placa 22×22×2 in)

Se corrio el modelo solido (Gmsh + CalculiX 2.21) y el 2D (Mindlin + Winkler) con las mismas
cargas. Maximo de la placa en el 3D medido a ≥ 1 espesor del perfil y de los agujeros
(las aristas vivas son singularidades de malla). Con la rigidez del concreto repartida por
area tributaria de cada nodo, relacion 3D/2D:

| Caso | von Mises | presion | deflexion | traccion en pernos |
|---|---|---|---|---|
| A: Mux 1800, V 30 | 0.97 | 0.85 | 0.86 | (sin traccion) |
| B: Mux 4200, V 0 | 1.02 | 0.90 | 0.90 | 0.77 |

El 2D queda del lado seguro en presion, deflexion y traccion (10-25 % mas alto) y coincide en
el esfuerzo de von Mises de la placa. No se calibro el 2D: ningun ajuste simple (balasto,
rigidez del perno, espesor bajo la huella, reparto de la carga) mejoro el acuerdo.

Convergencia del 3D (caso B, tamano de malla objetivo en in):

| Malla | Nodos | Tiempo | Tracc. total | Perno max | p max | w placa | vM placa lejos | vM global |
|---|---|---|---|---|---|---|---|---|
| 2.0 | 15,912 | 0.5 min | 85.5 kip | 31.2 | 3.554 | 0.0475 | 26.5 | 138 |
| 1.5 | 27,293 | 0.8 min | 85.5 kip | 30.8 | 3.543 | 0.0474 | 29.4 | 147 |
| 1.0 (auto) | 56,911 | 3 min | 85.4 kip | 30.9 | 3.551 | 0.0475 | 44.2 | 172 |
| 0.75 | 93,481 | 7 min | 85.5 kip | 30.8 | 3.549 | 0.0475 | 46.7 | 192 |

Las cantidades globales (traccion en pernos, presion, deflexion, |U|, reacciones) estan
convergidas desde la malla de 2.0 in (variacion < 1.5 %); una malla de 2.0 in basta para
ellas y corre en ~30 s. El von Mises local NO converge (crece al refinar, sobre todo el maximo
global: singularidades) y el de la placa lejos de las aristas aun sube ~5 % entre 1.0 y 0.75 in,
asi que conviene leerlo con la malla automatica o mas fina.

## Novedades: resultados 3D en la memoria y soldadura parcial

- Tras un analisis 3D, la memoria (PDF y Word) agrega una seccion con las imagenes de von Mises
  y de desplazamiento sobre la geometria deformada, con una etiqueta (★) en el esfuerzo maximo.
  El grafico 3D se ajusta al ancho y alto disponibles y se reajusta al cambiar el tamaño.
- Si alguna zona del perfil esta "Sin soldadura" (p. ej. un W solo soldado en el alma), sale un
  aviso y se verifica el contorno PARCIAL por el metodo elastico sobre las lineas soldadas; la
  compresion se transmite por contacto.

## Novedades: pegar coordenadas desde Excel

Pernos → Coordenadas manuales: boton **Pegar desde Excel** (reemplaza la lista con las
dos columnas x, y del portapapeles) o **Ctrl+V** sobre una celda (sobrescribe desde ella y
agrega filas). **Ctrl+C** copia las filas seleccionadas hacia Excel. Se aceptan coma o
punto decimal; encabezados y rotulos se ignoran; valores en las unidades actuales.

## Novedades: rigidizadores radiales

Con columna circular (HSS redondo o tubo) los rigidizadores se disponen en forma
RADIAL, repartidos por igual en 360° (cantidad = numero total de pletinas; angulo de la
primera en "Angulo de arranque"). El ancho tributario y la reduccion de voladizo usan la
separacion en arco a media proyeccion. La vista 3D ya no usa transparencias (el pedestal
de concreto no se dibuja).

## Novedades: vista 3D de geometria

La pestaña **Modelo 3D** muestra siempre la geometria de la conexion (placa, perfil,
pernos con tuerca, rigidizadores, llave de corte y pedestal transparente), dibujada
directamente por el programa: no necesita Gmsh ni CalculiX y se actualiza al editar.
El combo "Campo" tiene ahora "Solo geometria" (por defecto); tras un analisis 3D pasa a
von Mises. La columna inclinada se dibuja inclinada.

## Novedades: columna inclinada

Pestaña **Perfil → Inclinacion de la columna**: giro alrededor de X y/o de Y (grados,
respecto a la normal de la placa; 0° = perpendicular). Con inclinacion, Pu, Vux, Vuy,
Mux y Muy se ingresan en los ejes de la **columna** (Pu axial, V transversal) y el
programa los proyecta a los ejes de la placa con R = Ry·Rx antes de TODAS las
verificaciones (aplastamiento, pernos, soldadura, llave, FEA, CalculiX, informes).
Ejemplo: giro X = 30° → Pu,placa = Pu·cos30°, Vuy,placa = Vuy·cos30° + Pu·sin30°.
Con la columna inclinada **no se permiten rigidizadores**: la casilla se bloquea y, si el
proyecto ya los tenia, se desactivan al inclinar (o al abrir el archivo).
El torsor Tz que aparece por la inclinacion no se verifica (se emite un aviso).

## Novedades de la 1.5

| Cambio | Donde |
|---|---|
| **Catalogo AISC completo integrado**: 1,660 perfiles W, M, S, HP, C, MC, L, WT, MT, ST, HSS rectangulares y circulares, Pipe | pestana Perfil, lista Familia |
| **Secciones personalizadas**: tipo (I, canal, angulo, te, HSS, tubo, pletina) y dimensiones libres; propiedades calculadas | Perfil > Nueva seccion |
| **Secciones dobles espalda con espalda** con separacion (2L, 2C, 2WT...) | Perfil > Seccion doble |
| **Llave de corte con cualquier perfil**, ademas de la placa | pestana Llave de corte |
| **Biblioteca de materiales** propia: acero, anclajes y concreto | menu Materiales |
| **Varias conexiones por archivo** y reportes de todas de una vez (uno por conexion) | panel Conexiones; Exportar |
| Vista 3D centrada, con proporciones reales y **zoom con la rueda del mouse** (tambien en las vistas 2D) | Modelo 3D |

### Como se calculan las secciones nuevas

Toda seccion (salvo las redondas) se describe como un conjunto de rectangulos:
almas, alas, alas de angulo o pletinas. De ahi salen el dibujo, el solido 3D, las
paredes donde se lee la soldadura y las propiedades de las secciones dobles y
personalizadas. Para un perfil AISC simple se usan los valores de la tabla; los
rectangulos reproducen esas propiedades con 1-2 % de diferencia (los redondeos de
laminacion). Una seccion doble 2L4X4X1/2 con separacion de 3/8 in da Iy = 25.2 in⁴
contra 25.1 del Manual.

**Soldadura de angulos, canales, tes, pletinas y secciones dobles.** Se verifica
como grupo de soldadura por el metodo elastico en todo el contorno exterior,
con la especificacion "perimetral" de la pestana Soldadura:

    fz = −Pu/Lw + Mux·y/Ixw + Muy·x/Iyw   (+ traccion; la compresion va por contacto)
    f  = raiz( max(fz,0)² + (Vux/Lw)² + (Vuy/Lw)² )   <=   φ·0.60·FEXX·garganta

La autoprueba lo contrasta con dos casos a mano (traccion pura y momento puro).
Para estas secciones no se ofrecen rigidizadores.

**Llave de corte con perfil.** En cada direccion de cortante se verifican:
aplastamiento contra el concreto (ancho perpendicular × altura embebida), flexion
con Z del perfil en ese eje, cortante con los elementos paralelos a la fuerza,
soldadura como grupo en todo el contorno y desprendimiento del concreto. El giro
admite 0° o 90°.

### Varias conexiones

Un archivo `.pbase` guarda ahora todas las conexiones del proyecto, junto con los
perfiles personalizados y materiales propios que usen, para que abra igual en
otra computadora. Los archivos de versiones anteriores (una sola conexion) se
siguen abriendo. `Exportar > Reportes ... de TODAS las conexiones` genera un
archivo por conexion en la carpeta que se elija; el analisis 3D se incluye en el
reporte de una conexion solo si se corrio con esa conexion tal como esta.

## Novedades de la 1.4

| Cambio | Donde |
|---|---|
| **Gmsh y CalculiX incluidos**: el analisis 3D corre con un boton (o F8), sin instalar ni configurar nada | pestana Modelo 3D |
| **Revision de soldadura en el modelo 3D**: fuerza por unidad de longitud en cada ala, alma o cara, con D/C pico y D/C media | pestana Modelo 3D y reportes |
| Traccion por perno leida del modelo 3D | pestana Modelo 3D y reportes |
| Concreto **solo a compresion** y pernos **solo a traccion** en el 3D (paso no lineal) | — |
| Corregido: en el 3D el momento Mux/Muy no se aplicaba (iba a los grados de giro del nodo de referencia, que CalculiX ignora) | — |
| **Anclajes postinstalados con adhesivo** (ACI 318-19 17.6.5) para varilla recta | pestana Pernos |
| **Coordenadas manuales** de los anclajes | pestana Pernos |
| Corregido: con traccion neta la traccion se reparte entre todos los pernos (antes solo los de +Y) | — |
| Se quito la exportacion a Excel | — |

## Novedades de la 1.3

| Cambio | Donde |
|---|---|
| Todas las vistas graficas (planta, elevacion, rigidizador, FEA, 3D) dibujan y acotan en el sistema de unidades elegido | pestanas de salida |
| Los reportes — PDF y Word — salen enteros en ese sistema: datos de entrada, verificaciones, FEA y memoria detallada | Exportar |
| Tabla de tensiones perno por perno incluida en los tres reportes | Exportar |
| El calculo y el FEA corren solos con cada cambio; ya no hay boton "Calcular todo" ni casilla de FEA automatico | — |
| El analisis solido 3D se lanza y se ve dentro del programa (pestana Modelo 3D); ya no hay boton de exportacion en la barra | pestana Modelo 3D |
| Criterio del agujero de anclaje seleccionable: Tabla 14-2, arandela F844 o ajustado | pestana Pernos |
| Ejecutable portable para copiar y compartir | `build_portable.bat` |

## Novedades de la 1.1

| Cambio | Dónde |
|---|---|
| Sistema de unidades configurable, con presets | Pestaña Proyecto |
| Ubicación de los rigidizadores: separación fija, corrimiento o alineados con los pernos | Pestaña Rigidizadores |
| Forma de los rigidizadores: rectangular, triangular o con la esquina recortada, más destaje en el vértice | Pestaña Rigidizadores, vista Rigidizador |
| Memoria de cálculo en **PDF** (sin necesidad de Word) | Exportar |
| Tabla resumen de **tensiones perno por perno** | Pestaña Elementos finitos y los tres reportes |
| Los **agujeros de perno se mallan** en el FEA; el perno apoya en el anillo de la tuerca, no en un punto | Pestaña Elementos finitos |
| **Modelo sólido 3D** vía Gmsh + CalculiX, con la placa taladrada de verdad | Exportar |

---

## 1. Usar y compartir

**Si recibio `PlacaBasePro_portable.zip`:** descomprimalo donde quiera y abra
`PlacaBasePro\PlacaBasePro.exe`. No hay que instalar nada: Gmsh va dentro del
programa y CalculiX en `solvers\calculix`. No separe el `.exe` de su carpeta.

**Para compilarlo desde este codigo fuente (Windows):**

1. Tenga **Python 3.10 o superior** instalado.
2. Doble clic en **`build_portable.bat`**.

El script crea un entorno virtual, instala las dependencias (incluida la libreria
de Gmsh), corre las autopruebas, compila, copia `solvers\` y deja:

- `dist\PlacaBasePro\PlacaBasePro.exe` — el programa listo para usar.
- `PlacaBasePro_portable.zip` — la misma carpeta comprimida, para compartir.

`ejecutar_sin_compilar.bat` corre la aplicacion directamente con Python, util
mientras se prueba.

### Uso por línea de comandos

```
PlacaBasePro.exe                                      interfaz gráfica
PlacaBasePro.exe --selftest                           autopruebas del motor
PlacaBasePro.exe PB-01.pbase --pdf m.pdf --docx m.docx --inp m.inp
```

En modo lote devuelve código de salida 0 si cumple y 2 si no cumple, así que se
puede encadenar en un script para verificar muchas placas de golpe.

---

## 2. Lo que se pidió, y dónde está

### 2.1 Catálogo AISC 14

Pestaña **Perfil**. Selector de tipo (W / HSS rect. / HSS circular / Pipe) y luego
el perfil, ordenados por dimensiones. Debajo se muestran d, bf, tf, tw, A y el
origen del dato.

La tabla **integrada** es un subconjunto del Manual AISC 14ª Ed. con los perfiles
de uso más frecuente (249: W4 a W24, HSS cuadrados y rectangulares, HSS circulares
y Pipe STD/XS). **Para el catálogo completo y verificado**, use
`Archivo > Importar base de datos AISC v14.1...` y seleccione el archivo oficial
`aisc-shapes-database-v14.1.xlsx`. El importador reconoce las columnas nativas de
ese archivo (`Type`, `AISC_Manual_Label`, `d`, `bf`, `tf`, `tw`, `Ht`, `B`, `tdes`,
`OD`, `A`, `Ix`, `Sx`, `Zx`, …), guarda el resultado en
`%APPDATA%\PlacaBasePro\shapes.json` y los perfiles importados sustituyen a los
integrados. Hágalo una vez; queda permanente.

### 2.2 Pernos en pulgadas y base de materiales

Pestaña **Pernos**. Diámetros de 1/2" a 3" con `Ase` de rosca UNC (ASME B1.1),
diámetro de agujero según AISC Manual Tabla 14-2, ancho de tuerca hexagonal pesada
(ASME B18.2.2) y `Abrg` calculado como hexágono menos agujero — editable si usa
placa de anclaje en vez de tuerca.

Materiales de anclaje: F1554 Gr.36 / 55 / 105, A307 Gr.C, A36, F3125 Gr.A325
(dos rangos de diámetro) y Gr.A490, A449 (dos rangos), A193 B7, A354 BD. Cada uno
lleva su marca de ductilidad, que es la que decide el φ de ACI Tabla 17.5.3(a).

También hay catálogos de acero de placa (A36, A572 Gr.50/55/60/65, A588, A709,
A514), de perfil (A992, A500 B/C rect. y red., A53, A1085) y de electrodos
(E60XX a E110XX).

### 2.3 Rotación del perfil y pernos por eje

Pestaña **Perfil → Rotación**: cualquier ángulo. 0° = eje fuerte paralelo a N (Y);
90° = eje débil. Con ángulos distintos de 0/90 las fórmulas cerradas de DG1 usan
el rectángulo envolvente del perfil girado (conservador) y lo avisa; el modelo de
elementos finitos sí usa la geometría real girada.

Pestaña **Pernos → Disposición**: `Pernos en eje MAYOR` y `Pernos en eje MENOR`
son independientes. Patrones:

| Patrón | Total de pernos |
|---|---|
| Perimetral (4 lados) | 2·mayor + 2·menor − 4 |
| 2 lados (eje mayor) | 2·mayor |
| 2 lados (eje menor) | 2·menor |
| Circular | el número que indique, equiespaciados |

Distancias al borde `ex` y `ey` independientes. El programa avisa si algún perno
queda dentro del perfil o sin holgura para la tuerca y la llave.

### 2.4 Llave de corte

Pestaña **Llave de corte**. Orientación en X, en Y o en ambos ejes, con W, H, t,
acero, filete y electrodo. Al activarla, **el cortante se reasigna a la llave** y
deja de exigirse a los pernos (se anulan las verificaciones de cortante del
anclaje, como corresponde). Se verifica:

- aplastamiento del concreto contra la llave (ACI 318-19 17.11.2.1, descontando
  el espesor del mortero de la altura embebida);
- flexión y cortante de la pletina;
- soldadura de la llave a la placa (doble filete, V y M combinados);
- desprendimiento del concreto delante de la llave (17.11.2.2 → 17.7.2).

### 2.5 Tipo de anclaje

Pestaña **Pernos → Tipo de anclaje**: con cabeza hexagonal pesada, gancho en L,
gancho en J, o recto. Cambia el dibujo en elevación y la resistencia a extracción:

- **Con cabeza** → `Np = 8·Abrg·f'c` (ACI 17.6.3.2.2a), más verificación de
  desprendimiento lateral si `ca_min < 0.4·hef`.
- **Gancho L/J** → `Np = 0.9·f'c·eh·da` (17.6.3.2.2b), con `eh` limitado a
  3·db ≤ eh ≤ 4.5·db.
- **Recto** → ACI no le reconoce resistencia a extracción. Si hay tracción, el
  programa lo marca como aviso crítico y la verificación sale reprobada, que es
  el comportamiento correcto.

### 2.6 Soldadura

Pestaña **Soldadura**, con definiciones separadas para **alas**, **alma** y
**perímetro** (HSS/Pipe). Cada una: tipo (filete / CJP / PJP / sin soldadura),
tamaño, electrodo y si va a uno o ambos lados.

- CJP con metal de aporte compatible → resistencia = metal base (AISC J2.4); no se
  calcula el depósito, se reporta así.
- Filete y PJP → `φRn = 0.75·0.60·FEXX·garganta·L`, con el incremento direccional
  `(1 + 0.5·sin^1.5 θ)` de la Ec. J2-5 activable. Se verifica también el metal
  base adyacente y el tamaño mínimo de filete de la Tabla J2.4.
- Demanda: las alas toman la fuerza normal del ala (de Mux, Muy y Pu) más su parte
  del cortante; el alma toma el cortante en su plano. En HSS, la soldadura
  perimetral toma todo.

### 2.7 Elementos finitos

Pestaña **Elementos finitos**. Dos niveles:

**(a) Modelo integrado de la placa** — siempre disponible, sin dependencias
externas. Elemento **MITC4** de Mindlin-Reissner (deformaciones de corte supuestas
y ligadas en los puntos medios de los bordes), que evita a la vez el bloqueo por
cortante y los modos de energía nula. Sobre:

- resortes de Winkler nodo a nodo **solo a compresión** (iterativo, contacto
  unilateral) con `ks = Ec/h_pedestal` o manual;
- resortes de perno **solo a tracción**, `kb = E·Ase/(hef + tp + mortero)`;
- rigidizadores como banda de espesor equivalente
  `t_eq = (tp³ + 12·I_pletina/ancho_banda)^⅓` — rigidizan la placa, no la sostienen
  contra el suelo;
- carga repartida sobre la **huella real** del perfil (alas y alma, o paredes del
  HSS), no como una carga puntual.

- los **agujeros de perno recortados de la malla**, con el perno apoyando sobre el
  anillo de la tuerca (corona entre el agujero y el ancho de la hexagonal pesada) en
  vez de sobre un nodo puntual, que es como trabaja de verdad.

Salidas: deflexión, presión de contacto, von Mises, Mx, My, la **tabla de tensiones
perno por perno** (posición, tracción, esfuerzo sobre Ase y D/C frente a AISC J3) y
la demanda de soldadura por pulgada en la interfaz perfil-placa. El reparto real
entre pernos suele ser muy distinto del que supone el método de DG1: en el ejemplo
por defecto, el perno central de la fila traccionada toma más carga que los de
esquina. Cada corrida reporta el **residuo de equilibrio**; en la batería de 45
casos de prueba es ±0.000 kip.

**(b) Modelo SÓLIDO 3D, dentro del programa** — pestaña **Modelo 3D**, botón
*Ejecutar análisis 3D*, o `Cálculo > Análisis SÓLIDO 3D` (F8). Esto sí es
tridimensional de verdad: escribe un `.geo` con kernel OpenCASCADE que construye

- la placa base con los **agujeros taladrados** como cilindros restados,
- el perfil extruido como sólido con el espesor real de sus paredes y alas,
- las pletinas rigidizadoras con su forma (triangular, recortada, etc.),
- la llave de corte por debajo de la placa,

todo fusionado con `BooleanFragments`. La unión perfil-placa queda fusionada, que es
lo que representa una soldadura CJP y el idealizado habitual para un modelo global;
el filete se verifica aparte en forma cerrada por AISC J2.

El programa encadena todo el proceso en segundo plano, sin congelar la ventana:
malla con Gmsh en tetraedros de segundo orden, localiza por coordenadas los nodos
del apoyo, del tope y de cada anillo de perno, escribe el `.inp` de CalculiX con los
resortes de balasto, los resortes de perno (axiales **y** horizontales, que son los
que equilibran el cortante) y las cargas P-M-V en un nodo de referencia, lo resuelve,
y lee el `.frd` para dibujar el resultado en la pestaña. Puede alternar entre von
Mises, |U| y Uz, y amplificar la deformada con un factor de escala.

Junto al `.geo` se deja también **`correr_3d.py`** por si prefiere lanzarlo fuera de
la aplicación, y todos los archivos quedan en la carpeta que elija, listos para abrir
en PrePoMax o CGX.

Requiere Gmsh y CalculiX; indique sus rutas en la pestaña Elementos finitos.

Una advertencia de lectura: los picos de von Mises en aristas vivas — borde del
agujero, encuentro perfil-placa — son **singularidades de malla**. Su valor crece
indefinidamente al refinar y no debe interpretarse como esfuerzo real. Lo que sí es
confiable del modelo 3D es la distribución global, la deformada y el equilibrio de
reacciones, que el programa reporta para que usted lo verifique.

**(c) Modelo de cascarones CalculiX** — la exportación anterior, más liviana:
placa y perfil como `S4` con la unión por `*EQUATION` bilineales. Sigue disponible en
`Exportar > Modelo de cascaras CalculiX`.

### 2.8 Rigidizadores de pletina

Pestaña **Rigidizadores**. Posición en las alas, en el alma, en ambos, o en las
cuatro caras de un HSS. Cantidad, proyección L, altura h, espesor t, acero, filete
y electrodo. Las pletinas **giran con el perfil** y se recortan automáticamente al
contorno de la placa.

Efecto en el cálculo cerrado: el voladizo efectivo pasa a
`m_ef = máx(m − L, mín(m, s/2))`, donde `s` es la separación entre pletinas en esa
cara — pletinas muy separadas casi no reducen el voladizo, igual que muestra el FEA.

Verificaciones: que la proyección quepa en la placa, esbeltez `h/t ≤ 0.56√(E/Fy)`,
flexión y cortante de la pletina, soldadura **a la placa** (flujo de cortante) y
soldadura **a la columna** (V y M) — que son trayectorias de carga distintas y se
verifican por separado.

---

## 3. Lista completa de verificaciones

| Grupo | Verificación | Referencia |
|---|---|---|
| Placa | Aplastamiento del concreto, casos 1 y 2 | AISC J8, DG1 §3.3 |
| Placa | Espesor requerido (m, n, λn' y voladizo traccionado) | DG1 §3.1 y §3.3 |
| Perno | Tracción, cortante e interacción | AISC J3, Ec. J3-3a |
| Anclaje | Acero en tracción | ACI 17.6.1 |
| Anclaje | Arrancamiento del concreto en tracción (grupo) | ACI 17.6.2 |
| Anclaje | Extracción — pullout (cabeza o gancho) | ACI 17.6.3 |
| Anclaje | Desprendimiento lateral, si `ca_min < 0.4·hef` | ACI 17.6.4 |
| Anclaje | Acero en cortante (con factor 0.80 por mortero) | ACI 17.7.1 |
| Anclaje | Arrancamiento del concreto en cortante | ACI 17.7.2 |
| Anclaje | Pryout | ACI 17.7.3 |
| Anclaje | Interacción tracción-cortante | ACI 17.8 |
| Detallado | Distancia del perno al borde | AISC Tabla 14-2 / J3.4 |
| Soldadura | Ala, alma o perímetro; depósito y metal base; tamaño mínimo | AISC J2.4, Tabla J2.4 |
| Llave | Aplastamiento, flexión, cortante, soldadura, breakout | ACI 17.11, AISC F11/J2 |
| Rigidizador | Geometría, esbeltez, flexión, cortante, dos soldaduras | AISC B4.1a, F11, J2 |
| Perfil | Esfuerzo normal combinado y cortante en la base | AISC H1, G2 |
| FEA | von Mises, presión de contacto, tracción máxima por perno | — |

Opciones globales: concreto fisurado/no fisurado, condición A/B de refuerzo
suplementario, diseño sísmico (factor 0.75 de ACI 17.10.5.2), concreto liviano λa,
y descuento de la fricción placa-mortero del cortante en pernos.

---

## 3.bis  Memoria detallada (el "modo CalcPad")

La pestaña **Memoria detallada** muestra el cálculo completo paso a paso. Cada línea
tiene cuatro partes:

```
fp,max = φc·Pp / A1 = 8,651 / 312,257 = 27.70 MPa          [AISC Ec. J8-2]
  símbolo   fórmula     sustitución      resultado           referencia
```

No es un texto redactado aparte que pueda quedar desfasado: son los mismos cálculos
los que van registrando sus pasos mientras corren, así que la memoria y los números
de la tabla de verificaciones no pueden divergir. Todo sale en las unidades de
trabajo del proyecto, y las verificaciones aparecen marcadas con su D/C en verde o
rojo dentro de la sección que les corresponde.

Se incluye como anexo en los tres reportes (se puede desactivar con la casilla de la
pestaña) y hay un botón para copiarla al portapapeles.

## 4. Salidas

- **Memoria de cálculo PDF** — generada directamente, sin necesidad de tener Word
  instalado. Mismo contenido que la versión en Word, con la tabla de tensiones por
  perno incluida.
- **Memoria de cálculo Word** — datos de entrada, desarrollo del equilibrio de DG1,
  tabla de verificaciones con los D/C en rojo cuando no cumplen, avisos, resumen
  del FEA y anexo con planta, elevación y mapas de von Mises, presión y deflexión.
- **Imágenes PNG** sueltas.
- **Modelo `.inp` de CalculiX**.
- **Proyecto `.pbase`** (JSON legible) para reabrir o correr por lotes.

Todos los reportes salen en el sistema de unidades que haya elegido en la pestaña
Proyecto, incluida la tabla de verificaciones.

---

## 5. Alcance y limitaciones

Léalas antes de firmar nada con esto.

1. **La tabla de perfiles integrada debe verificarse** contra el Manual AISC, o
   mejor, reemplazarse importando la base oficial v14.1. Es un subconjunto
   transcrito, no la base certificada.
2. **Placa circular**: las fórmulas cerradas usan el cuadrado equivalente de igual
   área (`Leq = 0.8862·Dp`). Es una aproximación de diseño; el FEA sí modela el
   contorno circular real.
3. **Rotaciones distintas de 0° y 90°**: las fórmulas de DG1 usan el rectángulo
   envolvente del perfil girado. Conservador, pero conservador.
4. **Momento biaxial**: `Muy` entra en el esfuerzo del perfil, en la soldadura y en
   el FEA, pero el equilibrio cerrado de aplastamiento de DG1 es uniaxial (usa
   `Mux`). Con biaxial importante, gobierne por el FEA.
5. `ψec,N` y `ψec,V` de ACI se dejan en 1.0; si la resultante de tracción o el
   cortante son excéntricos respecto al grupo, ajústelos a mano.
6. No se verifica: fatiga, efecto de palanca (*prying*) por flexibilidad de la
   placa, anclajes post-instalados adheridos, ni el refuerzo del pedestal.
7. El FEA integrado es **lineal elástico** con contacto unilateral. No hay
   plasticidad ni pandeo. Para eso está la exportación a CalculiX.
8. Para diseño sísmico, ACI 17.10 además exige que el anclaje sea gobernado por la
   fluencia dúctil del acero; el programa aplica el 0.75 pero **no** verifica ese
   requisito de jerarquía por usted.

---

## 6. Estructura del código

```
run.py                  punto de entrada (GUI / lote / autopruebas)
selftest.py             45 casos de prueba del motor
placabase/
  units.py              sistema de unidades configurable (UnitSet)
  materials.py          aceros, varillas, electrodos, geometría de pernos
  shapes.py             catálogo AISC integrado + importador de la base oficial
  model.py              dataclasses del proyecto, serialización .pbase
  geometry.py           contornos, rotación, disposición de pernos, llave,
                        rigidizadores, detección de interferencias
  design.py             aplastamiento, espesor, soldadura, llave, rigidizadores
  anchors.py            ACI 318-19 Cap. 17 y AISC J3
  fea.py                elemento MITC4, agujeros mallados, contacto unilateral
  ccx.py                exportación de cascarones a CalculiX
  mesh3d.py             modelo sólido 3D: .geo de Gmsh, .inp de CalculiX y pipeline
  view3d.py             lectura del .frd y dibujo 3D de resultados
  explain.py            registro de ecuaciones para la memoria detallada
  draw.py               planta, elevación y mapas del FEA
  report.py             PDF y DOCX
  weld3d.py             soldadura, pernos y contacto leidos del modelo 3D
  dialogs.py            seccion personalizada y biblioteca de materiales
  data/aisc_shapes.json catalogo AISC integrado (1,660 perfiles)
  ui.py, ui_widgets.py  interfaz PySide6
ejemplos/               tres proyectos resueltos
```

Para tocar el motor sin abrir la GUI: `python run.py --selftest` corre los 45
casos y verifica, entre otras cosas, que el residuo de equilibrio del FEA sea nulo
en todos.

---

## 7. Ejemplos incluidos

| Archivo | Caso | D/C | Gobierna |
|---|---|---|---|
| `PB-01_W14X90.pbase` | W14X90, 22×22×2", 8 pernos Ø1¼", llave de corte | 0.750 | distancia al borde |
| `PB-02_HSS12_rigidizada.pbase` | HSS12X12X½, 24×24×2", rigidizadores perimetrales, soldadura CJP | 0.949 | esbeltez del rigidizador |
| `PB-03_poste_circular.pbase` | Pipe/HSS16 sobre placa circular Ø30", 12 pernos Ø1½" con gancho en J | 1.000 | aplastamiento del concreto |

---

*Los resultados deben ser revisados por un ingeniero responsable. El programa es
una herramienta de cálculo, no un sustituto del criterio profesional.*


## Modelo solido 3D: como se lee la soldadura

La union perfil-placa esta fusionada en el solido. Para cada pared del perfil (alas
y alma de un W, caras de un HSS, perimetro de un tubo) se recorre su linea media en
tramos; en cada tramo se promedian los esfuerzos de una franja situada justo por
encima del pie del cordon (para no leer la singularidad de la esquina) y se
integran en el espesor de la pared:

    f_n = t · σzz      normal al cordon (+ traccion)
    f_l = t · τ        cortante a lo largo del cordon
    f_t = t · τ        cortante transversal

Como en la DG1, la compresion se transmite por contacto y el cordon se verifica a
traccion y cortante: f = raiz(max(f_n,0)² + f_l² + f_t²), contra la resistencia del
metodo vectorial de AISC J2.4 (con el incremento direccional si esta activado en la
pestana Soldadura) limitada por el metal base.

Se reportan dos valores:

- **D/C pico** — el tramo mas cargado. Suele estar donde el alma llega al ala: la
  placa es flexible y la traccion se concentra ahi. Es una concentracion elastica
  local; las soldaduras tienen cierta capacidad de redistribuir, pero conviene
  mirarla.
- **D/C media** — la fuerza de toda la pared repartida en su longitud, que es lo
  que supone el calculo de forma cerrada.

Verificacion: la fuerza vertical integrada en el pie del perfil reproduce la carga
axial aplicada (en el caso de prueba, −149.8 kip contra Pu = −150 kip), y la
reaccion del concreto menos la traccion de los pernos cierra con Pu.
