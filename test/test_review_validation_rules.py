import unittest

from ../api.exceptions import ValidationError
from api.routes.documents.review import _validate_review_rules


class TestReviewValidationRules(unittest.TestCase):
    def setUp(self):
        self.template = {
            "template_fields": [
                {
                    "field_key": "inspection_conclusion",
                    "field_label": "检验结论",
                    "review_enforced": True,
                    "review_allowed_values": ["合格", "不合格"],
                }
            ]
        }

    def test_review_rules_pass_when_value_allowed(self):
        data = {"inspection_conclusion": "合格"}
        _validate_review_rules(self.template, data)

    def test_review_rules_fail_when_value_invalid(self):
        data = {"inspection_conclusion": "通过"}
        with self.assertRaises(ValidationError):
            _validate_review_rules(self.template, data)


if __name__ == "__main__":
    unittest.main()
