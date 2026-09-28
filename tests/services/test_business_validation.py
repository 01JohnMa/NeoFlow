from services.business_validation import clear_unsupported_enum_values, validate_template_values
from services.template_contract import load_template, template_to_schema
from services.extract_service import validate_output


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


def test_unsupported_enum_is_cleared_from_current_parse_text():
    t = load_template()
    values = {"trial_phase": "II期", "registration_type": "注册类", "multisite_flag": "是"}
    result = clear_unsupported_enum_values(t, values, "临床试验类型：注册类；多中心临床研究。研究阶段包括筛选期和治疗期。")
    assert "trial_phase" not in result
    assert result["registration_type"] == "注册类"
    assert result["multisite_flag"] == "是"


def test_enum_evidence_uses_unicode_normalization_and_schema_safe_omission():
    t = load_template()
    values = {"trial_phase": "II期", "registration_type": "注册类"}
    supported = clear_unsupported_enum_values(t, values, "Ⅱ期临床试验；注册类")
    assert supported["trial_phase"] == "II期"
    assert validate_output("per_doc", template_to_schema(t), supported) == []

    contradictory = clear_unsupported_enum_values(t, values, "III期临床试验；注册类")
    assert "trial_phase" not in contradictory
    assert validate_output("per_doc", template_to_schema(t), contradictory) == []
