"""
Pruebas automáticas del motor de inferencia y de la base de conocimiento.

Ejecutar desde la carpeta del proyecto:
    python -m unittest -v test_motor

Grupos de pruebas:
  1. Base de conocimiento: restricciones del enunciado (Horn, aciclicidad,
     alcanzabilidad, profundidad >= 4, mínimo 50 reglas).
  2. Motor hacia adelante: casos triviales, orden de la traza, punto fijo.
  3. Motor hacia atrás: casos base, derivación válida, memoización.
  4. Robustez: ciclos, límite de profundidad, KB vacía o inexistente.
  5. Casos clínicos: ambos motores dan el resultado esperado.
  6. Equivalencia: en cientos de combinaciones aleatorias de síntomas ambos
     motores coinciden con el cierre lógico calculado de forma independiente.
  7. Presentación: formato de las trazas y exportación.
"""
import contextlib
import io
import json
import os
import random
import tempfile
import unittest

import proyecto_inferencia_final as pif
from proyecto_inferencia_final import MotorInferencia

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_KB = os.path.join(CARPETA, "base_conocimiento.json")


def kb_temporal(reglas):
    """Crea un archivo JSON temporal con las reglas dadas [(id, [antecedentes], consecuente)]."""
    datos = {"reglas": [{"id": i, "antecedentes": a, "consecuente": c} for i, a, c in reglas]}
    descriptor, ruta = tempfile.mkstemp(suffix=".json")
    with os.fdopen(descriptor, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    return ruta


def motor_temporal(test, reglas):
    """MotorInferencia sobre una KB temporal que se borra al terminar la prueba."""
    ruta = kb_temporal(reglas)
    test.addCleanup(os.remove, ruta)
    return MotorInferencia(ruta)


def cierre_logico(reglas, hechos):
    """Cierre por modus ponens calculado de forma independiente al motor (referencia)."""
    memoria = set(hechos)
    cambio = True
    while cambio:
        cambio = False
        for r in reglas:
            if r.antecedentes <= memoria and r.consecuente not in memoria:
                memoria.add(r.consecuente)
                cambio = True
    return memoria


# ----------------------------------------------------------------------
# 1. Base de conocimiento
# ----------------------------------------------------------------------
class TestBaseConocimiento(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.motor = MotorInferencia(RUTA_KB)
        cls.validacion = cls.motor.validar_kb()
        with open(RUTA_KB, encoding="utf-8") as f:
            cls.json = json.load(f)

    def test_minimo_50_reglas(self):
        self.assertGreaterEqual(len(self.motor.reglas), 50)

    def test_forma_de_horn(self):
        """Antecedentes: lista no vacía de textos; consecuente: un único texto positivo."""
        for r in self.json["reglas"]:
            with self.subTest(regla=r["id"]):
                self.assertIsInstance(r["antecedentes"], list)
                self.assertTrue(r["antecedentes"])
                self.assertTrue(all(isinstance(a, str) and a for a in r["antecedentes"]))
                self.assertIsInstance(r["consecuente"], str)
                self.assertNotIn(r["consecuente"], r["antecedentes"])

    def test_ids_unicos(self):
        self.assertEqual(self.validacion["ids_duplicados"], [])

    def test_sin_reglas_duplicadas(self):
        firmas = [(frozenset(r.antecedentes), r.consecuente) for r in self.motor.reglas]
        self.assertEqual(len(firmas), len(set(firmas)))

    def test_aciclica(self):
        self.assertEqual(self.validacion["ciclos"], [])

    def test_todas_las_reglas_alcanzables(self):
        self.assertEqual(self.validacion["reglas_inalcanzables"], [])

    def test_objetivos_finales_profundidad_4(self):
        self.assertEqual(self.validacion["terminales_menor_nivel_4"], [])
        self.assertGreaterEqual(self.validacion["profundidad_maxima"], 4)

    def test_objetivos_finales_son_alertas(self):
        """Ningún hecho intermedio queda sin salida: todo terminal es un estado de alerta."""
        for t in self.validacion["terminales"]:
            with self.subTest(terminal=t):
                self.assertTrue(t.startswith("Alerta_"))

    def test_hechos_base_declarados_coinciden(self):
        self.assertEqual(sorted(self.json["hechos_base_permitidos"]), self.validacion["hechos_base"])

    def test_metadatos_consistentes(self):
        self.assertEqual(self.json["total_reglas"], len(self.json["reglas"]))
        por_nivel = {}
        for r in self.json["reglas"]:
            por_nivel[str(r["nivel"])] = por_nivel.get(str(r["nivel"]), 0) + 1
        declarado = {k: v for k, v in self.json["reglas_por_nivel"].items() if not k.startswith("_")}
        self.assertEqual(declarado, por_nivel)

    def test_validar_kb_detecta_problemas(self):
        """El validador sí reporta ciclos, ids repetidos e islas cuando existen."""
        motor = motor_temporal(self, [("R1", ["A"], "B"), ("R2", ["B"], "A"),
                                      ("R1", ["X"], "Y"), ("R3", ["Isla"], "Z"), ("R4", ["Z"], "Isla")])
        v = motor.validar_kb()
        self.assertTrue(v["ciclos"])
        self.assertEqual(v["ids_duplicados"], ["R1"])
        self.assertIn("R3", v["reglas_inalcanzables"])


# ----------------------------------------------------------------------
# 2. Motor hacia adelante
# ----------------------------------------------------------------------
class TestEncadenamientoAdelante(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.motor = MotorInferencia(RUTA_KB)

    def test_objetivo_en_los_hechos_iniciales(self):
        self.assertTrue(self.motor.ejecutar_inferencia(["Fiebre"], "Fiebre"))
        self.assertEqual(self.motor.traza_explicacion, [])

    def test_objetivo_inexistente(self):
        self.assertFalse(self.motor.ejecutar_inferencia(["Fiebre", "Tos"], "Hecho_Que_No_Existe"))

    def test_sin_hechos(self):
        self.assertFalse(self.motor.ejecutar_inferencia([], "Neumonia"))
        self.assertEqual(self.motor.traza_explicacion, [])

    def test_traza_cronologica_y_niveles(self):
        """Choque pediátrico: una regla por ola, en orden, de nivel 1 a 4."""
        self.assertTrue(self.motor.ejecutar_inferencia(
            ["Manos_Frias", "Relleno_Capilar_Mayor_3s", "Pulso_Debil_Rapido", "Contexto_Pediatrico"],
            "Alerta_Roja_Circulatoria"))
        traza = self.motor.traza_explicacion
        self.assertEqual([e["regla"] for e in traza], ["R27", "R58", "R86", "R102"])
        self.assertEqual([e["iteracion"] for e in traza], [1, 2, 3, 4])
        self.assertEqual([e["paso"] for e in traza], [1, 2, 3, 4])

    def test_parada_temprana(self):
        """El último disparo produce el objetivo: no se sigue infiriendo después."""
        self.motor.ejecutar_inferencia(["Fiebre", "Tos", "Fatiga", "Mialgias"], "Influenza")
        self.assertEqual(self.motor.traza_explicacion[-1]["consecuente"], "Influenza")

    def test_punto_fijo(self):
        """Sin el hecho diferenciador se agotan las reglas y se retorna fallo."""
        self.assertFalse(self.motor.ejecutar_inferencia(["Fiebre", "Tos", "Dificultad_Respiratoria"], "Neumonia"))
        self.assertNotIn("Neumonia", self.motor.memoria_trabajo)
        # La memoria final es exactamente el cierre lógico de los hechos.
        self.assertEqual(self.motor.memoria_trabajo,
                         cierre_logico(self.motor.reglas, ["Fiebre", "Tos", "Dificultad_Respiratoria"]))

    def test_traza_es_valida(self):
        """Cada disparo usa solo hechos iniciales o deducidos antes, y cada regla dispara una vez."""
        hechos = ["Fiebre", "Tos", "Dificultad_Respiratoria", "Dolor_Toracico_Pleuritico",
                  "Dificultad_Respiratoria_Severa"]
        self.motor.ejecutar_inferencia(hechos, "Alerta_Roja_Respiratoria")
        conocidos = set(hechos)
        reglas_usadas = []
        for e in self.motor.traza_explicacion:
            self.assertTrue(set(e["antecedentes"]) <= conocidos, e)
            self.assertNotIn(e["consecuente"], conocidos)
            conocidos.add(e["consecuente"])
            reglas_usadas.append(e["regla"])
        self.assertEqual(len(reglas_usadas), len(set(reglas_usadas)))

    def test_memoria_se_reinicia_entre_ejecuciones(self):
        self.motor.ejecutar_inferencia(["Fiebre", "Tos", "Fatiga", "Mialgias"], "Influenza")
        self.motor.ejecutar_inferencia(["Tos"], "Influenza")
        self.assertNotIn("Fiebre", self.motor.memoria_trabajo)
        self.assertNotIn("Influenza", self.motor.memoria_trabajo)


# ----------------------------------------------------------------------
# 3. Motor hacia atrás
# ----------------------------------------------------------------------
class TestEncadenamientoAtras(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.motor = MotorInferencia(RUTA_KB)

    def test_objetivo_en_los_hechos_iniciales(self):
        self.assertTrue(self.motor.ejecutar_inferencia_atras(["Fiebre"], "Fiebre"))
        self.assertEqual(self.motor.derivacion, [])

    def test_objetivo_inexistente(self):
        self.assertFalse(self.motor.ejecutar_inferencia_atras(["Fiebre"], "Hecho_Que_No_Existe"))
        self.assertEqual(self.motor.traza_explicacion[0]["tipo"], "FALLO")

    def test_derivacion_ordenada(self):
        """Neumonía con alerta: la derivación va de los síntomas al objetivo."""
        self.assertTrue(self.motor.ejecutar_inferencia_atras(
            ["Fiebre", "Tos", "Dificultad_Respiratoria", "Dolor_Toracico_Pleuritico",
             "Dificultad_Respiratoria_Severa"], "Alerta_Roja_Respiratoria"))
        self.assertEqual([r.id_regla for r in self.motor.derivacion],
                         ["R25", "R8", "R37", "R55", "R76", "R95"])

    def test_derivacion_es_una_prueba_valida(self):
        """Cada regla de la derivación solo usa hechos observados o probados antes."""
        hechos = ["Tos", "Dificultad_Respiratoria", "Sibilancias", "Dificultad_Respiratoria_Severa",
                  "Antecedente_Asma"]
        self.assertTrue(self.motor.ejecutar_inferencia_atras(hechos, "Alerta_Roja_Respiratoria"))
        conocidos = set(hechos)
        for regla in self.motor.derivacion:
            self.assertTrue(regla.antecedentes <= conocidos, str(regla))
            conocidos.add(regla.consecuente)
        self.assertEqual(self.motor.derivacion[-1].consecuente, "Alerta_Roja_Respiratoria")

    def test_fallo_por_hecho_faltante(self):
        self.assertFalse(self.motor.ejecutar_inferencia_atras(
            ["Fiebre", "Tos", "Dificultad_Respiratoria"], "Neumonia"))
        textos = [e["texto"] for e in self.motor.traza_explicacion]
        self.assertTrue(any(t.startswith("Dolor_Toracico_Pleuritico: no es hecho observado") for t in textos))

    def test_memoizacion(self):
        """En el caso EPOC, Disnea_Severa se reutiliza y Fiebre no se vuelve a explorar."""
        self.assertFalse(self.motor.ejecutar_inferencia_atras(
            ["Tos", "Dificultad_Respiratoria", "Sibilancias", "Dificultad_Respiratoria_Severa",
             "Antecedente_EPOC"], "Alerta_Roja_Respiratoria"))
        textos = [e["texto"] for e in self.motor.traza_explicacion]
        self.assertIn("Disnea_Severa: ya demostrado antes ✔", textos)
        self.assertIn("Fiebre: ya refutado antes ✘", textos)
        # Cada meta compuesta se intenta probar una sola vez (sin trabajo repetido).
        metas = [e["texto"] for e in self.motor.traza_explicacion if e["tipo"] == "META"]
        self.assertEqual(len(metas), len(set(metas)))

    def test_cortocircuito_del_and(self):
        """Si un antecedente falla, los siguientes de esa regla no se evalúan."""
        motor = motor_temporal(self, [("R1", ["A_falta", "B"], "Meta")])
        self.assertFalse(motor.ejecutar_inferencia_atras(["B"], "Meta"))
        self.assertFalse(any(e["texto"].startswith("B:") for e in motor.traza_explicacion))


# ----------------------------------------------------------------------
# 4. Robustez
# ----------------------------------------------------------------------
class TestRobustez(unittest.TestCase):

    def test_ciclo_sin_salida_termina(self):
        motor = motor_temporal(self, [("C1", ["A"], "B"), ("C2", ["B"], "A"), ("C3", ["B", "X"], "Meta")])
        self.assertFalse(motor.ejecutar_inferencia(["X"], "Meta"))
        self.assertFalse(motor.ejecutar_inferencia_atras(["X"], "Meta"))
        self.assertTrue(any(e["tipo"] == "CICLO" for e in motor.traza_explicacion))

    def test_ciclo_con_salida(self):
        motor = motor_temporal(self, [("C1", ["A"], "B"), ("C2", ["B"], "A"),
                                      ("C3", ["B", "X"], "Meta"), ("C4", ["Y"], "B")])
        self.assertTrue(motor.ejecutar_inferencia(["X", "Y"], "Meta"))
        self.assertTrue(motor.ejecutar_inferencia_atras(["X", "Y"], "Meta"))

    def test_fallo_por_corte_no_se_memoiza(self):
        """
        Al probar X con R1 se pide Y, que vuelve a pedir X (ciclo) y falla. Ese fallo de Y
        depende del camino: cuando X se demuestra luego con R2, Y sí es demostrable.
        Si el fallo de Y se hubiera memoizado, Meta quedaría refutada por error.
        """
        motor = motor_temporal(self, [("R1", ["Y"], "X"), ("R2", ["W"], "X"),
                                      ("R3", ["X"], "Y"), ("R4", ["X", "Y"], "Meta")])
        self.assertTrue(motor.ejecutar_inferencia(["W"], "Meta"))
        self.assertTrue(motor.ejecutar_inferencia_atras(["W"], "Meta"))
        self.assertTrue(any(e["tipo"] == "CICLO" for e in motor.traza_explicacion))

    def test_limite_de_profundidad(self):
        motor = motor_temporal(self, [(f"L{i}", [f"H{i}"], f"H{i + 1}") for i in range(100)])
        self.assertFalse(motor.ejecutar_inferencia_atras(["H0"], "H100", max_profundidad=50))
        self.assertTrue(any(e["tipo"] == "PROFUNDIDAD" for e in motor.traza_explicacion))
        self.assertTrue(motor.ejecutar_inferencia_atras(["H0"], "H100", max_profundidad=200))
        self.assertTrue(motor.ejecutar_inferencia_atras(["H0"], "H100"))   # límite por defecto
        self.assertTrue(motor.ejecutar_inferencia(["H0"], "H100"))

    def test_kb_inexistente(self):
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            motor = MotorInferencia(os.path.join(CARPETA, "no_existe.json"))
        self.assertEqual(motor.reglas, [])
        self.assertIn("Error al cargar", salida.getvalue())
        self.assertFalse(motor.ejecutar_inferencia(["A"], "B"))
        self.assertFalse(motor.ejecutar_inferencia_atras(["A"], "B"))

    def test_kb_vacia(self):
        motor = motor_temporal(self, [])
        self.assertTrue(motor.ejecutar_inferencia(["A"], "A"))
        self.assertFalse(motor.ejecutar_inferencia_atras(["A"], "B"))

    def test_hechos_desconocidos(self):
        motor = MotorInferencia(RUTA_KB)
        self.assertEqual(motor.hechos_desconocidos(["Fiebre", "fiebre", "Tos"]), ["fiebre"])


# ----------------------------------------------------------------------
# 5. Casos clínicos
# ----------------------------------------------------------------------
class TestCasosClinicos(unittest.TestCase):

    def test_al_menos_3_casos(self):
        self.assertGreaterEqual(len(pif.CASOS_CLINICOS), 3)

    def test_resultado_esperado_en_ambos_motores(self):
        motor = MotorInferencia(RUTA_KB)
        for n, caso in enumerate(pif.CASOS_CLINICOS, 1):
            with self.subTest(caso=n, nombre=caso["nombre"]):
                self.assertEqual(motor.hechos_desconocidos(caso["sintomas"]), [])
                self.assertEqual(motor.ejecutar_inferencia(caso["sintomas"], caso["objetivo"]), caso["esperado"])
                self.assertEqual(motor.ejecutar_inferencia_atras(caso["sintomas"], caso["objetivo"]),
                                 caso["esperado"])

    def test_casos_exitosos_de_alerta_llegan_al_nivel_4(self):
        motor = MotorInferencia(RUTA_KB)
        for caso in pif.CASOS_CLINICOS:
            if caso["esperado"] and caso["objetivo"].startswith("Alerta_"):
                with self.subTest(nombre=caso["nombre"]):
                    motor.ejecutar_inferencia(caso["sintomas"], caso["objetivo"])
                    self.assertEqual(motor.traza_explicacion[-1]["iteracion"], 4)


# ----------------------------------------------------------------------
# 6. Equivalencia de ambos motores (prueba aleatoria con semilla fija)
# ----------------------------------------------------------------------
class TestEquivalenciaMotores(unittest.TestCase):

    def test_adelante_atras_y_cierre_coinciden(self):
        motor = MotorInferencia(RUTA_KB)
        v = motor.validar_kb()
        base = v["hechos_base"]
        derivados = sorted({r.consecuente for r in motor.reglas})
        azar = random.Random(2026)
        for prueba in range(300):
            hechos = azar.sample(base, azar.randint(1, 12))
            esperado_cierre = cierre_logico(motor.reglas, hechos)
            for objetivo in azar.sample(derivados, 5):
                with self.subTest(prueba=prueba, objetivo=objetivo):
                    referencia = objetivo in esperado_cierre
                    self.assertEqual(motor.ejecutar_inferencia(hechos, objetivo), referencia)
                    self.assertEqual(motor.ejecutar_inferencia_atras(hechos, objetivo), referencia)


# ----------------------------------------------------------------------
# 7. Presentación y exportación
# ----------------------------------------------------------------------
class TestPresentacion(unittest.TestCase):

    def setUp(self):
        self.motor = MotorInferencia(RUTA_KB)
        self.hechos = ["Manos_Frias", "Relleno_Capilar_Mayor_3s", "Pulso_Debil_Rapido", "Contexto_Pediatrico"]

    def test_tabla_adelante(self):
        self.motor.ejecutar_inferencia(self.hechos, "Alerta_Roja_Circulatoria")
        texto = self.motor.formatear_traza("adelante")
        for fragmento in ("Paso", "Nivel", "Hecho nuevo", "R27", "R102", "Alerta_Roja_Circulatoria"):
            self.assertIn(fragmento, texto)

    def test_arbol_atras(self):
        self.motor.ejecutar_inferencia_atras(self.hechos, "Alerta_Roja_Circulatoria")
        texto = self.motor.formatear_traza("atras")
        self.assertIn("Derivación", texto)
        self.assertIn("└─ R102", texto)
        self.assertIn("Manos_Frias  ✔ hecho observado", texto)

    def test_arbol_de_fallo(self):
        self.motor.ejecutar_inferencia_atras(["Fiebre", "Tos", "Dificultad_Respiratoria"], "Neumonia")
        texto = self.motor.formatear_traza("atras")
        self.assertIn("Neumonia  ✘ no demostrable", texto)
        self.assertIn("Dolor_Toracico_Pleuritico  ✘ no observado", texto)

    def test_sin_colores_fuera_de_terminal(self):
        pif.activar_color(False)
        self.motor.ejecutar_inferencia(self.hechos, "Alerta_Roja_Circulatoria")
        self.assertNotIn("\x1b[", self.motor.formatear_traza("adelante"))

    def test_exportar_traza(self):
        self.motor.ejecutar_inferencia(self.hechos, "Alerta_Roja_Circulatoria")
        carpeta = tempfile.mkdtemp()
        ruta_json, ruta_txt = os.path.join(carpeta, "t.json"), os.path.join(carpeta, "t.txt")
        self.motor.exportar_traza(ruta_json)
        self.motor.exportar_traza(ruta_txt, "adelante")
        with open(ruta_json, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 4)
        with open(ruta_txt, encoding="utf-8") as f:
            self.assertIn("R102", f.read())
        os.remove(ruta_json); os.remove(ruta_txt); os.rmdir(carpeta)

    def test_programa_principal(self):
        """main() termina con código 0 y exporta las trazas de los 7 casos."""
        anterior = os.getcwd()
        carpeta = tempfile.mkdtemp()
        try:
            os.chdir(carpeta)
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                codigo = pif.main(["proyecto_inferencia_final.py", RUTA_KB])
            self.assertEqual(codigo, 0)
            self.assertIn(f"{len(pif.CASOS_CLINICOS)}/{len(pif.CASOS_CLINICOS)} casos correctos",
                          salida.getvalue())
            with open("trazas_casos_clinicos.txt", encoding="utf-8") as f:
                self.assertNotIn("\x1b[", f.read())
        finally:
            os.chdir(anterior)
            os.remove(os.path.join(carpeta, "trazas_casos_clinicos.txt"))
            os.rmdir(carpeta)


if __name__ == "__main__":
    unittest.main(verbosity=2)
