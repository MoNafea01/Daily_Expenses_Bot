import main


def setup_function():
    main._SEEN_UPDATE_IDS.clear()


def test_first_time_update_is_not_a_duplicate():
    assert main._already_processed(1001) is False


def test_same_update_id_is_a_duplicate_on_second_call():
    assert main._already_processed(2002) is False
    assert main._already_processed(2002) is True
    assert main._already_processed(2002) is True


def test_none_update_id_is_never_treated_as_duplicate():
    assert main._already_processed(None) is False
    assert main._already_processed(None) is False


def test_seen_set_is_bounded():
    for i in range(main._SEEN_MAX + 50):
        main._already_processed(i)
    assert len(main._SEEN_UPDATE_IDS) <= main._SEEN_MAX
    # Oldest ids evicted, newest retained.
    assert (main._SEEN_MAX + 49) in main._SEEN_UPDATE_IDS
    assert 0 not in main._SEEN_UPDATE_IDS
