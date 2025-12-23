from src.schemas import slots


def test_filter_valid_slots_filters_unknown_and_empty():
    payload = {
        "target_country": "Malaysia",
        "": "noop",
        "Degree_Level": "Undergraduate",
        "unknown": "value",
        "budget": "100000",
        "none_value": None,
        "blank": " ",
    }
    cleaned = slots.filter_valid_slots(payload)
    assert cleaned == {
        "target_country": "Malaysia",
        "degree_level": "Undergraduate",
        "budget": "100000",
    }


def test_missing_required_slots_returns_required_defs():
    missing = slots.missing_required_slots({})
    names = {slot.name for slot in missing}
    assert "target_country" in names


def test_slot_definitions_iterable():
    defs = list(slots.slot_definitions())
    assert any(defn.name == "target_country" for defn in defs)


def test_validate_slot_value_numeric_bounds():
    gpa_slot = slots.get_slot_definition("gpa")
    assert gpa_slot is not None
    assert slots.validate_slot_value(gpa_slot, "ten") == "must be a number"
    assert slots.validate_slot_value(gpa_slot, -1) == "must be ≥ 0.0"
    assert slots.validate_slot_value(gpa_slot, 5) == "must be ≤ 4.0"
    assert slots.validate_slot_value(gpa_slot, 3.2) is None


def test_validate_slots_collects_errors():
    errors = slots.validate_slots({"gpa": "bad", "target_country": ""})
    assert errors["gpa"] == "must be a number"
    assert errors["target_country"] == "required"
