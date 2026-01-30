import asyncio
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.supabase_service import supabase_service
from services.template_service import template_service


class TestPromptExtractionHint(unittest.TestCase):
    def test_sdcm_extraction_hint_is_rendered(self):
        tenant_id = "a0000000-0000-0000-0000-000000000002"
        template_code = "integrating_sphere"
        ocr_text = "SDCM：3.2"

        asyncio.run(supabase_service.initialize())
        template = asyncio.run(
            template_service.get_template_by_code(tenant_id, template_code)
        )
        self.assertIsNotNone(template)

        prompt = template_service.build_extraction_prompt(template, ocr_text)
        print("\n=== Generated Prompt ===\n")
        print(prompt)

        sdcm_line = next(
            (line for line in prompt.splitlines() if "| sdcm |" in line),
            "",
        )
        self.assertIn("仅数值，不带单位", sdcm_line)


if __name__ == "__main__":
    unittest.main()
