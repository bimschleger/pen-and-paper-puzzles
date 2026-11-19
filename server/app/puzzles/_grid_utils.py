"""
Shared grid neighbor and orthogonal connectivity utilities for puzzle plugins.
"""

from collections import deque
from typing import Collection, List, Tuple


def ortho_neighbors(r: int, c: int, rows: int, cols: int) -> List[Tuple[int, int]]:
    """Return in-bounds 4-connected orthogonal neighbors for cell (r, c)."""
    res: List[Tuple[int, int]] = []
    if r > 0:
        res.append((r - 1, c))
    if r + 1 < rows:
        res.append((r + 1, c))
    if c > 0:
        res.append((r, c - 1))
    if c + 1 < cols:
        res.append((r, c + 1))
    return res


def all_neighbors(r: int, c: int, rows: int, cols: int) -> List[Tuple[int, int]]:
    """Return in-bounds 8-connected orthogonal and diagonal neighbors for cell (r, c)."""
    r0 = r - 1 if r > 0 else 0
    r1 = r + 1 if r + 1 < rows else rows - 1
    c0 = c - 1 if c > 0 else 0
    c1 = c + 1 if c + 1 < cols else cols - 1
    res: List[Tuple[int, int]] = []
    for nr in range(r0, r1 + 1):
        for nc in range(c0, c1 + 1):
            if nr != r or nc != c:
                res.append((nr, nc))
    return res


def is_orthogonally_connected(cells: Collection[Tuple[int, int]]) -> bool:
    """Return True if all (r, c) coordinates form a single 4-connected component."""
    if not cells:
        return True
    remaining = set(cells)
    start = next(iter(remaining))
    remaining.remove(start)
    queue = deque([start])
    while queue:
        cr, cc = queue.popleft()
        for nbr in ((cr - 1, cc), (cr + 1, cc), (cr, cc - 1), (cr, cc + 1)):
            if nbr in remaining:
                remaining.remove(nbr)
                queue.append(nbr)
    return not remaining
