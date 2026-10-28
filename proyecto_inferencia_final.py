import json
import os
import re
import shutil
import sys
import textwrap

# ==========================================================
# PARTE 1: ESTRUCTURA DE DATOS (NO MODIFICAR)
# ==========================================================
class Regla:
    def __init__(self, id_regla, antecedentes, consecuente):
        self.id_regla = id_regla
        self.antecedentes = set(antecedentes)  
        self.consecuente = consecuente

    def __str__(self):
        return f"{self.id_regla}: {' AND '.join(self.antecedentes)} -> {self.consecuente}"

class MotorInferencia:
    def __init__(self, ruta_kb):
        self.reglas = self.cargar_kb(ruta_kb)
        self.memoria_trabajo = set()
        self.traza_explicacion = [] # Sugerencia para almacenar el orden de las reglas activadas

    def cargar_kb(self, ruta):
        """Carga las reglas desde un archivo JSON."""
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                datos = json.load(f)
            return [Regla(r.get('id'), r['antecedentes'], r['consecuente']) for r in datos['reglas']]
        except Exception as e:
            print(f"Error al cargar la Base de Conocimiento: {e}")
            return []

    # ==========================================================
    # PARTE 2: MOTORES DE INFERENCIA (DESARROLLADOS)
    # ==========================================================

    # ----------------------------------------------------------
    # Utilidades internas
    # ----------------------------------------------------------
    def _construir_indice(self):
        """
        Índice consecuente -> [reglas que lo concluyen].
        Permite que el encadenamiento hacia atrás encuentre en O(1) las
        reglas candidatas para un sub-objetivo (en vez de recorrer toda la KB).
        """
        indice = {}
        for regla in self.reglas:
            indice.setdefault(regla.consecuente, []).append(regla)
        return indice

    # ----------------------------------------------------------
    # A. MOTOR HACIA ADELANTE (Forward Chaining, data-driven)
    # ----------------------------------------------------------
    def ejecutar_inferencia(self, hechos_iniciales, objetivo):
        """
        Motor de Encadenamiento hacia Adelante (Forward Chaining).

        Estrategia (punto fijo por "olas" de inferencia):
          1. La memoria de trabajo arranca con los hechos iniciales (Δ).
          2. En cada iteración se evalúan, contra una FOTO de la memoria,
             todas las reglas aún no disparadas cuyos antecedentes están
             contenidos en ella (antecedentes ⊆ memoria).
          3. Los consecuentes nuevos se agregan a la memoria y cada disparo
             se registra en la traza (orden cronológico).
          4. Se termina con ÉXITO apenas el objetivo entra a la memoria, o
             con FALLO cuando una iteración completa no produce ningún hecho
             nuevo (punto fijo: la memoria ya no cambia).

        Terminación garantizada: cada regla se dispara a lo sumo una vez y la
        memoria solo crece, por lo que el bucle termina aunque la KB tuviera
        ciclos (no entra en bucle infinito).

        Retorna True si KB ∪ Δ ⊨ objetivo, False en caso contrario.
        La traza queda en self.traza_explicacion.
        """
        self.memoria_trabajo = set(hechos_iniciales)
        self.traza_explicacion = []

        # Caso trivial: el objetivo ya está entre los hechos observados.
        if objetivo in self.memoria_trabajo:
            return True

        reglas_pendientes = list(self.reglas)  # reglas que aún no se evalúan como disparadas
        iteracion = 0
        paso = 0

        while True:
            iteracion += 1
            foto = set(self.memoria_trabajo)   # snapshot: una "ola" usa solo lo conocido al inicio
            aplicables = []
            siguen_pendientes = []

            for regla in reglas_pendientes:
                if regla.antecedentes <= foto:
                    aplicables.append(regla)       # se puede disparar en esta ola
                else:
                    siguen_pendientes.append(regla)

            reglas_pendientes = siguen_pendientes
            hubo_hechos_nuevos = False

            for regla in aplicables:
                # Si otra regla de esta misma ola ya produjo el consecuente, es redundante.
                if regla.consecuente in self.memoria_trabajo:
                    continue

                self.memoria_trabajo.add(regla.consecuente)
                hubo_hechos_nuevos = True
                paso += 1
                self.traza_explicacion.append({
                    "tipo": "DISPARO",
                    "paso": paso,
                    "iteracion": iteracion,
                    "regla": regla.id_regla,
                    "antecedentes": sorted(regla.antecedentes),
                    "consecuente": regla.consecuente,
                })

                if regla.consecuente == objetivo:   # objetivo alcanzado: éxito
                    return True

            if not hubo_hechos_nuevos:              # punto fijo: no se infiere nada más
                return False

    # ----------------------------------------------------------
    # B. MOTOR HACIA ATRÁS (Backward Chaining, goal-driven)
    # ----------------------------------------------------------
    def ejecutar_inferencia_atras(self, hechos_iniciales, objetivo, max_profundidad=None):
        """
        Motor de Encadenamiento hacia Atrás (Backward Chaining).

        Estrategia (búsqueda en profundidad recursiva AND/OR):
          - OR: para probar un objetivo se prueba CUALQUIERA de las reglas
                que lo tienen como consecuente.
          - AND: para que una regla sirva, deben probarse TODOS sus
                antecedentes, cada uno como sub-objetivo recursivo.

        Casos base y controles (robustez):
          1. Hecho observado (meta ∈ Δ)             -> True.
          2. Meta ya demostrada antes (memo éxito)  -> True (evita recalcular).
          3. Meta ya refutada antes (memo fallo)    -> False.
          4. Ciclo (meta ya está en el camino actual) -> False. Evita
             bucles infinitos si la KB tuviera ciclos A->B, B->A.
          5. Meta sin reglas que la concluyan y que no es hecho -> False.
          6. Profundidad > max_profundidad          -> False (corte de seguridad).
             Por defecto = nº de reglas + 1: en una KB acíclica ninguna cadena
             de prueba puede ser más larga que eso.

        Retorna True si KB ∪ Δ ⊢ objetivo. El registro de la búsqueda queda en
        self.traza_explicacion y la derivación final (reglas en orden
        ascendente, de síntomas a objetivo) en self.derivacion.
        """
        hechos = set(hechos_iniciales)
        self.memoria_trabajo = set(hechos)
        self.traza_explicacion = []
        self.derivacion = []

        # Estado de la búsqueda
        self._indice = self._construir_indice()
        self._memo_exito = {}      # hecho -> regla que lo probó (None si es hecho observado)
        self._memo_fallo = set()   # hechos demostrablemente no derivables
        self._cortes = 0           # nº de ramas cortadas por ciclo/profundidad (afecta a la memoización de fallos)
        self._max_prof = max_profundidad if max_profundidad is not None else len(self.reglas) + 1

        resultado = self._probar(objetivo, hechos, set(), 0)

        if resultado:
            self.derivacion = self._reconstruir_derivacion(objetivo)
        return resultado

    def _log(self, nivel, tipo, texto, regla=None):
        """Registra un evento de la búsqueda hacia atrás en la traza."""
        self.traza_explicacion.append({
            "tipo": tipo, "nivel": nivel, "regla": regla, "texto": texto
        })

    def _probar(self, meta, hechos, camino, nivel):
        """
        Intenta demostrar `meta`. `camino` contiene las metas en curso de la
        rama actual (detección de ciclos); `nivel` es la profundidad.
        """
        # --- Casos base ---------------------------------------------------
        if meta in hechos:
            self._memo_exito.setdefault(meta, None)
            self._log(nivel, "HECHO", f"{meta}: es un hecho observado ✔")
            return True
        if meta in self._memo_exito:
            self._log(nivel, "MEMO", f"{meta}: ya demostrado antes ✔")
            return True
        if meta in self._memo_fallo:
            self._log(nivel, "MEMO", f"{meta}: ya refutado antes ✘")
            return False
        if meta in camino:
            self._cortes += 1
            self._log(nivel, "CICLO", f"{meta}: ciclo detectado, se corta la rama ✘")
            return False
        if nivel > self._max_prof:
            self._cortes += 1
            self._log(nivel, "PROFUNDIDAD", f"{meta}: profundidad máxima ({self._max_prof}) superada ✘")
            return False

        candidatas = self._indice.get(meta, [])
        if not candidatas:
            self._memo_fallo.add(meta)
            self._log(nivel, "FALLO", f"{meta}: no es hecho observado y ninguna regla lo concluye ✘")
            return False

        # --- Paso recursivo (OR sobre reglas, AND sobre antecedentes) ------
        self._log(nivel, "META", f"Probar {meta}")
        camino.add(meta)
        cortes_antes = self._cortes

        for regla in candidatas:
            self._log(nivel, "REGLA",
                      f"Intentar {regla.id_regla}: {' AND '.join(sorted(regla.antecedentes))} -> {meta}",
                      regla=regla.id_regla)
            # all() corta en el primer antecedente que falle (cortocircuito AND)
            if all(self._probar(a, hechos, camino, nivel + 1) for a in sorted(regla.antecedentes)):
                camino.discard(meta)
                self._memo_exito[meta] = regla
                self._log(nivel, "EXITO", f"{meta}: demostrado con {regla.id_regla} ✔", regla=regla.id_regla)
                return True

        camino.discard(meta)
        # Solo se memoiza el fallo si NO dependió de un corte por ciclo/profundidad
        # (un fallo causado por un corte depende del camino y no es definitivo).
        if self._cortes == cortes_antes:
            self._memo_fallo.add(meta)
        self._log(nivel, "FALLO", f"{meta}: ninguna regla pudo demostrarse ✘")
        return False

    def _reconstruir_derivacion(self, objetivo):
        """
        A partir de la memoización de éxitos reconstruye SOLO las reglas que
        forman parte de la prueba final, ordenadas de síntomas a objetivo
        (post-orden), equivalente a la traza del motor hacia adelante.
        """
        orden, vistos = [], set()

        def visitar(hecho):
            regla = self._memo_exito.get(hecho)
            if regla is None or hecho in vistos:   # hecho observado o ya visitado
                return
            vistos.add(hecho)
            for a in sorted(regla.antecedentes):
                visitar(a)
            orden.append(regla)

        visitar(objetivo)
        return orden

    # ----------------------------------------------------------
    # Presentación / exportación de la traza de explicación
    # ----------------------------------------------------------
    def formatear_traza(self, motor="adelante", sangria="   "):
        """
        Devuelve la traza de la última inferencia como texto.
        motor = "adelante" -> tabla cronológica de disparos (paso, nivel, regla, ...).
        motor = "atras"    -> derivación final + árbol de búsqueda con conectores.
        """
        if motor == "adelante":
            lineas = self._tabla_adelante()
        else:
            lineas = [negrita("Derivación") + tenue("  (de síntomas a objetivo)")]
            derivacion = getattr(self, "derivacion", [])
            if not derivacion:
                lineas.append(tenue("  (sin derivación: objetivo no demostrado o ya era un hecho inicial)"))
            for i, r in enumerate(derivacion, 1):
                lineas.append(f"  {i:>2}. {cian(f'{r.id_regla:<5}')} "
                              f"{' ∧ '.join(sorted(r.antecedentes))}  →  {negrita(r.consecuente)}")
            lineas.append("")
            lineas.append(negrita("Árbol de búsqueda") + tenue("  (dirigido por el objetivo)"))
            lineas += self._arbol_busqueda()
        return "\n".join(sangria + l if l else l for l in lineas)

    def _tabla_adelante(self):
        """Tabla alineada de los disparos del motor hacia adelante."""
        traza = self.traza_explicacion
        if not traza:
            return [tenue("(sin disparos: el objetivo ya era un hecho inicial o no se activó ninguna regla)")]
        ancho_hecho = max(len("Hecho nuevo"), max(len(e["consecuente"]) for e in traza))
        ancho_ant = max(28, ANCHO - 6 - 22 - ancho_hecho)
        cab = f"{'Paso':>4}  {'Nivel':>5}  {'Regla':<5}  {'Antecedentes':<{ancho_ant}}  {'Hecho nuevo'}"
        lineas = [negrita(cab), tenue(f"{'─' * 4}  {'─' * 5}  {'─' * 5}  {'─' * ancho_ant}  {'─' * ancho_hecho}")]
        for e in traza:
            partes = textwrap.wrap(" ∧ ".join(e["antecedentes"]), ancho_ant) or [""]
            regla = cian(e["regla"].ljust(5))
            lineas.append(f"{e['paso']:>4}  {e['iteracion']:>5}  {regla}  "
                          f"{partes[0]:<{ancho_ant}}  {e['consecuente']}")
            for extra in partes[1:]:
                lineas.append(f"{'':>4}  {'':>5}  {'':<5}  {extra}")
        return lineas

    def _arbol_busqueda(self):
        """
        Reconstruye el árbol Y/O a partir de la traza plana del motor hacia atrás
        (cada evento trae su nivel) y lo dibuja con conectores ├─ └─ │.
        """
        eventos = self.traza_explicacion
        detalle_hoja = {
            "HECHO": "hecho observado", "CICLO": "ciclo detectado: rama cortada",
            "PROFUNDIDAD": "límite de profundidad superado",
            "FALLO": "no observado y ninguna regla lo concluye",
        }

        def leer(i):
            e = eventos[i]
            if e["tipo"] != "META":                         # hoja: caso base
                meta = e["texto"].split(":", 1)[0]
                if e["tipo"] == "MEMO":
                    ok = "demostrado" in e["texto"]
                    detalle = "ya demostrado (memoria)" if ok else "ya refutado (memoria)"
                else:
                    ok = e["tipo"] == "HECHO"
                    detalle = detalle_hoja.get(e["tipo"], "")
                return {"meta": meta, "hoja": True, "ok": ok, "detalle": detalle}, i + 1
            nivel, meta = e["nivel"], e["texto"][len("Probar "):]
            i += 1
            reglas = []
            while eventos[i]["tipo"] == "REGLA" and eventos[i]["nivel"] == nivel:
                cuerpo = eventos[i]["texto"].split(": ", 1)[1].split(" -> ")[0]
                regla = {"id": eventos[i]["regla"], "ants": cuerpo.replace(" AND ", " ∧ "),
                         "hijos": [], "ok": False}
                i += 1
                while i < len(eventos) and eventos[i]["nivel"] == nivel + 1:
                    hijo, i = leer(i)
                    regla["hijos"].append(hijo)
                reglas.append(regla)
            fin = eventos[i]                                # EXITO o FALLO de esta meta
            ok = fin["tipo"] == "EXITO"
            if ok:
                reglas[-1]["ok"] = True
            return {"meta": meta, "hoja": False, "ok": ok, "regla": fin.get("regla"), "reglas": reglas}, i + 1

        def dibujar(nodo, prefijo, ultimo, raiz, salida):
            conector = "" if raiz else ("└─ " if ultimo else "├─ ")
            marca = OK() if nodo["ok"] else NO()
            if nodo["hoja"]:
                salida.append(f"{prefijo}{conector}{nodo['meta']}  {marca} {tenue(nodo['detalle'])}")
                return
            estado = f"demostrado con {nodo['regla']}" if nodo["ok"] else "no demostrable"
            salida.append(f"{prefijo}{conector}{negrita(nodo['meta'])}  {marca} {estado}")
            base = prefijo + ("" if raiz else ("   " if ultimo else "│  "))
            for k, regla in enumerate(nodo["reglas"]):
                ult_regla = k == len(nodo["reglas"]) - 1
                salida.append(f"{base}{'└─ ' if ult_regla else '├─ '}{cian(regla['id'])}: "
                              f"{tenue(regla['ants'])}  {OK() if regla['ok'] else NO()}")
                sub = base + ("   " if ult_regla else "│  ")
                for j, hijo in enumerate(regla["hijos"]):
                    dibujar(hijo, sub, j == len(regla["hijos"]) - 1, False, salida)

        if not eventos:
            return [tenue("(sin eventos)")]
        raiz, _ = leer(0)
        salida = []
        dibujar(raiz, "", True, True, salida)
        return salida

    def exportar_traza(self, ruta, motor="adelante"):
        """Exporta la traza a un archivo (.json o texto plano según la extensión)."""
        with open(ruta, "w", encoding="utf-8") as f:
            if ruta.lower().endswith(".json"):
                json.dump(self.traza_explicacion, f, ensure_ascii=False, indent=2)
            else:
                f.write(sin_color(self.formatear_traza(motor)))

    # ----------------------------------------------------------
    # Auditoría de la KB (restricciones lógicas 3.2 del enunciado)
    # ----------------------------------------------------------
    def validar_kb(self):
        """
        Verifica: ids duplicados, aciclicidad, hechos base, hechos terminales
        y profundidad de inferencia (nivel mínimo de cada hecho derivado).
        Devuelve un diccionario con el resultado.
        """
        indice = self._construir_indice()
        consecuentes = set(indice)
        antecedentes = set().union(*[r.antecedentes for r in self.reglas]) if self.reglas else set()
        hechos_base = antecedentes - consecuentes
        terminales = consecuentes - antecedentes

        ids = [r.id_regla for r in self.reglas]
        duplicados = sorted({i for i in ids if ids.count(i) > 1})

        # Detección de ciclos con DFS (blanco/gris/negro)
        estado, ciclos = {}, []
        def dfs(hecho, camino):
            if estado.get(hecho) == 1:
                ciclos.append(camino + [hecho]); return
            if estado.get(hecho) == 2:
                return
            estado[hecho] = 1
            for r in indice.get(hecho, []):
                for a in r.antecedentes:
                    dfs(a, camino + [hecho])
            estado[hecho] = 2
        for c in consecuentes:
            dfs(c, [])

        # Profundidad mínima: nº de niveles lógicos necesarios para derivar el hecho
        profundidad = {}
        if not ciclos:
            def prof(h):
                if h in profundidad: return profundidad[h]
                if h not in indice:
                    profundidad[h] = 0
                else:
                    profundidad[h] = 1 + min(max(prof(a) for a in r.antecedentes) for r in indice[h])
                return profundidad[h]
            for h in consecuentes:
                prof(h)

        # Alcanzabilidad (sin "islas"): con TODOS los hechos base en memoria, cada
        # regla debe poder dispararse en algún momento (punto fijo del encadenamiento).
        memoria, disparadas, cambio = set(hechos_base), set(), True
        while cambio:
            cambio = False
            for r in self.reglas:
                if r.id_regla not in disparadas and r.antecedentes <= memoria:
                    disparadas.add(r.id_regla)
                    memoria.add(r.consecuente)
                    cambio = True
        inalcanzables = [r.id_regla for r in self.reglas if r.id_regla not in disparadas]

        return {
            "n_reglas": len(self.reglas),
            "ids_duplicados": duplicados,
            "ciclos": ciclos,
            "hechos_base": sorted(hechos_base),
            "terminales": sorted(terminales),
            "terminales_menor_nivel_4": sorted(t for t in terminales if profundidad.get(t, 0) < 4),
            "profundidad_maxima": max(profundidad.values()) if profundidad else 0,
            "reglas_inalcanzables": inalcanzables,
        }

    def hechos_desconocidos(self, hechos):
        """Devuelve los hechos que no aparecen en ninguna regla (posibles errores de digitación)."""
        conocidos = set()
        for r in self.reglas:
            conocidos |= r.antecedentes
            conocidos.add(r.consecuente)
        return sorted(set(hechos) - conocidos)

# ==========================================================
# Utilidades de presentación en consola
# ==========================================================
# Ancho de las tablas: el de la terminal, acotado para que el archivo exportado sea legible.
ANCHO = max(90, min(shutil.get_terminal_size((110, 24)).columns, 120)) - 4
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_COLOR = False   # se activa en main() solo si la salida es una terminal


def activar_color(activar):
    """Activa los colores ANSI (en Windows también habilita las secuencias en la consola)."""
    global _COLOR
    _COLOR = activar
    if activar and os.name == "nt":
        os.system("")


def _c(codigo, texto):
    return f"\x1b[{codigo}m{texto}\x1b[0m" if _COLOR else str(texto)


def negrita(t): return _c("1", t)
def tenue(t):   return _c("2", t)
def verde(t):   return _c("32", t)
def rojo(t):    return _c("31", t)
def amarillo(t): return _c("33", t)
def cian(t):    return _c("36", t)
def OK():       return verde("✔")
def NO():       return rojo("✘")


def sin_color(texto):
    """Quita los códigos ANSI (para exportar a archivo)."""
    return _ANSI.sub("", texto)


def rellenar(texto, ancho):
    """ljust que ignora los códigos ANSI al medir el ancho visible."""
    return texto + " " * max(0, ancho - len(sin_color(texto)))


def centrar(texto, ancho):
    """center que ignora los códigos ANSI."""
    visible = len(sin_color(texto))
    izq = max(0, ancho - visible) // 2
    return " " * izq + texto + " " * max(0, ancho - visible - izq)


def titulo_caja(texto, doble=False):
    """Título dentro de un recuadro que ocupa todo el ancho."""
    h, v, a, b, c, d = ("═", "║", "╔", "╗", "╚", "╝") if doble else ("─", "│", "┌", "┐", "└", "┘")
    interior = ANCHO - 2
    return "\n".join([a + h * interior + b,
                      v + rellenar(" " + negrita(texto), interior) + v,
                      c + h * interior + d])


def seccion(texto):
    return f"\n{negrita(texto)}\n{tenue('─' * ANCHO)}"


def lista_hechos(hechos, sangria):
    """Lista de hechos separada por comas, ajustada al ancho disponible."""
    return textwrap.fill(", ".join(hechos), ANCHO - len(sangria),
                         subsequent_indent=sangria)


# ==========================================================
# PARTE 3: EJECUCIÓN (PUEDEN MODIFICAR PARA PRUEBAS)
# ==========================================================
# El orden sigue el del informe técnico: (1) profundidad de 4 niveles, (2) fallo por
# ausencia del hecho diferenciador, (3) diagnóstico + síntoma crítico -> alerta.
# "esperado" es el resultado clínicamente correcto; se compara con ambos motores.
CASOS_CLINICOS = [
    {
        "nombre": "Choque pediátrico",
        "ilustra": "Profundidad de 4 niveles: una regla por nivel",
        "sintomas": ["Manos_Frias", "Relleno_Capilar_Mayor_3s", "Pulso_Debil_Rapido",
                     "Contexto_Pediatrico"],
        "objetivo": "Alerta_Roja_Circulatoria",
        "esperado": True,
    },
    {
        "nombre": "Neumonía sin diferenciador",
        "ilustra": "Fallo por ausencia de Dolor_Toracico_Pleuritico",
        "sintomas": ["Fiebre", "Tos", "Dificultad_Respiratoria"],
        "objetivo": "Neumonia",
        "esperado": False,
    },
    {
        "nombre": "Neumonía con alerta roja",
        "ilustra": "Diagnóstico inferido + síntoma crítico → estado de alerta",
        "sintomas": ["Fiebre", "Tos", "Dificultad_Respiratoria",
                     "Dolor_Toracico_Pleuritico", "Dificultad_Respiratoria_Severa"],
        "objetivo": "Alerta_Roja_Respiratoria",
        "esperado": True,
    },
    {
        "nombre": "Exacerbación de asma",
        "ilustra": "Hecho diferenciador Antecedente_Asma (comparar con el caso 5)",
        "sintomas": ["Tos", "Dificultad_Respiratoria", "Sibilancias",
                     "Dificultad_Respiratoria_Severa", "Antecedente_Asma"],
        "objetivo": "Alerta_Roja_Respiratoria",
        "esperado": True,
    },
    {
        "nombre": "EPOC sin hipoxia",
        "ilustra": "Sin signos de hipoxia la exacerbación de EPOC no genera alerta roja",
        "sintomas": ["Tos", "Dificultad_Respiratoria", "Sibilancias",
                     "Dificultad_Respiratoria_Severa", "Antecedente_EPOC"],
        "objetivo": "Alerta_Roja_Respiratoria",
        "esperado": False,
    },
    {
        "nombre": "Influenza",
        "ilustra": "Hecho diferenciador Mialgias",
        "sintomas": ["Fiebre", "Tos", "Fatiga", "Mialgias"],
        "objetivo": "Influenza",
        "esperado": True,
    },
    {
        "nombre": "Resfriado común",
        "ilustra": "Hechos diferenciadores Rinorrea + Estornudos",
        "sintomas": ["Tos", "Fatiga", "Rinorrea", "Estornudos"],
        "objetivo": "Resfriado_Comun",
        "esperado": True,
    },
]


def texto_auditoria(motor, ruta_kb):
    """Bloque de auditoría de la KB (restricciones de la sección 3.2 del enunciado)."""
    v = motor.validar_kb()
    def chequeo(ok, texto_ok, texto_falla, detalle):
        return f"  {OK()} {texto_ok}" if ok else f"  {NO()} {texto_falla}: {rojo(detalle)}"
    lineas = [seccion("AUDITORÍA DE LA BASE DE CONOCIMIENTO"),
              f"  Archivo               {ruta_kb}",
              f"  Reglas                {v['n_reglas']}",
              f"  Hechos base           {len(v['hechos_base'])}",
              f"  Objetivos finales     {len(v['terminales'])}",
              f"  Profundidad máxima    {v['profundidad_maxima']}",
              "",
              chequeo(not v["ids_duplicados"], "Sin identificadores duplicados",
                      "Identificadores duplicados", v["ids_duplicados"]),
              chequeo(not v["ciclos"], "Sin ciclos (aciclicidad)", "Ciclos", v["ciclos"]),
              chequeo(not v["reglas_inalcanzables"], "Todas las reglas son alcanzables (sin islas)",
                      "Reglas inalcanzables", v["reglas_inalcanzables"]),
              chequeo(not v["terminales_menor_nivel_4"], "Todos los objetivos finales tienen profundidad ≥ 4",
                      "Objetivos con profundidad < 4", v["terminales_menor_nivel_4"])]
    return "\n".join(lineas)


def ejecutar_caso(motor, numero, total, caso):
    """Ejecuta ambos motores sobre un caso y devuelve (texto, resumen)."""
    sintomas, objetivo, esperado = caso["sintomas"], caso["objetivo"], caso["esperado"]
    def veredicto(r):
        return f"{OK()} {verde('DEMOSTRADO')}" if r else f"{NO()} {rojo('NO SE DERIVA')}"

    lineas = ["", titulo_caja(f"CASO {numero} de {total} · {caso['nombre']}"),
              f"  {tenue('Ilustra')}       {caso['ilustra']}",
              f"  {tenue('Síntomas (Δ)')}  {lista_hechos(sintomas, ' ' * 16)}",
              f"  {tenue('Objetivo (α)')}  {negrita(objetivo)}",
              f"  {tenue('Esperado')}      {'demostrable' if esperado else 'no demostrable'}"]
    desconocidos = motor.hechos_desconocidos(sintomas)
    if desconocidos:
        lineas.append(f"  {amarillo('Aviso')}: hechos que no aparecen en la KB "
                      f"(¿error de digitación?): {', '.join(desconocidos)}")

    # --- Motor hacia adelante ---
    r_adelante = motor.ejecutar_inferencia(sintomas, objetivo)
    traza = motor.traza_explicacion
    disparos = len(traza)
    olas = max((e["iteracion"] for e in traza), default=0)
    detalle = (f"{disparos} reglas disparadas, objetivo en el nivel {olas}" if r_adelante
               else f"{disparos} reglas disparadas, punto fijo en la ola {olas + 1}")
    lineas += ["", f"  {negrita('▶ Encadenamiento hacia adelante')}   {veredicto(r_adelante)}  {tenue('(' + detalle + ')')}",
               "", motor.formatear_traza("adelante", sangria="     ")]

    # --- Motor hacia atrás ---
    r_atras = motor.ejecutar_inferencia_atras(sintomas, objetivo)
    intentadas = sum(1 for e in motor.traza_explicacion if e["tipo"] == "REGLA")
    lineas += ["", f"  {negrita('▶ Encadenamiento hacia atrás')}      {veredicto(r_atras)}  "
                   f"{tenue(f'({intentadas} reglas intentadas, {len(motor.derivacion)} en la demostración)')}",
               "", motor.formatear_traza("atras", sangria="     ")]

    # --- Consistencia ---
    correcto = r_adelante == r_atras == esperado
    if correcto:
        lineas += ["", f"  {OK()} {verde('Ambos motores coinciden con el resultado esperado')}"]
    else:
        lineas += ["", f"  {NO()} {rojo('DISCREPANCIA')}: adelante={r_adelante}, atrás={r_atras}, esperado={esperado}"]
    resumen = {"numero": numero, "nombre": caso["nombre"], "objetivo": objetivo, "esperado": esperado,
               "adelante": r_adelante, "atras": r_atras, "disparos": disparos,
               "intentadas": intentadas, "correcto": correcto}
    return "\n".join(lineas), resumen


def texto_resumen(resumenes):
    """Tabla final con el resultado de todos los casos."""
    sn = lambda b: OK() if b else NO()
    ancho_nombre = max(len(r["nombre"]) for r in resumenes)
    ancho_obj = max(len("Objetivo"), max(len(r["objetivo"]) for r in resumenes))
    cab = (f"  {'#':>2}  {'Caso':<{ancho_nombre}}  {'Objetivo':<{ancho_obj}}  "
           f"Esp.  Adel.  Atrás  Disp.  Int.  Estado")
    lineas = [seccion("RESUMEN DE CASOS CLÍNICOS"), negrita(cab),
              tenue("  " + "─" * (len(cab) - 2))]
    for r in resumenes:
        estado = verde("OK") if r["correcto"] else rojo("FALLA")
        lineas.append(f"  {r['numero']:>2}  {r['nombre']:<{ancho_nombre}}  {r['objetivo']:<{ancho_obj}}  "
                      f"{centrar(sn(r['esperado']), 4)}  {centrar(sn(r['adelante']), 5)}  {centrar(sn(r['atras']), 5)}  "
                      f"{r['disparos']:>5}  {r['intentadas']:>4}  {estado}")
    correctos = sum(r["correcto"] for r in resumenes)
    total = len(resumenes)
    color = verde if correctos == total else rojo
    lineas += ["", "  " + color(negrita(f"{correctos}/{total} casos correctos"))
               + tenue("   (Disp.: disparos hacia adelante · Int.: reglas intentadas hacia atrás)")]
    return "\n".join(lineas)


def main(argv):
    """Punto de entrada: auditoría de la KB, casos clínicos, resumen y exportación."""
    # En Windows la consola/redirección usa cp1252 y falla con ✔/✘: se fuerza UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    activar_color(sys.stdout.isatty() and "NO_COLOR" not in os.environ)

    # 1. Inicializar el motor con el archivo de reglas (ruta opcional por argumento)
    ruta_kb = argv[1] if len(argv) > 1 else "base_conocimiento.json"
    motor = MotorInferencia(ruta_kb)
    if not motor.reglas:
        return 1

    # 2. Encabezado y auditoría de la KB
    bloques = [titulo_caja("SISTEMA EXPERTO DE DIAGNÓSTICO · Motor de inferencia con cláusulas de Horn", doble=True),
               texto_auditoria(motor, ruta_kb)]

    # 3. Ejecutar todos los casos clínicos con ambos motores
    resumenes = []
    for n, caso in enumerate(CASOS_CLINICOS, 1):
        texto, resumen = ejecutar_caso(motor, n, len(CASOS_CLINICOS), caso)
        bloques.append(texto)
        resumenes.append(resumen)

    # 4. Resumen y exportación de las trazas para el informe técnico (sin colores)
    bloques.append(texto_resumen(resumenes))
    salida = "\n".join(bloques)
    ruta_trazas = "trazas_casos_clinicos.txt"
    with open(ruta_trazas, "w", encoding="utf-8") as f:
        f.write(sin_color(salida) + "\n")
    print(salida)
    print(f"\n  {tenue('Trazas exportadas a')} {ruta_trazas}\n")

    # Código de salida distinto de 0 si algún caso no coincide (útil para automatizar)
    return 0 if all(r["correcto"] for r in resumenes) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
