import random

from calc import abs_diff, h, p


def test_passes_on_base_too():
    assert abs_diff(3, 1) == 2
    assert h(True) == 1
    assert p("1") == 1


def test_flaky():
    assert random.random() < 0.5
