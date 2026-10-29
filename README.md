# Proyecto 2 — Motor de inferencia con cláusulas de Horn

**Introducción a la Inteligencia Artificial · Pontificia Universidad Javeriana**

Sistema experto de triaje médico que decide si un diagnóstico o estado de alerta (**α**) se
deduce lógicamente de los síntomas de un paciente (**Δ**) usando una base de conocimiento
(**KB**) de reglas de Horn. Resuelve el problema **KB ∪ Δ ⊨ α** con dos motores:

| Motor | Función | Estrategia |
|---|---|---|
| Encadenamiento hacia adelante | `ejecutar_inferencia()` | Parte de los síntomas y deduce hechos hasta llegar a α o a un punto fijo |
| Encadenamiento hacia atrás | `ejecutar_inferencia_atras()` | Parte de α y lo descompone en sub-objetivos hasta llegar a los síntomas |

Este README es una **guía de sustentación**: explica qué hace cada parte del código, cómo lo
hace y por qué se diseñó así. Al final hay preguntas probables con sus respuestas y un guion
para la demostración en vivo.

---

## Índice

1. [Cómo ejecutarlo](#1-cómo-ejecutarlo)
2. [Archivos del repositorio](#2-archivos-del-repositorio)
3. [Conceptos teóricos mínimos](#3-conceptos-teóricos-mínimos)
4. [La base de conocimiento](#4-la-base-de-conocimiento-base_conocimientojson)
5. [Arquitectura del código](#5-arquitectura-del-código)
6. [Motor hacia adelante](#6-motor-hacia-adelante-ejecutar_inferencia)
7. [Motor hacia atrás](#7-motor-hacia-atrás-ejecutar_inferencia_atras)
8. [Auditoría de la KB](#8-auditoría-de-la-kb-validar_kb)
9. [Presentación de las trazas](#9-presentación-de-las-trazas)
10. [Programa principal y casos clínicos](#10-programa-principal-y-casos-clínicos)
11. [Pruebas automáticas](#11-pruebas-automáticas-test_motorpy)
12. [Preguntas probables en la sustentación](#12-preguntas-probables-en-la-sustentación)
13. [Guion para la demostración en vivo](#13-guion-para-la-demostración-en-vivo)
14. [Limitaciones](#14-limitaciones)

---

## 1. Cómo ejecutarlo

Requisitos: **Python 3.8 o superior**. No usa librerías externas, solo la biblioteca estándar.

```bash
# Ejecutar los 7 casos clínicos con ambos motores
python proyecto_inferencia_final.py

# Usar otra base de conocimiento
python proyecto_inferencia_final.py otra_kb.json

# Ejecutar las 43 pruebas automáticas
python -m unittest -v test_motor
```

El programa:

1. Carga la KB y la audita (ciclos, reglas inalcanzables, profundidad).
2. Ejecuta los 7 casos clínicos con los dos motores y muestra sus trazas.
3. Muestra una tabla resumen y guarda todo en `trazas_casos_clinicos.txt`.
4. Termina con **código 0** si todos los casos dan el resultado esperado y con **código 2** si
   alguno falla (útil para automatizar).

En una terminal la salida usa colores. Si se redirige a un archivo, o si la variable de
entorno `NO_COLOR` existe, se imprime sin colores.

---

## 2. Archivos del repositorio

| Archivo | Contenido |
|---|---|
| `proyecto_inferencia_final.py` | Motor de inferencia: estructuras de datos, los dos motores, auditoría de la KB, presentación de trazas y programa principal |
| `base_conocimiento.json` | 115 reglas de Horn del dominio médico, más metadatos (fuentes, advertencias, hechos base) |
| `test_motor.py` | 43 pruebas automáticas con `unittest` |
| `trazas_casos_clinicos.txt` | Salida de la última ejecución (se regenera cada vez) |

La carpeta `documentacion/` (informe técnico, enunciado y figuras) no se versiona; está en
`.gitignore`.

---

## 3. Conceptos teóricos mínimos

Lo que hay que tener claro para defender el proyecto:

- **Cláusula de Horn:** regla con antecedentes unidos por Y y **un solo** consecuente
  positivo: `P1 ∧ P2 ∧ … ∧ Pn → Q`. No admite «o» en el consecuente ni negaciones.
- **Consecuencia lógica `KB ∪ Δ ⊨ α`:** α es verdadero en todo modelo donde la KB y los
  hechos lo son.
- **Modus ponens:** si se conocen `P1 … Pn` y existe la regla `P1 ∧ … ∧ Pn → Q`, se puede
  agregar `Q`. Para cláusulas de Horn es **correcto** (solo deduce cosas verdaderas) y
  **completo** (deduce todo lo que se puede deducir).
- **Memoria de trabajo:** el conjunto de hechos conocidos en un momento dado.
- **Punto fijo:** estado en el que ninguna regla agrega hechos nuevos. Ese conjunto final es
  exactamente todo lo que la KB y Δ implican; si α no está ahí, α no es consecuencia lógica.
- **Mundo cerrado:** un hecho que no se observó y no se puede deducir se considera falso.

Por eso **ambos motores deben dar siempre el mismo resultado**: los dos son procedimientos
correctos y completos para cláusulas de Horn. Las pruebas lo comprueban (sección 11).

---

## 4. La base de conocimiento (`base_conocimiento.json`)

### 4.1 Formato

```json
{
  "id": "R76",
  "nivel": 3,
  "antecedentes": ["Neumonico_Sospechado", "Dificultad_Respiratoria"],
  "consecuente": "Neumonia"
}
```

- `antecedentes` es una lista que el motor interpreta como conjunción (Y).
- `consecuente` es **un solo texto**, por lo que el formato no permite escribir algo que no
  sea Horn.
- `nivel` es informativo: el motor no lo usa. La profundidad real la calcula el código.
- Convención de nombres: `Mayuscula_Inicial` con guiones bajos y sin tildes. Un hecho debe
  escribirse igual en todas partes, porque `Fiebre` y `fiebre` son símbolos distintos.

El archivo también tiene metadatos: fuentes (dataset de Kaggle y protocolos de la OMS),
advertencias de uso, `hechos_base_permitidos` y la correspondencia entre las columnas del
dataset y los hechos de la KB.

### 4.2 Estructura en cuatro niveles

| Nivel | Paso | Reglas | Ejemplo |
|---|---|---|---|
| 1 | Hechos → Signos | 41 | `Fiebre ∧ Tos → Cuadro_Febril_Respiratorio` |
| 2 | Signos → Síndromes | 28 | `Broncoespasmo ∧ Compromiso_Respiratorio → Obstructivo_Bronquial` |
| 3 | Síndromes → Enfermedades | 23 | `Obstructivo_Bronquial ∧ Antecedente_Asma → Exacerbacion_Asma` |
| 4 | Enfermedad → Alerta | 23 | `Neumonia ∧ Disnea_Severa → Alerta_Roja_Respiratoria` |

En total hay **115 reglas, 42 hechos base** (síntomas que se pueden observar), 97 hechos
derivados y **11 objetivos finales** (estados de alerta). Todos los objetivos finales están a
profundidad 4, así que nunca se salta de un síntoma a una alerta en un solo paso.

### 4.3 Hechos diferenciadores

Las enfermedades parecidas comparten una categoría intermedia y se separan por **un solo
hecho**:

| Enfermedad | Comparte | Hecho diferenciador |
|---|---|---|
| Exacerbación de asma (R77) | `Obstructivo_Bronquial` | `Antecedente_Asma` |
| Exacerbación de EPOC (R78) | `Obstructivo_Bronquial` | `Antecedente_EPOC` |
| Influenza (R52, R73) | `Malestar_Febril` | `Mialgias` |
| Faringitis (R56, R85) | `Malestar_Febril` | `Dolor_Garganta` |
| Bronquitis (R53, R75) | `Cuadro_Febril_Respiratorio` | `Expectoracion` |
| Neumonía (R55, R76) | `Cuadro_Febril_Respiratorio` y disnea | `Dolor_Toracico_Pleuritico` |
| Resfriado común (R51, R74) | `Cuadro_Respiratorio_Con_Fatiga` | `Rinorrea` y `Estornudos` |

### 4.4 Reglas de gravedad

Toman un diagnóstico **ya inferido** y lo combinan con un síntoma crítico nuevo:

- R95: `Neumonia ∧ Disnea_Severa → Alerta_Roja_Respiratoria`
- R96: `Influenza ∧ Signo_Hipoxia_Critica → Alerta_Roja_Respiratoria`
- R97: `Exacerbacion_Asma ∧ Disnea_Severa → Alerta_Roja_Respiratoria`
- R98: `Exacerbacion_EPOC ∧ Signo_Hipoxia_Critica → Alerta_Roja_Respiratoria`
- R109: `Deshidratacion_Grave ∧ Contexto_Pediatrico → Alerta_Roja_Deshidratacion_Pediatrica`

### 4.5 Ejemplo de cadena completa

Con los síntomas Fiebre, Tos, Dificultad_Respiratoria, Dolor_Toracico_Pleuritico y
Dificultad_Respiratoria_Severa:

```
Nivel 1  Fiebre ∧ Tos ∧ Dificultad_Respiratoria  → Cuadro_Respiratorio_Febril_Con_Disnea  (R8)
Nivel 1  Fiebre ∧ Dolor_Toracico_Pleuritico      → Febril_Pleuritico                      (R37)
Nivel 1  Dificultad_Respiratoria_Severa          → Disnea_Severa                          (R25)
Nivel 2  Cuadro_Resp…_Con_Disnea ∧ Febril_Pleuritico → Neumonico_Sospechado               (R55)
Nivel 3  Neumonico_Sospechado ∧ Dificultad_Respiratoria → Neumonia                        (R76)
Nivel 4  Neumonia ∧ Disnea_Severa                → Alerta_Roja_Respiratoria               (R95)
```

### 4.6 Correcciones hechas durante la auditoría

La primera versión (117 reglas) tenía problemas que el validador detectó:

- La lista `hechos_base_permitidos` estaba en minúsculas y las reglas con mayúscula inicial.
  Se unificó la convención.
- Siete hechos derivados no llevaban a ningún diagnóstico. Se eliminaron R12, R19 y R20, que no
  tenían valor clínico, y se conectaron los demás modificando R46, R64 y R94 y agregando R118.
- R86 (choque) pasó a exigir `Contexto_Pediatrico`, porque ETAT es un protocolo pediátrico, y
  R89 (fallo respiratorio) pasó a exigir `Neurologico`.

Se conservan reglas de un solo antecedente en las cadenas de emergencia (vía aérea,
hemorragia, convulsiones). Es intencional: en el triaje de la OMS un solo signo crítico basta
para escalar la prioridad.

---

## 5. Arquitectura del código

`proyecto_inferencia_final.py` está dividido en las partes de la plantilla del profesor:

```
PARTE 1 · Estructura de datos (no se modificó)
   class Regla            id_regla, antecedentes (set), consecuente
   class MotorInferencia  __init__, cargar_kb

PARTE 2 · Motores (métodos de MotorInferencia)
   _construir_indice()            consecuente → reglas que lo concluyen
   ejecutar_inferencia()          motor hacia adelante
   ejecutar_inferencia_atras()    motor hacia atrás (prepara el estado)
   _probar()                      recursión del motor hacia atrás
   _log()                         registra eventos de la búsqueda
   _reconstruir_derivacion()      demostración final en orden
   formatear_traza()              texto de la traza (tabla o árbol)
   _tabla_adelante()              tabla de disparos
   _arbol_busqueda()              árbol Y/O con conectores ├─ └─
   exportar_traza()               guarda la traza en .txt o .json
   validar_kb()                   auditoría de restricciones lógicas
   hechos_desconocidos()          detecta errores de digitación en Δ

Utilidades de presentación (funciones del módulo)
   activar_color, negrita, verde, rojo…, sin_color, rellenar, centrar, titulo_caja…

PARTE 3 · Ejecución
   CASOS_CLINICOS          los 7 casos con su resultado esperado
   texto_auditoria()       bloque de auditoría
   ejecutar_caso()         corre ambos motores sobre un caso
   texto_resumen()         tabla final
   main()                  punto de entrada
```

### 5.1 Parte 1: estructuras de datos

```python
class Regla:
    def __init__(self, id_regla, antecedentes, consecuente):
        self.id_regla = id_regla
        self.antecedentes = set(antecedentes)
        self.consecuente = consecuente
```

**Detalle clave:** los antecedentes se guardan como **conjunto** (`set`). Así, la pregunta
«¿se cumplen todos los antecedentes?» es una sola operación de inclusión:

```python
regla.antecedentes <= memoria   # ¿antecedentes ⊆ memoria?
```

`cargar_kb()` lee el JSON y crea un objeto `Regla` por cada entrada. Si el archivo no existe o
está mal formado, imprime el error y retorna una lista vacía. Con una lista vacía ningún motor
falla: simplemente no se deduce nada.

---

## 6. Motor hacia adelante (`ejecutar_inferencia`)

**Idea:** partir de los síntomas y aplicar modus ponens una y otra vez hasta deducir α o hasta
que ya no salga nada nuevo.

### 6.1 Algoritmo

```python
self.memoria_trabajo = set(hechos_iniciales)
self.traza_explicacion = []

if objetivo in self.memoria_trabajo:          # caso trivial: α ∈ Δ
    return True

reglas_pendientes = list(self.reglas)
iteracion = paso = 0
while True:
    iteracion += 1
    foto = set(self.memoria_trabajo)          # (1) foto de la memoria: una "ola"
    aplicables, siguen_pendientes = [], []
    for regla in reglas_pendientes:           # (2) separar las reglas que se pueden disparar
        if regla.antecedentes <= foto:
            aplicables.append(regla)
        else:
            siguen_pendientes.append(regla)
    reglas_pendientes = siguen_pendientes     # (3) refracción: las aplicables salen para siempre

    hubo_hechos_nuevos = False
    for regla in aplicables:                  # (4) disparar en el orden de la KB
        if regla.consecuente in self.memoria_trabajo:
            continue                          #     otra regla ya lo dedujo
        self.memoria_trabajo.add(regla.consecuente)
        hubo_hechos_nuevos = True
        paso += 1
        self.traza_explicacion.append({...})  # (5) registrar paso, ola, regla, hecho nuevo
        if regla.consecuente == objetivo:
            return True                       # (6) éxito: parada temprana

    if not hubo_hechos_nuevos:
        return False                          # (7) punto fijo: fallo
```

### 6.2 Decisiones de diseño y su justificación

| Decisión | Por qué |
|---|---|
| **Foto de la memoria por ola** | Una regla solo puede usar hechos conocidos al **inicio** de la ola. Así el número de ola en que aparece un hecho coincide con su **nivel de inferencia**, y la traza muestra la progresión signos → síndromes → enfermedad → alerta. |
| **Refracción** (cada regla sale de `reglas_pendientes` una sola vez) | Garantiza que el algoritmo **termina**: hay un número finito de reglas y la memoria solo crece. Funciona aunque la KB tuviera ciclos. |
| **Orden de la KB** dentro de cada ola | Es la estrategia de resolución de conflictos. Hace la traza **determinista**: siempre sale igual. |
| **Parada temprana** | No hace falta calcular todo el cierre si α ya apareció. |
| **`sorted(antecedentes)` en la traza** | Un `set` no tiene orden fijo; ordenarlo hace la salida reproducible. |

### 6.3 Complejidad

Cada ola recorre las reglas pendientes y comprueba la inclusión de hasta *k* antecedentes:
**O(|R|·k)** por ola. En el peor caso hay |R| olas, lo que da **O(|R|²·k)**. En esta KB hay a lo
sumo 4 o 5 olas, porque siguen los niveles.

### 6.4 Ejemplo real (caso 1: choque pediátrico)

```
Paso  Nivel  Regla  Antecedentes                                          Hecho nuevo
   1      1  R27    Manos_Frias ∧ Pulso_Debil_Rapido ∧ Relleno_Capilar…   Signo_Choque_Etat
   2      2  R58    Signo_Choque_Etat                                     Sindrome_Choque_Etat
   3      3  R86    Contexto_Pediatrico ∧ Sindrome_Choque_Etat            Choque
   4      4  R102   Choque                                                Alerta_Roja_Circulatoria
```

Una regla por ola: es el ejemplo más claro de los cuatro niveles.

---

## 7. Motor hacia atrás (`ejecutar_inferencia_atras`)

**Idea:** partir de α y preguntar «¿qué regla lo concluye?». Sus antecedentes se convierten en
sub-objetivos, que se prueban de la misma forma, hasta llegar a los síntomas. Es una
**búsqueda en profundidad sobre un árbol Y/O**:

- **O** entre las reglas: basta con que **una** de las reglas que concluyen la meta funcione.
- **Y** entre los antecedentes: dentro de una regla, **todos** deben probarse.

### 7.1 Preparación

```python
hechos = set(hechos_iniciales)
self._indice     = self._construir_indice()   # consecuente → [reglas], búsqueda en O(1)
self._memo_exito = {}      # meta → regla que la probó (None si es un hecho observado)
self._memo_fallo = set()   # metas que se sabe que no son demostrables
self._cortes     = 0       # cuántas ramas se cortaron por ciclo o por profundidad
self._max_prof   = max_profundidad if max_profundidad is not None else len(self.reglas) + 1
resultado = self._probar(objetivo, hechos, set(), 0)
if resultado:
    self.derivacion = self._reconstruir_derivacion(objetivo)
```

### 7.2 La recursión `_probar(meta, hechos, camino, nivel)`

Los **casos base** se revisan en este orden:

| # | Condición | Resultado | Para qué sirve |
|---|---|---|---|
| 1 | `meta in hechos` | ✔ verdadero | La meta es un síntoma observado: es la hoja del árbol |
| 2 | `meta in _memo_exito` | ✔ verdadero | Ya se demostró en otra rama; no se repite el trabajo |
| 3 | `meta in _memo_fallo` | ✘ falso | Ya se sabe que no es demostrable |
| 4 | `meta in camino` | ✘ falso + corte | **Ciclo**: la meta reaparece en su propia rama |
| 5 | `nivel > _max_prof` | ✘ falso + corte | **Control de profundidad**: corte de seguridad |
| 6 | Ninguna regla la concluye | ✘ falso | No es síntoma ni se puede deducir (mundo cerrado) |

Si ningún caso base aplica, viene el **paso recursivo**:

```python
camino.add(meta)                          # meta en curso en esta rama
cortes_antes = self._cortes
for regla in candidatas:                  # O entre reglas
    if all(self._probar(a, hechos, camino, nivel + 1)
           for a in sorted(regla.antecedentes)):   # Y con cortocircuito
        camino.discard(meta)
        self._memo_exito[meta] = regla
        return True
camino.discard(meta)
if self._cortes == cortes_antes:          # solo si no hubo cortes
    self._memo_fallo.add(meta)
return False
```

### 7.3 Detalles que hay que saber explicar

**`all()` con un generador = Y con cortocircuito.** `all()` se detiene en el primer `False`, así
que si un antecedente falla, los siguientes de esa regla no se evalúan. En el caso 2, al fallar
`Dolor_Toracico_Pleuritico`, el motor ya no evalúa `Fiebre` dentro de R37.

**`camino` contiene solo las metas de la rama actual.** Se agrega la meta al entrar y se quita al
salir, sea con éxito o con fallo. Así se detecta `A → B → A` en la misma rama, pero una meta
puede aparecer sin problema en ramas distintas.

**¿Por qué no se memoriza un fallo causado por un corte?** Porque ese fallo depende del camino
y no es definitivo. Ejemplo de `test_motor.py`:

```
R1: Y → X      R2: W → X      R3: X → Y      R4: X ∧ Y → Meta      Δ = {W}
```

1. Para probar `Meta` (R4) se prueba primero `X`.
2. `X` intenta R1, que pide `Y`. `Y` intenta R3, que pide `X`, pero `X` está en curso: **ciclo**,
   y `Y` falla.
3. `X` intenta R2 con `W`: ✔. `X` queda demostrada.
4. Ahora R4 necesita `Y`. Si su fallo del paso 2 se hubiera memorizado, `Meta` fallaría por
   error. Como no se memorizó, `Y` se prueba de nuevo, ahora vía `X` ✔, y `Meta` ✔.

El contador `_cortes` lo resuelve: si durante la búsqueda de una meta hubo algún corte, su fallo
no se guarda.

**Límite de profundidad por defecto = |R| + 1 = 116.** En una KB acíclica ninguna cadena de
prueba puede ser más larga que el número de reglas, así que con la KB real nunca se activa; es
una protección adicional. Se puede cambiar: `ejecutar_inferencia_atras(Δ, α, max_profundidad=50)`.

**Memoización = complejidad lineal.** Cada meta se resuelve como máximo una vez, así que el costo
es **O(|R|·k)**. Sin memoria, una meta compartida por varias ramas se recalcularía muchas veces.

### 7.4 Reconstrucción de la derivación

`_memo_exito` guarda qué regla probó cada meta. `_reconstruir_derivacion()` recorre ese registro
desde α en **post-orden** (primero los antecedentes, después la regla). El resultado es la
demostración ordenada de los síntomas al objetivo, con **solo** las reglas que intervienen. El
conjunto `vistos` evita repetir una regla cuando un mismo hecho derivado alimenta a varias reglas
de la demostración.

### 7.5 Ejemplo real (caso 2: neumonía sin hecho diferenciador)

```
Neumonia  ✘ no demostrable
└─ R76: Dificultad_Respiratoria ∧ Neumonico_Sospechado  ✘
   ├─ Dificultad_Respiratoria  ✔ hecho observado
   └─ Neumonico_Sospechado  ✘ no demostrable
      └─ R55: Cuadro_Respiratorio_Febril_Con_Disnea ∧ Febril_Pleuritico  ✘
         ├─ Cuadro_Respiratorio_Febril_Con_Disnea  ✔ demostrado con R8
         │  └─ R8: Dificultad_Respiratoria ∧ Fiebre ∧ Tos  ✔
         │     ├─ Dificultad_Respiratoria  ✔ hecho observado
         │     ├─ Fiebre  ✔ hecho observado
         │     └─ Tos  ✔ hecho observado
         └─ Febril_Pleuritico  ✘ no demostrable
            └─ R37: Dolor_Toracico_Pleuritico ∧ Fiebre  ✘
               └─ Dolor_Toracico_Pleuritico  ✘ no observado y ninguna regla lo concluye
```

El árbol señala exactamente qué faltó: el dolor torácico pleurítico.

---

## 8. Auditoría de la KB (`validar_kb`)

Comprueba las restricciones de la sección 3.2 del enunciado y retorna un diccionario:

| Clave | Cómo se calcula |
|---|---|
| `ids_duplicados` | Identificadores que aparecen más de una vez |
| `ciclos` | **DFS con tres estados** (sin visitar / en curso / terminado) sobre el grafo consecuente → antecedentes. Llegar a un nodo «en curso» significa que hay un ciclo |
| `hechos_base` | Antecedentes que ninguna regla concluye: los síntomas observables |
| `terminales` | Consecuentes que no son antecedentes de nada: los objetivos finales |
| `terminales_menor_nivel_4` | Objetivos con profundidad mínima < 4. Profundidad: `prof(base) = 0`; `prof(h) = 1 + mín sobre reglas de (máx prof de sus antecedentes)`, con memoria |
| `reglas_inalcanzables` | Se ejecuta forward chaining con **todos** los hechos base hasta el punto fijo; las reglas que nunca se disparan son «islas» |

Con la KB actual: 0 duplicados, 0 ciclos, 0 inalcanzables y los 11 objetivos con profundidad 4.

`hechos_desconocidos(hechos)` devuelve los síntomas de Δ que no aparecen en ninguna regla.
Sirve para detectar errores de digitación como `fiebre` en vez de `Fiebre`; el programa los
muestra como aviso.

---

## 9. Presentación de las trazas

Ninguna de estas funciones cambia la lógica: solo dan formato a lo que los motores registraron.

- **Motor hacia adelante:** `traza_explicacion` es una lista de diccionarios
  `{paso, iteracion, regla, antecedentes, consecuente}`. `_tabla_adelante()` la muestra como
  tabla alineada; los antecedentes largos se parten en varias líneas con `textwrap`.
- **Motor hacia atrás:** `_log()` registra eventos planos con su `nivel` de profundidad (`META`,
  `REGLA`, `HECHO`, `MEMO`, `CICLO`, `PROFUNDIDAD`, `EXITO`, `FALLO`). `_arbol_busqueda()`
  reconstruye el árbol Y/O leyendo esa lista recursivamente:
  - un evento `META` abre un nodo;
  - los `REGLA` del mismo nivel son sus alternativas;
  - los eventos del nivel siguiente son los hijos de cada regla;
  - el `EXITO` o `FALLO` final cierra el nodo.

  Después lo dibuja con `├─ └─ │` y marca cada meta y cada regla con ✔ o ✘.
- **Colores:** códigos ANSI que solo se activan si la salida es una terminal
  (`sys.stdout.isatty()`). `sin_color()` los quita para el archivo exportado. Las funciones
  `rellenar()` y `centrar()` miden el ancho **visible**, sin los códigos, para que las tablas
  queden alineadas.
- **`exportar_traza(ruta, motor)`:** guarda la traza en `.json` (datos crudos) o en `.txt`
  (texto formateado, sin colores).

---

## 10. Programa principal y casos clínicos

`main()`:

1. Fuerza UTF-8 en la salida, porque la consola de Windows usa cp1252 y fallaría con ✔ y ✘.
2. Activa los colores si corresponde.
3. Carga la KB (si falla, termina con código 1).
4. Imprime el encabezado y la auditoría.
5. Para cada caso de `CASOS_CLINICOS` llama a `ejecutar_caso()`, que ejecuta **ambos** motores,
   imprime sus trazas y compara los dos resultados con el `esperado`.
6. Imprime la tabla resumen, exporta todo sin colores a `trazas_casos_clinicos.txt` y retorna 0
   o 2.

| # | Caso | Δ (síntomas) | α (objetivo) | Esperado | Disparos (adelante) | Reglas intentadas (atrás) | Ilustra |
|---|---|---|---|---|---|---|---|
| 1 | Choque pediátrico | Manos_Frias, Relleno_Capilar_Mayor_3s, Pulso_Debil_Rapido, Contexto_Pediatrico | Alerta_Roja_Circulatoria | ✔ | 4 | 4 | 4 niveles, una regla por nivel |
| 2 | Neumonía sin diferenciador | Fiebre, Tos, Dificultad_Respiratoria | Neumonia | ✘ | 4 | 4 | Fallo por falta del hecho diferenciador (es el caso de la plantilla) |
| 3 | Neumonía con alerta roja | caso 2 + Dolor_Toracico_Pleuritico, Dificultad_Respiratoria_Severa | Alerta_Roja_Respiratoria | ✔ | 10 | 6 | Diagnóstico + síntoma crítico → alerta |
| 4 | Exacerbación de asma | Tos, Dificultad_Respiratoria, Sibilancias, Dificultad_Respiratoria_Severa, Antecedente_Asma | Alerta_Roja_Respiratoria | ✔ | 7 | 14 | Hecho diferenciador |
| 5 | EPOC sin hipoxia | igual que el 4 pero con Antecedente_EPOC | Alerta_Roja_Respiratoria | ✘ | 6 | 24 | Un solo hecho cambia el resultado |
| 6 | Influenza | Fiebre, Tos, Fatiga, Mialgias | Influenza | ✔ | 8 | 4 | Diferenciador Mialgias |
| 7 | Resfriado común | Tos, Fatiga, Rinorrea, Estornudos | Resfriado_Comun | ✔ | 4 | 4 | Diferenciador nasal |

**Lectura de la tabla:** en el caso 3 el motor hacia atrás es más eficiente, porque solo usa las
6 reglas de la demostración, mientras que el de adelante dispara 10 (incluye hechos
irrelevantes como `Disnea_Febril`). En el caso 5 ocurre lo contrario: hacia atrás se intentan 24
reglas, porque hay que descartar las seis alternativas que concluyen la alerta, mientras que
hacia adelante bastan 6 disparos para llegar al punto fijo.

Para agregar un caso, basta con añadir un diccionario a `CASOS_CLINICOS` con `nombre`,
`ilustra`, `sintomas`, `objetivo` y `esperado`. Las pruebas lo incluyen automáticamente.

---

## 11. Pruebas automáticas (`test_motor.py`)

Son 43 pruebas con `unittest`, agrupadas en siete clases:

| Clase | Qué verifica |
|---|---|
| `TestBaseConocimiento` | Mínimo 50 reglas, forma de Horn, ids únicos, sin duplicados, sin ciclos, sin islas, profundidad ≥ 4, que todo objetivo final sea una alerta, metadatos consistentes y que el validador **sí** detecte problemas en una KB defectuosa |
| `TestEncadenamientoAdelante` | Objetivo en Δ, objetivo inexistente, Δ vacío, orden y niveles de la traza, parada temprana, que el punto fijo sea igual al cierre lógico, validez de cada disparo, reinicio de la memoria entre ejecuciones |
| `TestEncadenamientoAtras` | Casos base, orden de la derivación, que la derivación sea una prueba válida, fallo por hecho faltante, memoización, cortocircuito del Y |
| `TestRobustez` | Ciclo sin salida (termina), ciclo con salida, fallo por corte no memorizado, límite de profundidad (cadena de 100 reglas), KB inexistente, KB vacía, hechos mal escritos |
| `TestCasosClinicos` | Los 7 casos dan lo esperado en ambos motores; las alertas exitosas llegan al nivel 4 |
| `TestEquivalenciaMotores` | **300 combinaciones aleatorias** de síntomas (semilla fija 2026) × 5 objetivos cada una: ambos motores coinciden con un cierre lógico calculado de forma independiente |
| `TestPresentacion` | Tabla, árbol de éxito y de fallo, salida sin colores, exportación y `main()` completo con código 0 |

**¿Cómo sabemos que las pruebas sirven?** Se introdujeron errores a propósito en una copia del
motor y se comprobó que las pruebas los detectan:

| Error introducido | Detectado por |
|---|---|
| Quitar la detección de ciclos | `test_ciclo_sin_salida_termina` |
| Quitar la parada al alcanzar el objetivo | Casos clínicos, traza, equivalencia y otras |
| Memorizar todos los fallos, incluso los de un corte | `test_fallo_por_corte_no_se_memoiza` |

---

## 12. Preguntas probables en la sustentación

**¿Por qué los dos motores siempre dan el mismo resultado?**
Para cláusulas de Horn, tanto el encadenamiento hacia adelante como el encadenamiento hacia
atrás son correctos y completos: deducen exactamente lo que la KB implica. La prueba
`TestEquivalenciaMotores` lo verifica en 1500 consultas aleatorias.

**¿Qué pasa si la KB tiene un ciclo, por ejemplo A → B y B → A?**
Hacia adelante no hay problema: cada regla se dispara una sola vez (refracción), así que el
ciclo no se repite. Hacia atrás, el conjunto `camino` detecta que una meta reaparece en su propia
rama y corta esa rama. Además, `validar_kb()` reporta el ciclo y la KB real no tiene ninguno.

**¿Cuáles son los casos base del motor hacia atrás?**
Hecho observado, ya demostrado, ya refutado, ciclo, límite de profundidad y meta sin reglas que
la concluyan (tabla de la sección 7.2).

**¿Para qué el límite de profundidad si ya se detectan ciclos?**
Es una segunda protección que exige el enunciado. Con una KB acíclica el valor por defecto
(|R| + 1) nunca se alcanza, pero si alguien usa una KB enorme o mal formada, la recursión queda
acotada.

**¿Por qué el motor hacia adelante usa una «foto» de la memoria?**
Para que una ola solo use lo conocido al empezar. Así el número de ola coincide con el nivel
lógico del hecho y la traza muestra la estructura de la KB. Sin la foto, una regla podría usar un
hecho deducido en la misma ola y los niveles se mezclarían. El resultado final sería el mismo;
solo cambia el orden.

**¿Qué diferencia hay entre «paso» y «nivel» en la traza?**
El paso es el orden cronológico del disparo (1, 2, 3…). El nivel es la ola en que ocurrió, y
equivale a la distancia del hecho a los síntomas.

**¿Por qué el caso de la plantilla (Fiebre, Tos, Dificultad_Respiratoria → Neumonia) da falso?**
Porque en la KB la neumonía exige el hecho diferenciador `Dolor_Toracico_Pleuritico`. Fiebre,
tos y disnea son comunes a varias infecciones respiratorias. Es el caso 2 y el árbol hacia atrás
muestra exactamente qué falta.

**¿Por qué no se memoriza un fallo si hubo un corte?**
Porque ese fallo depende del camino recorrido, no de la KB. El ejemplo X/Y de la sección 7.3
muestra cómo memorizarlo produciría una respuesta incorrecta.

**¿Qué complejidad tiene cada motor?**
Hacia adelante: O(|R|·k) por ola y O(|R|²·k) en el peor caso. Hacia atrás: O(|R|·k) gracias a la
memoización. Aquí |R| es el número de reglas y k el máximo de antecedentes por regla.

**¿Cuándo conviene cada motor?**
Hacia adelante, para descubrir todo lo que implican unos síntomas, por ejemplo al monitorear a
un paciente. Hacia atrás, para confirmar o descartar una hipótesis concreta, porque explora solo
lo relevante. Los casos 3 y 5 muestran que ninguno es siempre más eficiente.

**¿Cómo se garantiza la forma de Horn?**
El JSON solo admite una lista de antecedentes (conjunción) y **un** consecuente de tipo texto. No
hay forma de escribir «o» ni negaciones. La prueba `test_forma_de_horn` lo verifica regla por
regla.

**¿Cómo se verificó que no hay «islas»?**
Se ejecuta el encadenamiento hacia adelante con **todos** los hechos base a la vez; si una regla
no se dispara ni así, es inalcanzable. Además, todo objetivo final es una alerta, así que ningún
hecho intermedio queda sin salida.

**¿Se usó IA para crear la KB? ¿Cómo se auditó?**
Sí, como apoyo para proponer reglas. Se auditó con revisión manual frente a las fuentes (OMS y
Kaggle), con `validar_kb()` y con los casos y pruebas. La auditoría encontró y corrigió los
problemas de la sección 4.6.

**¿Por qué se guardan los antecedentes en un `set`?**
Porque la condición de disparo, «todos los antecedentes son conocidos», se convierte en una
inclusión de conjuntos (`<=`), que es directa y eficiente. Además, los duplicados no importan.

**¿Qué es el «mundo cerrado»?**
Lo que no se observó ni se puede deducir se toma como falso. Por eso el sistema no puede afirmar
«no tiene fiebre», solo «no se sabe que tenga fiebre».

---

## 13. Guion para la demostración en vivo

1. **Pruebas primero** (unos 2 s): muestra que todo funciona.
   ```bash
   python -m unittest -v test_motor
   ```
2. **Programa completo:**
   ```bash
   python proyecto_inferencia_final.py
   ```
   Señala en este orden:
   - La auditoría con sus cuatro ✔.
   - **Caso 1:** la tabla con una regla por nivel y el árbol lineal.
   - **Caso 2:** el árbol hacia atrás que termina en `Dolor_Toracico_Pleuritico ✘`.
   - **Casos 4 y 5:** mismos síntomas, distinto antecedente, distinto resultado.
   - La **tabla resumen** con 7/7.
3. **Consulta improvisada** (si el profesor propone síntomas), desde Python:
   ```python
   from proyecto_inferencia_final import MotorInferencia
   m = MotorInferencia("base_conocimiento.json")

   m.ejecutar_inferencia(["Fiebre", "Tos", "Fatiga", "Mialgias"], "Influenza")      # True
   print(m.formatear_traza("adelante"))

   m.ejecutar_inferencia_atras(["Fiebre", "Tos", "Fatiga"], "Influenza")             # False
   print(m.formatear_traza("atras"))      # el árbol muestra que faltan las mialgias

   m.hechos_desconocidos(["fiebre"])      # ['fiebre'] -> error de digitación
   ```
4. **Robustez ante ciclos** (si lo preguntan): crear una KB con `A → B` y `B → A` y mostrar que
   ambos motores terminan, como hace `test_ciclo_sin_salida_termina`.

---

## 14. Limitaciones

- Lógica binaria: sin probabilidades ni grados de certeza.
- Sin negación: no se puede expresar «ausencia de fiebre».
- Mundo cerrado: un síntoma no registrado se trata como falso.
- Las alertas son etiquetas pedagógicas inspiradas en la OMS, no una clasificación oficial de
  triaje. En un sistema real, un signo crítico debería alertar de inmediato sin recorrer cuatro
  niveles.
- El dataset de Kaggle es pequeño y ambiguo; los hechos diferenciadores salen de fuentes
  clínicas, no del dataset.

**Posibles mejoras:** factores de certeza, más enfermedades, encadenamiento hacia atrás
interactivo que pregunte al usuario por los síntomas que faltan, e interfaz gráfica.
