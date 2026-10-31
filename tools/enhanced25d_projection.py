"""Pure presentation projection. Never changes source movement/camera state."""
from math import isfinite

ORIGIN = (512, 1536)
SIZE = (448, 256)


def viewport(width, height):
    if not all(isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError('Invalid presentation viewport')
    scale = min(width / SIZE[0], height / SIZE[1])
    return ((width - SIZE[0] * scale) / 2,
            (height - SIZE[1] * scale) / 2, scale)


def project_raw(x, y, width, height):
    if not all(isinstance(v, int) and not isinstance(v, bool) and -32768 <= v <= 32767 for v in (x, y)):
        raise ValueError('Expected signed source fixed-point integers')
    ox, oy, scale = viewport(width, height)
    return (ox + (x / 16 - ORIGIN[0]) * scale,
            oy + (y / 16 - ORIGIN[1]) * scale)


def inverse_raw(x, y, width, height):
    if not all(isfinite(v) for v in (x, y)):
        raise ValueError('Invalid presentation point')
    ox, oy, scale = viewport(width, height)
    return ((x - ox) / scale + ORIGIN[0]) * 16, ((y - oy) / scale + ORIGIN[1]) * 16


def validate_art_grid(source, art, length):
    if len(source) != len(art) or len(source) < 2:
        raise ValueError('Missing art registration pairs')
    for values in (source, art):
        if values[0] != 0 or values[-1] != length or any(not isfinite(v) for v in values):
            raise ValueError('Invalid art registration extent')
        if any(a >= b for a, b in zip(values, values[1:])):
            raise ValueError('Folded art registration grid')
