import sheets_client as sc

BASE_ROW = [
    "2026-09-01", 150.0, "EGP", "kabab lunch",
    "أكل", "Cash", "I ate kabab | It cost 150", "2026-09-01 13:20:00",
]


def _append_result(row=None, row_number=7):
    return {"row": list(row or BASE_ROW), "row_number": row_number}


def test_matches_exact_readback(monkeypatch):
    monkeypatch.setattr(sc, "get_row", lambda n: list(BASE_ROW))
    assert sc.verify_expense_write(_append_result()) is True


def test_amount_with_thousands_separator_still_matches(monkeypatch):
    # Sheets may echo "6,000" for a USER_ENTERED 6000.
    written = ["2026-09-01", 6000.0, "EGP", "ssd", "أخرى", "Card", "raw text here", "ts"]
    read_back = list(written)
    read_back[1] = "6,000"
    monkeypatch.setattr(sc, "get_row", lambda n: read_back)
    assert sc.verify_expense_write(_append_result(written)) is True


def test_date_reformatted_by_sheets_is_tolerated(monkeypatch):
    read_back = list(BASE_ROW)
    read_back[0] = "9/1/2026"  # Sheets locale reformat
    monkeypatch.setattr(sc, "get_row", lambda n: read_back)
    assert sc.verify_expense_write(_append_result()) is True


def test_raw_text_mismatch_fails(monkeypatch):
    read_back = list(BASE_ROW)
    read_back[6] = "a completely different row"
    monkeypatch.setattr(sc, "get_row", lambda n: read_back)
    assert sc.verify_expense_write(_append_result()) is False


def test_amount_mismatch_fails(monkeypatch):
    read_back = list(BASE_ROW)
    read_back[1] = 999.0
    monkeypatch.setattr(sc, "get_row", lambda n: read_back)
    assert sc.verify_expense_write(_append_result()) is False


def test_empty_readback_fails(monkeypatch):
    monkeypatch.setattr(sc, "get_row", lambda n: [])
    assert sc.verify_expense_write(_append_result()) is False


def test_falls_back_to_last_record_without_row_number(monkeypatch):
    monkeypatch.setattr(sc, "get_last_record", lambda: list(BASE_ROW))
    called = {"get_row": False}
    monkeypatch.setattr(sc, "get_row", lambda n: called.__setitem__("get_row", True))
    assert sc.verify_expense_write({"row": list(BASE_ROW), "row_number": None}) is True
    assert called["get_row"] is False


def test_accepts_legacy_plain_row_list(monkeypatch):
    monkeypatch.setattr(sc, "get_last_record", lambda: list(BASE_ROW))
    assert sc.verify_expense_write(list(BASE_ROW)) is True


def test_parse_updated_row_number():
    resp = {"updates": {"updatedRange": "Sheet1!A7:H7"}}
    assert sc._parse_updated_row_number(resp) == 7
    assert sc._parse_updated_row_number({}) is None
    assert sc._parse_updated_row_number({"updates": {"updatedRange": "weird"}}) is None
