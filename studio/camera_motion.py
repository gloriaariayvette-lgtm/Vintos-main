"""Camera motion: where the main moving region went between two frames, from pixels, on the CPU.

A small structured-memory organ for the camera mamepa. Each frame is reduced to a 96-pixel thumbnail (kept only
while it is the previous frame of the scene); between consecutive frames the changed pixels are found and the
shift that best carries the earlier frame's changed pixels onto the later frame is searched exhaustively. A rigid
object moving over a steady background matches at its true shift with almost no error; a cut, a flicker or a
change with no consistent shift does not, and is reported as no motion. Nothing is named and nothing is kept on
disk: the result is a displacement in fractions of the view, its reliability, and how much of the view changed.

Image coordinates: x grows to the right, y grows downward, so a negative dy is upward motion.
"""
import numpy as np

SIDE = 96                 # thumbnail side (pixels)
MAX_SHIFT = 16            # largest shift searched between consecutive frames (thumbnail pixels, 1/6 of the view)
CHANGE = 24 / 255.        # a pixel changed when any channel moved by more than this
MIN_CHANGED = 6           # fewer changed pixels than this: nothing moved
SAMPLE = 1500             # changed pixels used for the search (evenly thinned)
RELIABLE = .35            # the best shift's error must be below this fraction of the no-shift error
WHOLE_VIEW = .6            # above this changed fraction the change is a camera move or a cut, not an object
MIN_NET = 2.5 / SIDE      # net displacement (fraction of the view) below this reads as no clear direction
DOMINANCE = 1.5           # the leading axis must exceed the other by this factor to name one direction


def thumb(rgb):
    """96x96 RGB float32 in 0..1 (box filtered), the only pixels this organ ever holds."""
    from PIL import Image
    x = Image.fromarray(np.asarray(rgb, dtype=np.uint8)).convert('RGB').resize((SIDE, SIDE), Image.BOX)
    return np.asarray(x, dtype=np.float32) / 255.


_SHIFTS = np.array([(dy, dx) for dy in range(-MAX_SHIFT, MAX_SHIFT + 1) for dx in range(-MAX_SHIFT, MAX_SHIFT + 1)])


def step(a, b):
    """Displacement of the main moving region from thumbnail ``a`` to the later thumbnail ``b``.
    Returns {'dx', 'dy' (fractions of the view), 'reliable', 'changed' (fraction of the view)}."""
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    diff = np.abs(a - b).max(-1)
    ys, xs = np.nonzero(diff > CHANGE)
    changed = len(ys) / float(diff.size)
    out = {'dx': 0., 'dy': 0., 'reliable': False, 'changed': round(changed, 4)}
    if len(ys) < MIN_CHANGED:
        return out
    if len(ys) > SAMPLE:
        pick = np.linspace(0, len(ys) - 1, SAMPLE).round().astype(int)
        ys, xs = ys[pick], xs[pick]
    h, w = diff.shape
    src = a[ys, xs]                                          # (n, 3)
    ty = ys[None, :] + _SHIFTS[:, :1]                        # (k, n)
    tx = xs[None, :] + _SHIFTS[:, 1:]
    inside = (ty >= 0) & (ty < h) & (tx >= 0) & (tx < w)
    tgt = b[np.clip(ty, 0, h - 1), np.clip(tx, 0, w - 1)]    # (k, n, 3)
    err = np.abs(tgt - src[None]).max(-1)
    count = inside.sum(1)
    cost = np.where(count >= max(MIN_CHANGED, len(ys) // 2), (err * inside).sum(1) / np.maximum(count, 1), np.inf)
    zero = int(np.flatnonzero((_SHIFTS[:, 0] == 0) & (_SHIFTS[:, 1] == 0))[0])
    best = int(np.argmin(cost))
    if not np.isfinite(cost[best]) or best == zero:
        return out
    dy, dx = _SHIFTS[best]
    out.update(dx=float(dx) / w, dy=float(dy) / h, reliable=bool(cost[best] <= RELIABLE * max(cost[zero], 1e-6)),
               error_ratio=round(float(cost[best] / max(cost[zero], 1e-6)), 4))
    return out


def direction(dx, dy):
    """One word for a net displacement, or None when it is too small or has no leading axis."""
    if max(abs(dx), abs(dy)) < MIN_NET:
        return None
    if abs(dx) >= DOMINANCE * abs(dy):
        return 'right' if dx > 0 else 'left'
    if abs(dy) >= DOMINANCE * abs(dx):
        return 'down' if dy > 0 else 'up'
    return None

