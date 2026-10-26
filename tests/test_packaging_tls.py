"""Release recipe must retain TLS data required by the build runtime."""
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class PackagingTlsTests(unittest.TestCase):
    def recipe_data(self, runtime_directory):
        recipe = Path(__file__).resolve().parents[1] / "packaging/QR-Scanner.spec"
        inputs = {}

        def analysis(*args, **kwargs):
            inputs.update(kwargs)
            return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

        with patch("ssl.__file__", str(runtime_directory / "ssl.py")), \
             patch("PyInstaller.utils.hooks.collect_all", return_value=([], [], [])):
            runpy.run_path(str(recipe), init_globals={
                "SPECPATH": str(recipe.parent), "Analysis": analysis,
                "PYZ": lambda *args: None, "EXE": lambda *args, **kwargs: None,
            })
        return inputs["datas"]

    def test_runtime_tls_support_file_is_bundled_at_ssl_module_root(self):
        # Omitting this public file breaks SSLContext before any network call.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            support = root / "codex-rejected-cas.pem"
            support.write_text("test-only public TLS support material", encoding="ascii")
            self.assertIn((str(support), "."), self.recipe_data(root))

    def test_stock_python_without_optional_tls_support_still_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = self.recipe_data(Path(directory))
            self.assertFalse(any(Path(source).name == "codex-rejected-cas.pem" for source, _ in rows))

    def test_self_test_does_not_report_success_when_tls_cannot_initialize(self):
        from app import run_self_test
        with patch("ssl.create_default_context", side_effect=FileNotFoundError("missing TLS fixture")):
            with self.assertRaises(FileNotFoundError):
                run_self_test()
