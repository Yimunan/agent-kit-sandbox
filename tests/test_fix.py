from calc import abs_diff


def test_abs_diff_negative():
    assert abs_diff(1, 3) == 2
