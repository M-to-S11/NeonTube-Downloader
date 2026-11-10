"""Static UI layout regression tests; do not require a graphical display."""
import ast
import unittest
from pathlib import Path

class LayoutTests(unittest.TestCase):
    def test_neon_progress_does_not_override_framework_draw(self):
        """CTkFrame calls its internal _draw(no_color_updates=True) during init."""
        app = ast.parse((Path(__file__).parent / "app.py").read_text(encoding="utf-8"))
        progress = next(node for node in app.body if isinstance(node, ast.ClassDef)
                        and node.name == "NeonGradientProgress")
        methods = {node.name for node in progress.body if isinstance(node, ast.FunctionDef)}
        self.assertNotIn("_draw", methods, "Framework method _draw must not be overridden")
        self.assertIn("_draw_progress", methods)

    def test_place_does_not_set_width_or_height(self):
        app = ast.parse((Path(__file__).parent / "app.py").read_text(encoding="utf-8"))
        for call in ast.walk(app):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "place":
                dimensions = set(k.arg for k in call.keywords) & {"width", "height"}
                self.assertFalse(dimensions, f"Illegal .place() dimensions on line {call.lineno}: {dimensions}")

if __name__ == "__main__":
    unittest.main()
