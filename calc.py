def add(a, b):
    return a + b


def abs_diff(a, b):
    return abs(a - b)


def h(x):
    return 1 if x else 2


def p(text):
    try:
        return int(text)
    except ValueError:
        return None
