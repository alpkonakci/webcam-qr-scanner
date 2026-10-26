import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.release_licenses import copy_material, input_files, inventory, verify_sources
from scripts.verify_distribution import verify_upstream_sources


class ReleaseLicenseTests(unittest.TestCase):
    def test_input_inventory_ignores_option_and_module_names(self):
        entries = [True, ['numpy'], [('thing', 'some.dll', 'BINARY'),
                                   ('option', 'somewhere', 'OPTION')]]
        self.assertEqual(list(input_files(entries)), [Path('some.dll').resolve()])

    def test_unknown_site_package_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            analysis = Path(directory) / 'Analysis.toc'
            analysis.write_text(repr([('mystery', str(Path(directory) / 'site-packages/mystery.py'), 'PYMODULE')]))
            with patch('scripts.release_licenses.metadata.distributions', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'Unmapped third-party'):
                    inventory(analysis)

    def test_inventory_retains_nested_license_tree_without_local_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            license_path = root / 'example-1.dist-info/licenses/nested/NOTICE'
            license_path.parent.mkdir(parents=True)
            license_path.write_text('Example copyright')
            output = root / 'out'
            output.mkdir()
            rows = [{'name': 'example', 'version': '1', 'license': 'MIT',
                     'files': ['private-local-source'], 'license_files': [license_path]}]
            copy_material(rows, output)
            self.assertEqual((output / 'INVENTORY_LICENSES/example/licenses/nested/NOTICE').read_text(), 'Example copyright')
            manifest = (output / 'DEPENDENCY_INVENTORY.json').read_text()
            self.assertNotIn('private-local-source', manifest)
            self.assertEqual(json.loads(manifest)[0]['input_count'], 1)

    def test_checked_in_upstream_sources_match_installed_packages(self):
        root = Path(__file__).resolve().parents[1]
        verify_sources(root / 'third_party/sources')
        result = verify_upstream_sources(root / 'third_party/sources', root / '.venv/Lib/site-packages')
        self.assertEqual(result, {'pystray': 13, 'certifi': 6})

    def test_source_digest_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.tar.gz').write_bytes(b'not the pinned source')
            (root / 'manifest.json').write_text(json.dumps([{'filename': 'source.tar.gz', 'sha256': '0'*64}]))
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                verify_sources(root)

    def test_source_manifest_cannot_escape_its_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps([{'filename': '../other', 'sha256': '0'*64}]))
            with self.assertRaisesRegex(ValueError, 'directly inside'):
                verify_sources(root)

    def test_actual_rebuild_recipe_drops_ffmpeg_not_camera_backend(self):
        root = Path(__file__).resolve().parents[1]
        recipe = (root / 'packaging/QR-Scanner.spec').read_text()
        self.assertIn('opencv_videoio_ffmpeg', recipe)
        self.assertNotIn("'cv2'", recipe.split('excludes=')[1].split('noarchive')[0])
        self.assertIn('WQRS_BUILD_IMPORT_PATH', recipe)
        self.assertIn('if probe else []', recipe)


if __name__ == '__main__':
    unittest.main()
