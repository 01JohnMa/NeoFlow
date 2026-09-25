from services.template_contract import load_template, template_consistency, template_to_schema, project_fields


def test_canonical_template_has_40_fields_and_schema_shape():
    t = load_template()
    assert template_consistency(t) == []
    assert len(t["fields"]) == 40
    s = template_to_schema(t)
    assert set(s["properties"]) == {f["key"] for f in t["fields"]}
    assert s["properties"]["trial_phase"]["enum"] == ["I期", "II期", "III期", "IV期", "BE", "其他"]
    assert s["properties"]["control_products"]["items"]["required"] == ["name"]


def test_projection_retains_declarations_and_empty_values():
    t = load_template()
    result = project_fields({"sample_size": "240例", "trial_phase": ""}, template=t)
    assert len(result["fields"]) == 40
    empty = next(f for f in result["fields"] if f["key"] == "trial_phase")
    assert empty["value"] == ""
    assert "confidence" not in empty and "source" not in empty
    assert next(f for f in result["fields"] if f["key"] == "sample_size")["value"] == "240例"
