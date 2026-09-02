import dspy_extractor as dx


def test_canonical_categories_map_to_themselves():
    for cat in dx.CATEGORIES:
        assert dx.normalize_category(cat) == cat


def test_common_aliases():
    assert dx.normalize_category("food") == "أكل"
    assert dx.normalize_category("مطعم") == "أكل"
    assert dx.normalize_category("uber") == "مواصلات"
    assert dx.normalize_category("wifi") == "إنترنت"
    assert dx.normalize_category("shoes") == "ملابس"


def test_combined_alias_english_string_takes_first_part():
    assert dx.normalize_category("اكل/Food") == "أكل"


def test_arabic_definite_article_is_stripped():
    assert dx.normalize_category("الكهرباء") == "مرافق"


def test_empty_input_returns_none():
    assert dx.normalize_category("") is None
    assert dx.normalize_category(None) is None


def test_unknown_value_falls_back_to_other_not_raw_string():
    assert dx.normalize_category("totally-unknown-xyz") == dx.FALLBACK_CATEGORY
    assert dx.FALLBACK_CATEGORY == "أخرى"


def test_legacy_categories_map_into_budget_buckets():
    assert dx.normalize_category("تسوق") == "ملابس"
    assert dx.normalize_category("صحة") == "طوارئ"
    assert dx.normalize_category("other") == "أخرى"


def test_every_normalized_value_is_a_known_category():
    samples = ["food", "بنزين", "خدعة", "", "investment", "الانترنت", "random"]
    for s in samples:
        result = dx.normalize_category(s)
        assert result is None or result in dx.KNOWN_CATEGORIES
