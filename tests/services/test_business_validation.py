from services.business_validation import validate_template_values
from services.template_contract import load_template


def test_empty_values_are_unresolved_without_field_specific_rules():
    t = load_template()
    assert validate_template_values(t, {"trial_phase": "", "nmpa_date": ""}) == []


def test_generic_enum_date_number_and_products_validation():
    t = load_template()
    issues = validate_template_values(t, {
        "trial_type": "未知",
        "nmpa_date": "2026/01/01",
        "planned_subject_count": "240",
        "control_products": [{"name": "", "dosage_form": "未知"}],
    })
    codes = {i["code"] for i in issues}
    assert {"invalid_enum", "invalid_date", "invalid_number", "empty_product_name", "invalid_product_enum"} <= codes


def test_evidence_page_must_be_in_current_parse_range():
    t = load_template()
    issues = validate_template_values(t, {"project_name": "x"}, page_numbers={1, 2}, evidence={"project_name": [{"page": 3}]})
    assert any(i["code"] == "evidence_page_out_of_range" for i in issues)
