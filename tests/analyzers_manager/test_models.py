from unittest.mock import patch

from django.core.exceptions import ValidationError

from api_app.analyzers_manager.models import AnalyzerConfig
from tests import CustomTestCase


class AnalyzerConfigTestCase(CustomTestCase):
    def test_clean(self):
        ac = AnalyzerConfig(
            name="test",
            python_module="yara_scan.YaraScan",
            description="test",
            config={"soft_time_limit": 10, "queue": "default"},
            secrets={},
            params={},
            disabled=False,
            type="file",
            leaks_info=True,
            run_hash=True,
        )
        with self.assertRaises(ValidationError) as e:
            ac.full_clean()
        self.assertIn("__all__", e.exception.message_dict)
        self.assertEqual(1, len(e.exception.message_dict["__all__"]))
        self.assertEqual(
            "run_hash_type must be populated if run_hash is True",
            e.exception.message_dict["__all__"][0],
        )
        ac.delete()

    def test_update(self):

        result = AnalyzerConfig.update("yara_scan.YaraScan2")
        self.assertFalse(result)

        ac = AnalyzerConfig(
            name="test",
            python_module="xlm_macro_deobfuscator.XlmMacroDeobfuscator",
            description="test",
            config={"soft_time_limit": 10, "queue": "default"},
            secrets={},
            params={},
            disabled=False,
            type="file",
            leaks_info=True,
        )
        result = AnalyzerConfig.update("xlm_macro_deobfuscator.XlmMacroDeobfuscator")
        self.assertFalse(result)
        ac.delete()

        ac = AnalyzerConfig(
            name="test",
            python_module="yara_scan.YaraScan",
            description="test",
            config={"soft_time_limit": 10, "queue": "default"},
            secrets={},
            params={},
            disabled=False,
            type="file",
            leaks_info=True,
        )
        with patch("intel_owl.celery.broadcast"):
            result = AnalyzerConfig.update("yara_scan.YaraScan")
        self.assertTrue(result)
        ac.delete()