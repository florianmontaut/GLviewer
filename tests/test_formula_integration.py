
import unittest
import math
import numpy as np

from model.formula.lexer import Lexer
from model.formula.parser import MathParser
from model.formula.interpreter import Interpreter


def evaluate(expr: str, variables=None):
    """Helper end-to-end: Lexer → Parser → Interpreter"""
    tokens = list(Lexer(expr).generate_tokens())
    tree = MathParser(tokens).parse()
    interpreter = Interpreter()
    interpreter.vars.update(variables or {})
    return interpreter.visit(tree).value


class TestEndToEnd(unittest.TestCase):

    # -------------------------------
    # Nombres & opérations
    # -------------------------------
    def test_simple_arithmetic(self):
        self.assertEqual(evaluate("1+2"), 3)
        self.assertEqual(evaluate("10-3"), 7)
        self.assertEqual(evaluate("4*5"), 20)
        self.assertEqual(evaluate("20/4"), 5)
        self.assertEqual(evaluate("2^3"), 8)

    # -------------------------------
    # Expressions plus complexes
    # -------------------------------
    def test_complex_expression(self):
        expr = "27 + ((43 / 36) - 48) * 51"
        value = evaluate(expr)
        expected = 27 + ((43/36) - 48) * 51
        self.assertAlmostEqual(value, expected, 5)

    # -------------------------------
    # Fonctions (1 argument)
    # -------------------------------
    def test_single_argument_functions(self):
        self.assertAlmostEqual(evaluate("sin(pi/2)"), 1.0, 5)
        self.assertEqual(evaluate("abs(-5)"), 5)
        self.assertEqual(evaluate("sqrt(9)"), 3)
        self.assertAlmostEqual(evaluate("log(e())"), 1.0, 5)

    # -------------------------------
    # Constantes
    # -------------------------------
    def test_constants(self):
        self.assertAlmostEqual(evaluate("pi()"), math.pi, 7)
        self.assertAlmostEqual(evaluate("e()"), math.e, 7)

    # -------------------------------
    # Fonctions multi-arguments
    # -------------------------------
    def test_multi_argument_functions(self):
        self.assertEqual(evaluate("max(1;5;3)"), 5)
        self.assertEqual(evaluate("min(10;7;9)"), 7)
        self.assertEqual(evaluate("sum(1;2;3;4)"), 10)
        self.assertEqual(evaluate("avg(10;20;30)"), 20)

    # -------------------------------
    # Variables
    # -------------------------------
    def test_variables(self):
        # Suite d'expressions dans un même interpreter
        interp = Interpreter()

        # x = 5
        tokens = list(Lexer("x=5").generate_tokens())
        tree = MathParser(tokens).parse()
        interp.visit(tree)

        # sin(x) + x^2
        tokens = list(Lexer("sin(x) + x^2").generate_tokens())
        tree = MathParser(tokens).parse()
        value = interp.visit(tree).value

        expected = math.sin(5) + 5**2
        self.assertAlmostEqual(value, expected, 5)

    # -------------------------------
    # Tests d’erreurs
    # -------------------------------
    def test_errors(self):
        with self.assertRaises(Exception):
            evaluate("unknownFunction(10)")

        with self.assertRaises(Exception):
            evaluate("1/0")

        with self.assertRaises(Exception):
            evaluate("x + 5")  # x non définie

        for expr in ["1 2 3", "2^", "(1+2", "1+", "1.2.3", "sin(1;2)", "max()", "log(-1)", "5 # 3"]:
            with self.assertRaises(Exception, msg=expr):
                evaluate(expr)

    def test_power(self):
        self.assertEqual(evaluate("2^3^2"), 512)
        self.assertEqual(evaluate("-2^2"), -4)
        self.assertEqual(evaluate("2^-1"), 0.5)
        self.assertEqual(evaluate("2*3^2"), 18)

    def test_function_names_kept(self):
        self.assertAlmostEqual(evaluate("log(10)"), math.log(10), 7)
        self.assertEqual(evaluate("sin(0)+5"), 5)
        self.assertAlmostEqual(evaluate("pi"), math.pi, 7)
        self.assertAlmostEqual(evaluate("2*pi"), 2*math.pi, 7)

    def test_channels(self):
        # préfigure log(CH1-CH2)/52 avec des voies injectées dans l'interpréteur
        interp = Interpreter()
        interp.vars.update({"CH1": 12.0, "CH2": 2.0})
        tree = MathParser(Lexer("log(CH1-CH2)/52").generate_tokens()).parse()
        self.assertAlmostEqual(interp.visit(tree).value, math.log(10)/52, 7)


class TestSignals(unittest.TestCase):
    """Voies (np.ndarray) comme on les extrairait d'un .csv"""

    def setUp(self):
        self.ch = {
            "CH1": np.array([3.0, 5.0, 12.0, 1.0]),
            "CH2": np.array([2.0, 4.0, 2.0, 1.0]),
        }

    def test_target_expression(self):
        result = evaluate("log(CH1-CH2)/52", self.ch)
        self.assertIsInstance(result, np.ndarray)
        np.testing.assert_allclose(result[:3], np.log([1.0, 1.0, 10.0]) / 52)
        # dernier échantillon : log(0) -> -inf, sans exception
        self.assertEqual(result[3], -np.inf)

    def test_elementwise_operations(self):
        np.testing.assert_allclose(evaluate("CH1*CH2 + 1", self.ch), [7, 21, 25, 2])
        np.testing.assert_allclose(evaluate("CH1^2", self.ch), [9, 25, 144, 1])
        np.testing.assert_allclose(evaluate("-CH1/2", self.ch), [-1.5, -2.5, -6, -0.5])
        np.testing.assert_allclose(evaluate("2*sin(pi*CH2/4)", self.ch), 2*np.sin(np.pi*self.ch["CH2"]/4))
        np.testing.assert_allclose(evaluate("20*log10(abs(CH1))", self.ch), 20*np.log10(self.ch["CH1"]))

    def test_invalid_samples_do_not_raise(self):
        result = evaluate("1/(CH1-CH2)", self.ch)
        np.testing.assert_allclose(result[:3], [1.0, 1.0, 0.1])
        self.assertEqual(result[3], np.inf)
        self.assertTrue(np.isnan(evaluate("sqrt(CH2-CH1)", self.ch)[0]))

    def test_reductions_single_argument(self):
        self.assertEqual(evaluate("max(CH1)", self.ch), 12)
        self.assertEqual(evaluate("min(CH1)", self.ch), 1)
        self.assertEqual(evaluate("sum(CH1)", self.ch), 21)
        self.assertEqual(evaluate("avg(CH1)", self.ch), 5.25)
        # le résultat d'une réduction est un scalaire réutilisable : signal centré
        np.testing.assert_allclose(evaluate("CH1-avg(CH1)", self.ch), self.ch["CH1"] - 5.25)

    def test_elementwise_multi_arguments(self):
        np.testing.assert_allclose(evaluate("max(CH1;CH2)", self.ch), [3, 5, 12, 1])
        np.testing.assert_allclose(evaluate("min(CH1;4)", self.ch), [3, 4, 4, 1])
        np.testing.assert_allclose(evaluate("sum(CH1;CH2;1)", self.ch), [6, 10, 15, 3])
        np.testing.assert_allclose(evaluate("avg(CH1;CH2)", self.ch), [2.5, 4.5, 7, 1])

    def test_assignment_of_signal(self):
        interp = Interpreter()
        interp.vars.update(self.ch)
        interp.visit(MathParser(Lexer("D = CH1-CH2").generate_tokens()).parse())
        value = interp.visit(MathParser(Lexer("D*2").generate_tokens()).parse()).value
        np.testing.assert_allclose(value, [2, 2, 20, 0])

    def test_list_input_is_converted(self):
        np.testing.assert_allclose(evaluate("CH*2", {"CH": [1, 2, 3]}), [2, 4, 6])

    def test_shape_mismatch(self):
        with self.assertRaises(Exception):
            evaluate("A+B", {"A": np.array([1.0, 2.0]), "B": np.array([1.0, 2.0, 3.0])})

    def test_scalar_results_stay_float(self):
        self.assertIsInstance(evaluate("1+2"), float)
        self.assertIsInstance(evaluate("max(CH1)", self.ch), float)


if __name__ == "__main__":
    unittest.main()


# ---------------- ajouts GLviewer ----------------
import pytest
from model.formula import FormulaError, parse, references, evaluate as glv_evaluate


@pytest.mark.parametrize("text, value", [("4.18e3", 4180.0), ("1E-3*2", 0.002),
                                         ("2.5e+2", 250.0), ("2*e", 2 * math.e),
                                         (".5e1", 5.0)])
def test_scientific_notation(text, value):
    assert glv_evaluate(parse(text), {}) == pytest.approx(value)


def test_bracket_channels_with_spaces_and_accents():
    tree = parse("[Débit eau]/60*4180*([T sortie]-[T entrée]) + CH3*time")
    assert references(tree) == ({"CH3", "time"}, {"Débit eau", "T sortie", "T entrée"})
    value = glv_evaluate(tree, {"[Débit eau]": 6.0, "[T sortie]": 30.0, "[T entrée]": 20.0,
                                "CH3": 0.0, "time": 0.0})
    assert value == pytest.approx(6 / 60 * 4180 * 10)


@pytest.mark.parametrize("text", ["[T AMB", "[]", "[a[b]]", "2 [a]", "", "1e"])
def test_formula_errors(text):
    with pytest.raises(FormulaError):
        parse(text)


def test_formula_error_is_caught_by_glviewer():
    from ressources.custom_exceptions import AnalysisError
    assert issubclass(FormulaError, AnalysisError) and issubclass(FormulaError, ValueError)
    with pytest.raises(FormulaError, match="Unknown channel"):
        glv_evaluate(parse("[T AMB]"), {})
