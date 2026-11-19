"""
Morning Puzzles - Lights Plugin (Akari / Light Up)
Encapsulates procedural generation, canonical instruction formatting,
ASCII layout, solution key formatting, and 576-dot thermal raster rendering.
"""

from collections import deque
import random
from typing import List, Tuple, Optional, Dict, Any, Set, Union

from .base import BasePuzzle, BasePuzzleResult
from ._grid_utils import ortho_neighbors
from ..renderer.canvas import (
    THERMAL_WIDTH_DOTS,
    ThermalBitmap,
)


class LightsPuzzle(BasePuzzle):
    """
    Lights (Akari) line-of-sight deduction puzzle.
    Solvers place bulbs to illuminate all white cells without mutual line of sight,
    while matching orthogonal count clues on numbered barrier walls.
    """

    DIFFICULTY_SETTINGS = {
        "easy":    {"size": 6,  "wall_prob": 0.20, "retain_target": 0.85},
        "medium":  {"size": 8,  "wall_prob": 0.20, "retain_target": 0.65},
        "hard":    {"size": 10, "wall_prob": 0.22, "retain_target": 0.45},
        "extreme": {"size": 12, "wall_prob": 0.22, "retain_target": 0.35},
    }

    @property
    def puzzle_id(self) -> str:
        return "lights"

    @property
    def title(self) -> str:
        return "LIGHTS"

    @property
    def has_difficulty(self) -> bool:
        return True

    @property
    def default_difficulty(self) -> str:
        return "medium"

    @property
    def supported_difficulties(self) -> List[str]:
        return ["easy", "medium", "hard", "extreme"]

    def _get_visibility(self, rows: int, cols: int, walls: List[List[int]], r: int, c: int) -> List[Tuple[int, int]]:
        """Returns list of white cells visible from (r, c) including (r, c) itself."""
        if walls[r][c] != -1:
            return []
        vis = [(r, c)]
        for dr in range(r - 1, -1, -1):
            if walls[dr][c] != -1:
                break
            vis.append((dr, c))
        for dr in range(r + 1, rows):
            if walls[dr][c] != -1:
                break
            vis.append((dr, c))
        for dc in range(c - 1, -1, -1):
            if walls[r][dc] != -1:
                break
            vis.append((r, dc))
        for dc in range(c + 1, cols):
            if walls[r][dc] != -1:
                break
            vis.append((r, dc))
        return vis

    def _get_adj_cells(self, rows: int, cols: int, r: int, c: int) -> List[Tuple[int, int]]:
        return ortho_neighbors(r, c, rows, cols)

    def _solve_deductive(self, rows: int, cols: int, walls: List[List[int]]) -> Tuple[bool, Optional[List[List[int]]]]:
        """
        Pure deductive logic solver for Akari / Lights using incremental worklists.
        Returns (is_solved, bulb_grid).
        Only forced logical moves are made; zero guessing/branching.
        """
        total = rows * cols
        flat_walls = [walls[r][c] for r in range(rows) for c in range(cols)]
        white_indices: List[int] = []
        vis_idx: List[Tuple[int, ...]] = [()] * total

        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                if flat_walls[idx] != -1:
                    continue
                white_indices.append(idx)
                vis = [idx]
                for dr in range(r - 1, -1, -1):
                    ni = dr * cols + c
                    if flat_walls[ni] != -1:
                        break
                    vis.append(ni)
                for dr in range(r + 1, rows):
                    ni = dr * cols + c
                    if flat_walls[ni] != -1:
                        break
                    vis.append(ni)
                for dc in range(c - 1, -1, -1):
                    ni = r * cols + dc
                    if flat_walls[ni] != -1:
                        break
                    vis.append(ni)
                for dc in range(c + 1, cols):
                    ni = r * cols + dc
                    if flat_walls[ni] != -1:
                        break
                    vis.append(ni)
                vis_idx[idx] = tuple(vis)

        wall_clues: List[int] = []
        wall_adj: List[Tuple[int, ...]] = []
        cell_adj_walls: List[List[int]] = [[] for _ in range(total)]

        for r in range(rows):
            for c in range(cols):
                clue = flat_walls[r * cols + c]
                if clue < 0:
                    continue
                adj_white = tuple(nr * cols + nc for nr, nc in ortho_neighbors(r, c, rows, cols) if flat_walls[nr * cols + nc] == -1)
                if clue > len(adj_white):
                    return False, None
                w_id = len(wall_clues)
                wall_clues.append(clue)
                wall_adj.append(adj_white)
                for ni in adj_white:
                    cell_adj_walls[ni].append(w_id)

        num_walls = len(wall_clues)
        is_bulb = bytearray(total)
        can_be_bulb = bytearray(1 if v == -1 else 0 for v in flat_walls)
        is_lit = bytearray(total)
        placer_cnt = [len(vis_idx[i]) if flat_walls[i] == -1 else 0 for i in range(total)]

        wall_confirmed = [0] * num_walls
        wall_cand = [len(adj) for adj in wall_adj]
        dirty_walls = deque(range(num_walls))
        in_dirty_walls = bytearray([1] * num_walls)
        forced_unlit = deque()

        for i in white_indices:
            if placer_cnt[i] == 0:
                return False, None
            if placer_cnt[i] == 1:
                forced_unlit.append(i)

        def forbid_bulb(idx: int) -> bool:
            if not can_be_bulb[idx]:
                return True
            if is_bulb[idx]:
                return False
            can_be_bulb[idx] = 0
            for w_id in cell_adj_walls[idx]:
                wall_cand[w_id] -= 1
                if not in_dirty_walls[w_id]:
                    in_dirty_walls[w_id] = 1
                    dirty_walls.append(w_id)
            for v in vis_idx[idx]:
                placer_cnt[v] -= 1
                if not is_lit[v]:
                    if placer_cnt[v] == 0:
                        return False
                    if placer_cnt[v] == 1:
                        forced_unlit.append(v)
            return True

        def place_bulb(idx: int) -> bool:
            if is_bulb[idx]:
                return True
            if not can_be_bulb[idx]:
                return False
            is_bulb[idx] = 1
            is_lit[idx] = 1
            for w_id in cell_adj_walls[idx]:
                wall_confirmed[w_id] += 1
                wall_cand[w_id] -= 1
                if wall_confirmed[w_id] > wall_clues[w_id]:
                    return False
                if not in_dirty_walls[w_id]:
                    in_dirty_walls[w_id] = 1
                    dirty_walls.append(w_id)
            for v in vis_idx[idx]:
                is_lit[v] = 1
                if v != idx and not forbid_bulb(v):
                    return False
            return True

        max_steps = (total + num_walls + 4) * 4
        steps = 0
        while (dirty_walls or forced_unlit) and steps < max_steps:
            steps += 1
            if dirty_walls:
                w_id = dirty_walls.popleft()
                in_dirty_walls[w_id] = 0
                clue = wall_clues[w_id]
                conf = wall_confirmed[w_id]
                cand = wall_cand[w_id]
                if conf > clue or conf + cand < clue:
                    return False, None
                if cand > 0:
                    if conf == clue:
                        for ci in wall_adj[w_id]:
                            if can_be_bulb[ci] and not is_bulb[ci]:
                                if not forbid_bulb(ci):
                                    return False, None
                    elif conf + cand == clue:
                        for ci in wall_adj[w_id]:
                            if can_be_bulb[ci] and not is_bulb[ci]:
                                if not place_bulb(ci):
                                    return False, None
            else:
                u = forced_unlit.popleft()
                if is_lit[u]:
                    continue
                placer = -1
                for p in vis_idx[u]:
                    if can_be_bulb[p]:
                        placer = p
                        break
                if placer == -1 or not place_bulb(placer):
                    return False, None

        for w_id in range(num_walls):
            if wall_confirmed[w_id] != wall_clues[w_id]:
                return False, None

        for idx in white_indices:
            if not is_lit[idx]:
                return False, None

        bulb_grid = [[1 if is_bulb[r * cols + c] else 0 for c in range(cols)] for r in range(rows)]
        return True, bulb_grid

    def generate(
        self,
        difficulty: str = "medium",
        seed: Optional[int] = None,
        **kwargs,
    ) -> BasePuzzleResult:
        rng = self.make_rng(seed)
        diff_key = self.normalize_difficulty(difficulty)
        cfg = self.DIFFICULTY_SETTINGS.get(diff_key, self.DIFFICULTY_SETTINGS["medium"])
        size = cfg["size"]
        rows = cols = size
        wall_prob = cfg["wall_prob"]
        retain_target = cfg["retain_target"]

        for _ in range(300):
            walls = [[-1] * cols for _ in range(rows)]
            num_wall_pairs = int((rows * cols * wall_prob) / 2)
            cells = [(r, c) for r in range(rows) for c in range(cols)]
            rng.shuffle(cells)

            placed = 0
            for r, c in cells:
                sr, sc = rows - 1 - r, cols - 1 - c
                if walls[r][c] == -1 and walls[sr][sc] == -1:
                    walls[r][c] = -2
                    walls[sr][sc] = -2
                    placed += 1
                    if placed >= num_wall_pairs:
                        break

            white_cells = [(r, c) for r in range(rows) for c in range(cols) if walls[r][c] == -1]
            if len(white_cells) < size * size * 0.65:
                continue

            vis_map = {cell: self._get_visibility(rows, cols, walls, cell[0], cell[1]) for cell in white_cells}
            if any(len(vis_map[c]) <= 1 for c in white_cells):
                continue

            # Independent dominating set search
            bulbs = set()
            success = False
            for attempt_dom in range(25):
                bulbs.clear()
                unlit = set(white_cells)
                forbidden = set()

                while unlit:
                    if attempt_dom == 0:
                        target = min(unlit, key=lambda c: sum(1 for v in vis_map[c] if v not in forbidden))
                    else:
                        target = min(unlit, key=lambda c: (sum(1 for v in vis_map[c] if v not in forbidden), rng.random()))
                    placers = [v for v in vis_map[target] if v not in forbidden]
                    if not placers:
                        break
                    if attempt_dom == 0:
                        b = max(placers, key=lambda p: len(set(vis_map[p]) & unlit))
                    else:
                        b = max(placers, key=lambda p: (len(set(vis_map[p]) & unlit), rng.random()))
                    bulbs.add(b)
                    for v in vis_map[b]:
                        unlit.discard(v)
                        forbidden.add(v)

                if not unlit and all(b1 == b2 or b2 not in vis_map[b1] for b1 in bulbs for b2 in bulbs):
                    success = True
                    break

            if not success:
                continue

            # Assign initial wall clues
            for r in range(rows):
                for c in range(cols):
                    if walls[r][c] == -2:
                        adj = self._get_adj_cells(rows, cols, r, c)
                        walls[r][c] = sum(1 for ar, ac in adj if (ar, ac) in bulbs)

            # Check deductive solvability
            can_solve, bulb_grid = self._solve_deductive(rows, cols, walls)
            if not can_solve:
                continue

            # Clue thinning to match difficulty
            all_walls = [(r, c) for r in range(rows) for c in range(cols) if walls[r][c] >= 0]
            rng.shuffle(all_walls)

            for wr, wc in all_walls:
                old_clue = walls[wr][wc]
                walls[wr][wc] = -2  # unnumbered wall

                can_solve, _ = self._solve_deductive(rows, cols, walls)
                if can_solve:
                    current_numbered = sum(1 for r in range(rows) for c in range(cols) if walls[r][c] >= 0)
                    if current_numbered <= len(all_walls) * retain_target:
                        break
                else:
                    walls[wr][wc] = old_clue

            # Final deductive pass
            can_solve, final_grid = self._solve_deductive(rows, cols, walls)
            if can_solve and final_grid is not None:
                bulb_list = [[r, c] for r, c in bulbs]
                total_bulbs = len(bulbs)

                raw_data = {
                    "rows": rows,
                    "cols": cols,
                    "size": size,
                    "puzzle": walls,
                    "solution": final_grid,
                    "bulbs": bulb_list,
                    "total_bulbs": total_bulbs,
                    "difficulty": diff_key,
                }

                instruction = self.get_instruction(raw_data)
                return BasePuzzleResult(
                    puzzle_type=self.puzzle_id,
                    title=self.title,
                    difficulty=diff_key,
                    instruction=instruction,
                    raw_data=raw_data,
                )

        raise RuntimeError(f"Failed to generate valid LIGHTS puzzle for difficulty '{diff_key}'")

    def get_instruction(self, puzzle_data: Union[BasePuzzleResult, Dict[str, Any]]) -> str:
        total_bulbs = puzzle_data.get("total_bulbs", 10)
        return f"Place {total_bulbs} bulbs to light corridors; none can face each other; numbers show bulbs sharing an edge."

    def format_ascii_puzzle(self, puzzle_data: Union[BasePuzzleResult, Dict[str, Any]]) -> str:
        rows = puzzle_data.get("rows", 8)
        cols = puzzle_data.get("cols", 8)
        puzzle = puzzle_data.get("puzzle", [])
        total_bulbs = puzzle_data.get("total_bulbs", 10)

        lines = [f"TOTAL BULBS: {total_bulbs}", ""]
        compact = cols >= 11  # Keep 12x12 within 48-col ESC/POS Font A limit
        indent = "  " if compact else "   "
        sep = indent + "+" + ("--+" if compact else "---+") * cols
        lines.append(sep)

        for r in range(rows):
            line = indent + "|"
            for c in range(cols):
                val = puzzle[r][c] if r < len(puzzle) and c < len(puzzle[r]) else -1
                if compact:
                    if val >= 0:
                        line += f"{val} |"
                    elif val == -2:
                        line += "# |"
                    else:
                        line += "  |"
                else:
                    if val >= 0:
                        line += f" {val} |"
                    elif val == -2:
                        line += " # |"
                    else:
                        line += "   |"
            lines.append(line)
            lines.append(sep)

        return "\n".join(lines)

    def format_solution_key(self, puzzle_data: Union[BasePuzzleResult, Dict[str, Any]]) -> List[str]:
        rows = puzzle_data.get("rows", 8)
        cols = puzzle_data.get("cols", 8)
        puzzle = puzzle_data.get("puzzle", [])
        sol = puzzle_data.get("solution", [])
        if not sol:
            return []

        lines = []
        for r in range(rows):
            row_str = "      "
            for c in range(cols):
                p_val = puzzle[r][c] if r < len(puzzle) and c < len(puzzle[r]) else -1
                if p_val >= 0:
                    row_str += f"{p_val} "
                elif p_val == -2:
                    row_str += "# "
                elif r < len(sol) and c < len(sol[r]) and sol[r][c] == 1:
                    row_str += "* "
                else:
                    row_str += ". "
            lines.append(row_str)

        return lines

    def render_raster(
        self,
        puzzle_data: Union[BasePuzzleResult, Dict[str, Any]],
        target_width: int = THERMAL_WIDTH_DOTS,
    ) -> bytes:
        size = puzzle_data.get("size", puzzle_data.get("rows", 8))
        rows = cols = size
        puzzle = puzzle_data.get("puzzle", [])

        padding = 24
        board_size = target_width - padding * 2
        cell_size = board_size // size
        actual_board = cell_size * size
        total_h = padding + actual_board + padding

        tb = ThermalBitmap(target_width, total_h)

        # Outer grid border (Tier 1: 4px)
        tb.draw_rect(padding, padding, actual_board, actual_board, thickness=4)

        # Internal grid dividers (Tier 4: 1px)
        for r in range(1, size):
            tb.draw_hline(padding, padding + r * cell_size, actual_board, thickness=1)
        for c in range(1, size):
            tb.draw_vline(padding + c * cell_size, padding, actual_board, thickness=1)

        # Render barrier cells: Pattern 1 diagonal hatch (like Stars) + circular white badge with black scale-3 numeral
        for r in range(rows):
            for c in range(cols):
                val = puzzle[r][c] if r < len(puzzle) and c < len(puzzle[r]) else -1
                if val != -1:
                    x0 = padding + c * cell_size
                    y0 = padding + r * cell_size
                    tb.fill_hatch(x0, y0, cell_size, cell_size, 1)

                    if val >= 0:
                        mid_x = x0 + cell_size // 2
                        mid_y = y0 + cell_size // 2
                        r_rad = max(13, min(cell_size // 2 - 4, 16))
                        tb.fill_circle(mid_x, mid_y, r_rad, color=0)

                        cx = x0 + (cell_size - 18) // 2
                        cy = y0 + (cell_size - 21) // 2
                        tb.draw_char(cx, cy, str(val), scale=3, color=1)

        return tb.to_escpos()

    def verify_accuracy(
        self,
        puzzle_data: Union[BasePuzzleResult, Dict[str, Any]],
    ) -> Tuple[bool, str]:
        puzzle = puzzle_data.get("puzzle")
        solution = puzzle_data.get("solution")
        bulbs = puzzle_data.get("bulbs")

        if not puzzle or not isinstance(puzzle, list):
            return False, "Lights puzzle grid missing or invalid"
        if not solution or not isinstance(solution, list):
            return False, "Lights solution grid missing or invalid"

        rows = len(puzzle)
        cols = len(puzzle[0]) if rows > 0 else 0
        if rows != cols:
            return False, f"Lights grid must be square, got {rows}x{cols}"

        # 1. Check bulb placements
        bulb_coords = set()
        for r in range(rows):
            for c in range(cols):
                if solution[r][c] == 1:
                    if puzzle[r][c] != -1:
                        return False, f"Bulb placed in wall cell ({r}, {c})"
                    bulb_coords.add((r, c))

        if bulbs is not None and len(bulb_coords) != len(bulbs):
            return False, f"Bulbs count mismatch: solution has {len(bulb_coords)}, data has {len(bulbs)}"

        # 2. No two bulbs can illuminate each other
        vis_map = {cell: set(self._get_visibility(rows, cols, puzzle, cell[0], cell[1]))
                   for r in range(rows) for c in range(cols) if puzzle[r][c] == -1 for cell in [(r, c)]}

        for b1 in bulb_coords:
            for b2 in bulb_coords:
                if b1 != b2 and b2 in vis_map.get(b1, set()):
                    return False, f"Bulbs at {b1} and {b2} shine on each other"

        # 3. All white cells must be lit
        lit_cells = set()
        for b in bulb_coords:
            lit_cells.update(vis_map.get(b, set()))

        for r in range(rows):
            for c in range(cols):
                if puzzle[r][c] == -1 and (r, c) not in lit_cells:
                    return False, f"White cell ({r}, {c}) is not illuminated"

        # 4. Numbered wall clues must be strictly satisfied
        for r in range(rows):
            for c in range(cols):
                clue = puzzle[r][c]
                if clue >= 0:
                    adj = self._get_adj_cells(rows, cols, r, c)
                    adj_bulbs = sum(1 for ar, ac in adj if (ar, ac) in bulb_coords)
                    if adj_bulbs != clue:
                        return False, f"Wall at ({r}, {c}) has clue {clue} but has {adj_bulbs} adjacent bulbs"

        # 5. Logical solvability check
        can_solve, deduced_solution = self._solve_deductive(rows, cols, puzzle)
        if not can_solve:
            return False, "Lights puzzle cannot be solved by pure deductive logic"
        if deduced_solution != solution:
            return False, "Deduced solution does not match generated solution"

        return True, "All rules satisfied"
