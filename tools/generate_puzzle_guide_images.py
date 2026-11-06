#!/usr/bin/env python3
"""
Morning Puzzles - Puzzle Guide Image Generator
Generates high-contrast 1-bit thermal PNG images for Starting Position and
Completed Solution states for all 20 featured games in Pen and Paper Puzzles.

Assets are written directly to docs/images/puzzles/<puzzle_key>_start.png
and docs/images/puzzles/<puzzle_key>_solved.png.
"""

import math
import os
import struct
import sys
import zlib
from typing import Dict, Any, Tuple, List, Optional

# Ensure server package is on path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
SERVER_DIR = os.path.join(ROOT_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server.app.renderer.canvas import ThermalBitmap, THERMAL_WIDTH_DOTS
from server.app.puzzles.registry import DEFAULT_REGISTRY

OUTPUT_DIR = os.path.join(ROOT_DIR, "docs", "images", "puzzles")


def bitmap_to_png(buffer: bytes, width: int, height: int) -> bytes:
    """
    Converts 1-bit raw bitmap buffer (where 1=ink/black, 0=paper/white)
    into a valid standard grayscale PNG (bit depth 1, color type 0).
    """
    width_bytes = (width + 7) // 8
    raw_rows = []
    for y in range(height):
        row = buffer[y * width_bytes : (y + 1) * width_bytes]
        # In PNG 1-bit grayscale: 0 is black (0% luminance), 1 is white (100% luminance).
        # In ThermalBitmap: 1 is ink (black), 0 is paper (white).
        # We invert so paper (0) -> white (1), and ink (1) -> black (0).
        inv_row = bytes((~b) & 0xFF for b in row)
        raw_rows.append(b"\x00" + inv_row)

    compressed = zlib.compress(b"".join(raw_rows), 9)

    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    png = b"\x89PNG\r\n\x1a\n"
    # IHDR: width, height, bit depth 1, color type 0 (grayscale), compression 0, filter 0, interlace 0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    png += make_chunk(b"IHDR", ihdr_data)
    png += make_chunk(b"IDAT", compressed)
    png += make_chunk(b"IEND", b"")
    return png


def escpos_to_thermal_bitmap(escpos_data: bytes) -> ThermalBitmap:
    """
    Unwraps an ESC/POS GS v 0 raster byte stream into a ThermalBitmap instance.
    ESC/POS GS v 0 format: 0x1D 0x76 0x30 0x00 xL xH yL yH [data...]
    """
    if len(escpos_data) < 8 or escpos_data[:4] != b"\x1d\x76\x30\x00":
        raise ValueError("Invalid ESC/POS GS v 0 raster header")
    xl, xh, yl, yh = escpos_data[4], escpos_data[5], escpos_data[6], escpos_data[7]
    width_bytes = xl | (xh << 8)
    height = yl | (yh << 8)
    width = width_bytes * 8

    tb = ThermalBitmap(width, height)
    tb.buffer = bytearray(escpos_data[8 : 8 + width_bytes * height])
    return tb


def save_png(tb: ThermalBitmap, filename: str):
    png_bytes = bitmap_to_png(tb.buffer, tb.width, tb.height)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(png_bytes)
    print(f"  [SAVED] {filename} ({tb.width}x{tb.height}, {len(png_bytes)} bytes)")


# --- Custom Solved State Renderers for Puzzles needing custom annotations ---

def render_solved_sudoku(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    raster = plugin.render_raster({**res, "grid": res["solution"]})
    return escpos_to_thermal_bitmap(raster)


def render_solved_sudokito(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    raster = plugin.render_raster({**res, "grid": res["solution"]})
    return escpos_to_thermal_bitmap(raster)


def render_solved_binary(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    raster = plugin.render_raster({**res, "puzzle": res["solution"]})
    return escpos_to_thermal_bitmap(raster)


def render_solved_tango(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    raster = plugin.render_raster({**res, "puzzle": res["solution"]})
    return escpos_to_thermal_bitmap(raster)


def render_solved_inequality(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    size = res["size"]
    sol = res["solution"]
    all_givens = [(r, c, sol[r][c]) for r in range(size) for c in range(size)]
    raster = plugin.render_raster({**res, "givens": all_givens})
    return escpos_to_thermal_bitmap(raster)


def render_solved_towers(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    size = res["size"]
    diff_key = str(res.get("difficulty", "medium")).lower()
    cfg = plugin.DIFFICULTY_CONFIGS.get(diff_key, plugin.DIFFICULTY_CONFIGS["medium"])
    cell_size = cfg["cell_size"]
    grid_w = size * cell_size
    total_h = cfg["height"]
    grid_x = (THERMAL_WIDTH_DOTS - grid_w) // 2
    grid_y = (total_h - grid_w) // 2
    sol = res["solution"]

    for r in range(size):
        for c in range(size):
            tx = grid_x + c * cell_size + (cell_size - 18) // 2
            ty = grid_y + r * cell_size + (cell_size - 21) // 2
            start_tb.draw_char(tx, ty, str(sol[r][c]), scale=3)
    return start_tb


def render_solved_killer(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    size = res.get("size", 4)
    padding = 24
    board_size = THERMAL_WIDTH_DOTS - padding * 2
    c_size = board_size // size
    sol = res["solution"]

    for r in range(size):
        for c in range(size):
            cx = padding + c * c_size + (c_size - 18) // 2
            cy = padding + r * c_size + (c_size - 21) // 2
            start_tb.draw_char(cx, cy, str(sol[r][c]), scale=3)
    return start_tb


def render_solved_stars(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    size = res.get("grid_size", res.get("size", 8))
    padding = 24
    board_size = THERMAL_WIDTH_DOTS - padding * 2
    cell_size = board_size // size
    stars = res.get("stars_solution", [])

    for r, c in stars:
        cx = padding + c * cell_size + cell_size // 2
        cy = padding + r * cell_size + cell_size // 2
        rad = max(14, cell_size // 3)
        # Circular white badge cutout & crisp 2px border
        start_tb.fill_circle(cx, cy, rad, color=0)
        start_tb.draw_circle(cx, cy, rad, thickness=2, color=1)
        # Bold star asterisk inside badge
        start_tb.draw_char(cx - 9, cy - 10, "*", scale=3)
    return start_tb


def render_solved_nonogram(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    size = res.get("rows", res.get("size", 5))
    sol = res.get("solution", [])
    row_clues = res.get("row_clues", [])
    col_clues = res.get("col_clues", [])

    padding = 24
    inner_width = THERMAL_WIDTH_DOTS - padding * 2
    cell_size = 76 if size <= 5 else (50 if size <= 8 else (40 if size <= 10 else 26))
    grid_size = cell_size * size
    row_clue_width = inner_width - grid_size
    col_clue_item_h = max(24, int(cell_size * 0.55))
    max_col_clues = max((len(c) for c in col_clues), default=1)
    col_clue_height = max(50, max_col_clues * col_clue_item_h + 16)

    grid_x = padding + row_clue_width
    grid_y = 12 + col_clue_height

    for r in range(size):
        for c in range(size):
            if r < len(sol) and c < len(sol[r]) and sol[r][c] == 1:
                # Fill shaded cell with solid inset or Pattern 1 diagonal hatch
                x0 = grid_x + c * cell_size + 2
                y0 = grid_y + r * cell_size + 2
                w = cell_size - 4
                h = cell_size - 4
                start_tb.fill_hatch(x0, y0, w, h, 1)
                start_tb.draw_rect(x0, y0, w, h, thickness=2)
    return start_tb


def render_solved_wordsearch(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    grid = res.get("grid", [])
    words = res.get("words", [])
    placements = res.get("placements", {})
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 12

    cell_size = (THERMAL_WIDTH_DOTS - 48) // cols
    inner_width = cell_size * cols
    padding = (THERMAL_WIDTH_DOTS - inner_width) // 2
    grid_y = 12
    grid_h = cell_size * rows

    dir_deltas = {
        "E": (0, 1), "W": (0, -1),
        "S": (1, 0), "N": (-1, 0),
        "SE": (1, 1), "NW": (-1, -1),
        "SW": (1, -1), "NE": (-1, 1)
    }

    # Draw highlights over placed words
    for word, place in placements.items():
        sr = place["row"]
        sc = place["col"]
        d = place["dir"]
        dr, dc = dir_deltas.get(d, (0, 1))

        for k in range(len(word)):
            r = sr + k * dr
            c = sc + k * dc
            cx = padding + c * cell_size + 3
            cy = grid_y + r * cell_size + 3
            start_tb.draw_rect(cx, cy, cell_size - 6, cell_size - 6, thickness=2)

    # Check off words in checklist
    cur_y = grid_y + grid_h + 16 + 18 + 28
    col_w = inner_width // 2
    for i, word in enumerate(words):
        col_idx = i % 2
        row_idx = i // 2
        ix = padding + col_idx * col_w
        iy = cur_y + row_idx * 28
        # Draw checkmark inside box
        start_tb.draw_char(ix + 2, iy + 2, "X", scale=2)
        # Strike through word
        text_w = len(word) * 12
        start_tb.draw_hline(ix + 24, iy + 10, text_w, thickness=2)

    return start_tb


def render_solved_mines(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    rows = res.get("rows", 8)
    cols = res.get("cols", 8)
    mine_coords = set(res.get("mine_coords", []))
    sol = res.get("solution", [])

    padding = 24
    inner_width = THERMAL_WIDTH_DOTS - padding * 2
    cell_size = inner_width // cols
    badge_h = 36
    grid_y = 12 + badge_h + 12

    for r in range(rows):
        for c in range(cols):
            cx = padding + c * cell_size + (cell_size - 18) // 2
            cy = grid_y + r * cell_size + (cell_size - 21) // 2
            mid_x = padding + c * cell_size + cell_size // 2
            mid_y = grid_y + r * cell_size + cell_size // 2

            if (r, c) in mine_coords or (r < len(sol) and c < len(sol[r]) and sol[r][c] == -1):
                # Draw mine glyph: filled circular body with spikes
                start_tb.fill_circle(mid_x, mid_y, 10, color=1)
                start_tb.draw_line(mid_x - 14, mid_y, mid_x + 14, mid_y, thickness=2)
                start_tb.draw_line(mid_x, mid_y - 14, mid_x, mid_y + 14, thickness=2)
                start_tb.draw_char(cx, cy, "*", scale=3, color=0)
            elif r < len(sol) and c < len(sol[r]):
                val = sol[r][c]
                if val > 0:
                    start_tb.draw_char(cx, cy, str(val), scale=3)
    return start_tb


def render_solved_tents(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    size = res.get("size", 8)
    padding = 24
    inner_width = THERMAL_WIDTH_DOTS - padding * 2
    margin_w = 48
    board_size = inner_width - margin_w
    cell_size = board_size // size
    grid_x = padding + margin_w
    grid_y = padding + margin_w
    tents = res.get("tents", [])

    for r, c in tents:
        mid_x = grid_x + c * cell_size + cell_size // 2
        mid_y = grid_y + r * cell_size + cell_size // 2
        # Draw clean geometric tent triangle with entrance slit
        poly = [(mid_x, mid_y - 13), (mid_x + 14, mid_y + 12), (mid_x - 14, mid_y + 12)]
        start_tb.draw_polygon(poly, thickness=2)
        start_tb.draw_line(mid_x, mid_y - 10, mid_x, mid_y + 12, thickness=1)
    return start_tb


def render_solved_bridges(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    size = res.get("size", 8)
    islands = res.get("islands", [])
    bridges = res.get("solution_bridges", [])

    padding = 32
    board_size = THERMAL_WIDTH_DOTS - padding * 2
    step = board_size // (size - 1) if size > 1 else board_size
    total_h = padding + board_size + padding
    island_radius = max(18, min(24, step // 3))

    tb = ThermalBitmap(THERMAL_WIDTH_DOTS, total_h)

    # 1. Draw bridges first so island circles can occlude cleanly
    for b in bridges:
        r1, c1 = b["r1"], b["c1"]
        r2, c2 = b["r2"], b["c2"]
        cnt = b.get("count", 1)

        x1 = padding + c1 * step
        y1 = padding + r1 * step
        x2 = padding + c2 * step
        y2 = padding + r2 * step

        if r1 == r2:  # Horizontal
            if cnt == 1:
                tb.draw_hline(min(x1, x2), y1 - 1, abs(x2 - x1), thickness=2)
            else:
                tb.draw_hline(min(x1, x2), y1 - 5, abs(x2 - x1), thickness=2)
                tb.draw_hline(min(x1, x2), y1 + 3, abs(x2 - x1), thickness=2)
        elif c1 == c2:  # Vertical
            if cnt == 1:
                tb.draw_vline(x1 - 1, min(y1, y2), abs(y2 - y1), thickness=2)
            else:
                tb.draw_vline(x1 - 5, min(y1, y2), abs(y2 - y1), thickness=2)
                tb.draw_vline(x1 + 3, min(y1, y2), abs(y2 - y1), thickness=2)

    # 2. Draw islands on top
    for isl in islands:
        r, c = isl.get("r", 0), isl.get("c", 0)
        count = isl.get("count", 1)
        cx = padding + c * step
        cy = padding + r * step

        tb.fill_circle(cx, cy, island_radius, color=0)
        tb.draw_circle(cx, cy, island_radius, thickness=2, color=1)
        tb.draw_char(cx - 5, cy - 7, str(count), scale=2, color=1)

    return tb


def render_solved_cryptogram(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    phrase = str(res.get("phrase", "")).upper()
    author = str(res.get("author", "")).strip()
    padding = 24
    inner_width = THERMAL_WIDTH_DOTS - padding * 2

    # Break phrase into matching lines
    words = phrase.split(" ")
    lines = []
    curr = ""
    for w in words:
        if not curr:
            curr = w
        elif len(curr) + 1 + len(w) <= 24:
            curr += " " + w
        else:
            lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)

    row_height = 76
    row_gap = 20
    cur_y = 16

    for line_str in lines:
        line_len = len(line_str)
        char_w = min(24, inner_width // max(1, line_len))
        start_x = padding + (inner_width - line_len * char_w) // 2
        text_y = cur_y + 4

        for idx, ch in enumerate(line_str):
            cx = start_x + idx * char_w
            if ch.isalpha():
                start_tb.draw_char(cx + 4, text_y, ch, scale=2, color=1)
        cur_y += row_height + row_gap

    return start_tb


def render_solved_jumble(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    words = res.get("words", [])
    answer = res.get("answer", "")
    scrambled = res.get("scrambled", [])
    count = len(words)
    padding = 24
    inner_width = THERMAL_WIDTH_DOTS - padding * 2
    clue_size = 66
    word_gap = 14

    cur_y = 12
    # 1. Fill in unscrambled words in row 2 of clue blocks
    for i in range(count):
        item = words[i]
        word = (item.get("original", "") if isinstance(item, dict) else str(item)).upper()
        length = len(word)
        for c in range(length):
            cx0 = padding + c * clue_size
            char_x = cx0 + (clue_size - 18) // 2
            char_y = cur_y + 66 + (clue_size - 21) // 2
            start_tb.draw_char(char_x, char_y, word[c], scale=3)
        cur_y += 132 + word_gap

    # 2. Fill in final answer
    riddle = res.get("riddle", "")
    riddle_lines = [riddle] if len(riddle) <= 28 else [riddle[:28], riddle[28:]]
    cur_y += 16 + 20 + len(riddle_lines) * 28 + 22 + 20 + 192 + 22

    ans_box_w = 48
    ans_box_h = 56
    ans_words = answer.split(" ")
    line_w = sum(len(w) * ans_box_w for w in ans_words) + max(0, len(ans_words) - 1) * 16
    start_x = padding + max(0, (inner_width - line_w) // 2)

    ax = start_x
    for w in ans_words:
        for idx, ch in enumerate(w):
            if ch.isalpha():
                cx = ax + idx * ans_box_w + (ans_box_w - 18) // 2
                cy = cur_y + (ans_box_h - 21) // 2
                start_tb.draw_char(cx, cy, ch.upper(), scale=3)
        ax += len(w) * ans_box_w + 16

    return start_tb


def render_solved_ladder(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_word = str(res.get("start_word", "COLD")).upper()
    target_word = str(res.get("target_word", "WARM")).upper()
    solution = [str(w).upper() for w in res.get("solution", [])]
    total_rungs = len(solution) if solution else 5
    word_len = len(start_word)

    tile_size = 66
    gap_y = 14
    box_width = word_len * tile_size
    box_x = (THERMAL_WIDTH_DOTS - box_width) // 2
    gap_x = 14
    margin_top = 24
    ladder_height = total_rungs * tile_size + (total_rungs - 1) * gap_y
    total_height = (margin_top + ladder_height + margin_top + 7) & ~7

    tb = ThermalBitmap(THERMAL_WIDTH_DOTS, total_height)

    for r in range(total_rungs):
        ry = margin_top + r * (tile_size + gap_y)
        num_text = f"{r + 1}."
        text_x = box_x - gap_x - len(num_text) * 12
        text_y = ry + (tile_size - 14) // 2
        tb.draw_text(text_x, text_y, num_text, scale=2, color=1)

        tb.draw_rect(box_x, ry, box_width, tile_size, thickness=2, color=1)
        for c in range(1, word_len):
            div_x = box_x + c * tile_size
            tb.draw_vline(div_x, ry, tile_size, thickness=1, color=1)

        # Draw all solution words
        word = solution[r] if r < len(solution) else ""
        for c in range(word_len):
            if c < len(word):
                char_x = box_x + c * tile_size + (tile_size - 15) // 2
                char_y = ry + (tile_size - 21) // 2
                tb.draw_char(char_x, char_y, word[c], scale=3, color=1)

    return tb


def render_solved_wheel(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    root_word = str(res.get("root_word", "EXAMPLE")).upper()
    words = res.get("words", [])

    # Annotate bottom benchmarks box with solution solutions
    box_y = 330
    tb = ThermalBitmap(THERMAL_WIDTH_DOTS, 480)
    # Copy start_tb into new buffer
    tb.buffer[:len(start_tb.buffer)] = start_tb.buffer[:]

    # Display Pangram and sample solution words
    tb.draw_centered_text(340, f"9-LETTER PANGRAM: {root_word}", scale=2)
    sample_words = ", ".join([w.upper() for w in words[:6]])
    if len(words) > 6:
        sample_words += f" ... (+{len(words) - 6} more)"
    tb.draw_centered_text(370, f"SOLUTIONS: {sample_words}", scale=2)
    return tb


def render_solved_lights(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    size = res.get("size", res.get("rows", 8))
    rows = cols = size
    padding = 24
    board_size = THERMAL_WIDTH_DOTS - padding * 2
    cell_size = board_size // size
    bulbs = res.get("bulbs", [])
    sol = res.get("solution", [])

    for r in range(rows):
        for c in range(cols):
            is_bulb = (r, c) in bulbs or (r < len(sol) and c < len(sol[r]) and sol[r][c] == 1)
            if is_bulb:
                cx = padding + c * cell_size + cell_size // 2
                cy = padding + r * cell_size + cell_size // 2
                rad = max(12, cell_size // 3)
                # Draw lightbulb icon: filled circle + rays
                start_tb.fill_circle(cx, cy, rad, color=1)
                start_tb.fill_circle(cx, cy, rad - 3, color=0)
                start_tb.draw_char(cx - 9, cy - 10, "*", scale=3, color=1)
    return start_tb


def render_solved_loop(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    n = res.get("size", 7)
    clues = res.get("clues", [])
    diff = res.get("difficulty", "medium").lower()
    cfg = plugin.DIFFICULTY_SETTINGS.get(diff, plugin.DIFFICULTY_SETTINGS["medium"])
    cell_size = cfg["cell_size"]
    padding = cfg["padding"]
    board_size = cell_size * n
    left_margin = (THERMAL_WIDTH_DOTS - board_size) // 2
    total_h = 576

    tb = ThermalBitmap(THERMAL_WIDTH_DOTS, total_h)
    sol_h = res.get("solution_h", [])
    sol_v = res.get("solution_v", [])

    # 1. Draw loop edges (Tier 1: 4px thick lines)
    for r in range(n + 1):
        for c in range(n):
            if r < len(sol_h) and c < len(sol_h[r]) and sol_h[r][c] == 1:
                x0 = left_margin + c * cell_size
                y0 = padding + r * cell_size - 1
                tb.draw_hline(x0, y0, cell_size, thickness=4, color=1)

    for r in range(n):
        for c in range(n + 1):
            if r < len(sol_v) and c < len(sol_v[r]) and sol_v[r][c] == 1:
                x0 = left_margin + c * cell_size - 1
                y0 = padding + r * cell_size
                tb.draw_vline(x0, y0, cell_size, thickness=4, color=1)

    # 2. Draw lattice dots (3px radius filled circles)
    dot_radius = 3
    for r in range(n + 1):
        py = padding + r * cell_size
        for c in range(n + 1):
            px = left_margin + c * cell_size
            tb.fill_circle(px, py, dot_radius, color=1)

    # 3. Draw clue numbers (scale 3)
    for r in range(n):
        for c in range(n):
            k = clues[r][c] if r < len(clues) and c < len(clues[r]) else -1
            if k >= 0:
                tx = left_margin + c * cell_size + (cell_size - 18) // 2
                ty = padding + r * cell_size + (cell_size - 21) // 2
                tb.draw_char(tx, ty, str(k), scale=3, color=1)

    return tb


def render_solved_maze(plugin, res: Dict[str, Any]) -> ThermalBitmap:
    start_tb = escpos_to_thermal_bitmap(plugin.render_raster(res))
    n = res.get("size", 20)
    diff = res.get("difficulty", "medium").lower()
    cfg = plugin.DIFFICULTY_SETTINGS.get(diff, plugin.DIFFICULTY_SETTINGS["medium"])
    cell_size = cfg["cell_size"]
    board_size = 480
    left_margin = (THERMAL_WIDTH_DOTS - board_size) // 2  # 48
    top_margin = (576 - board_size) // 2           # 48

    path = res.get("solution_path", [])
    if path:
        # Draw solution path line through cell centers
        for i in range(len(path) - 1):
            r1, c1 = path[i]
            r2, c2 = path[i + 1]
            x1 = left_margin + c1 * cell_size + cell_size // 2
            y1 = top_margin + r1 * cell_size + cell_size // 2
            x2 = left_margin + c2 * cell_size + cell_size // 2
            y2 = top_margin + r2 * cell_size + cell_size // 2
            start_tb.draw_line(x1, y1, x2, y2, thickness=3, color=1)

        # Highlight entrance and exit markers
        er, ec = path[0]
        xr = left_margin + ec * cell_size + cell_size // 2
        yr = top_margin + er * cell_size + cell_size // 2
        start_tb.fill_circle(xr, yr, 5, color=1)

        er2, ec2 = path[-1]
        xr2 = left_margin + ec2 * cell_size + cell_size // 2
        yr2 = top_margin + er2 * cell_size + cell_size // 2
        start_tb.fill_circle(xr2, yr2, 5, color=1)

    return start_tb


SOLVED_RENDERERS = {
    "sudoku": render_solved_sudoku,
    "sudokito": render_solved_sudokito,
    "binary": render_solved_binary,
    "tango": render_solved_tango,
    "inequality": render_solved_inequality,
    "towers": render_solved_towers,
    "killer": render_solved_killer,
    "queens": render_solved_stars,
    "nonogram": render_solved_nonogram,
    "wordsearch": render_solved_wordsearch,
    "mines": render_solved_mines,
    "tents": render_solved_tents,
    "bridges": render_solved_bridges,
    "cryptogram": render_solved_cryptogram,
    "jumble": render_solved_jumble,
    "ladder": render_solved_ladder,
    "wheel": render_solved_wheel,
    "lights": render_solved_lights,
    "loop": render_solved_loop,
    "maze": render_solved_maze,
}

PUZZLE_KEY_ALIASES = {
    "queens": "stars",
    "wordsearch": "search",
}


def generate_puzzle_guide_markdown():
    """
    Builds docs/PUZZLE_GUIDE.md using canonical data from server/data/game_rules.json
    and links to the 40 generated start/solved puzzle images.
    """
    import json
    import re

    readme_path = os.path.join(ROOT_DIR, "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_text = f.read()

    # Extract aliases from README.md
    item_pattern = re.compile(
        r"^\s*(\d+)\.\s+\*\*([^*]+)\*\*(?:\s+\*([^*]+)\*)?:\s*(.+)$",
        re.MULTILINE,
    )
    alias_map = {}
    for m in item_pattern.finditer(readme_text):
        title = m.group(2).strip()
        alias = m.group(3).strip("() ") if m.group(3) else ""
        alias_map[title.upper()] = alias

    rules_path = os.path.join(SERVER_DIR, "data", "game_rules.json")
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)

    games = rules_data.get("games", [])
    lines = [
        "# Pen and Paper Puzzles: Comprehensive Visual Puzzle Guide 📰🧩\n",
        "Welcome to the comprehensive visual catalog and player guide for **Pen and Paper Puzzles**! This guide illustrates each of the **20 open-source puzzle types** printed directly to your physical 80mm commercial thermal receipt printer.\n",
        "For each puzzle, you will find:",
        "- **Canonical One-Sentence Gameplay Instruction** (conforming to the $\\le 100$-character thermal standard)",
        "- **Core Objective & Rules of Play**",
        "- **Authentic Thermal Board Comparison**: Side-by-side **Starting Position** vs. **Completed Solution**",
        "- **Opening Deduction Anchors**: Proven opening strategies to start solving without guessing",
        "- **Frequently Asked Questions (FAQ)**\n",
        "---\n",
        "## 📑 Table of Contents\n",
    ]

    for idx, g in enumerate(games, 1):
        key = g["key"]
        title = g["title"]
        alias = alias_map.get(title.upper(), "")
        alias_str = f" *({alias})*" if alias else ""
        lines.append(f"{idx}. [{title}{alias_str}](#{key})")

    lines.append("\n---\n")

    for idx, g in enumerate(games, 1):
        key = g["key"]
        title = g["title"]
        alias = alias_map.get(title.upper(), "")
        inst = g["instruction"]
        obj = g["objective"]
        rules = g.get("rules", [])
        anchors = g.get("opening_anchors", [])
        faqs = g.get("faq", [])

        lines.append(f'<a id="{key}" name="{key}"></a>')
        lines.append(f"## {idx}. --- {title} ---")
        if alias:
            lines.append(f"**Also Known As**: *{alias}*\n")
        lines.append(f"> **Instruction**: `{inst}`\n")
        lines.append("### 🎯 Objective")
        lines.append(f"{obj}\n")
        lines.append("### 📜 Rules of Play")
        for r in rules:
            lines.append(f"- {r}")
        lines.append("\n### 🖼️ Board Comparison: Starting Position vs. Completed Solution")
        lines.append("| Starting Position (Fresh Receipt) | Completed Solution (Solved Grid) |")
        lines.append("| :---: | :---: |")
        lines.append(f"| ![{title} Starting Position](images/puzzles/{key}_start.png) | ![{title} Completed Solution](images/puzzles/{key}_solved.png) |\n")

        if anchors:
            lines.append("### 💡 Opening Deduction Anchors")
            for a in anchors:
                lines.append(f"- {a}")
            lines.append("")

        if faqs:
            lines.append("### ❓ Frequently Asked Questions")
            for f in faqs:
                lines.append(f"* **Q: {f['q']}**")
                lines.append(f"  **A**: {f['a']}")
            lines.append("")

        lines.append("---\n")

    guide_path = os.path.join(ROOT_DIR, "docs", "PUZZLE_GUIDE.md")
    with open(guide_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[SAVED] Generated comprehensive guide: {guide_path} ({len(lines)} lines)")


def generate_all_images():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plugins = DEFAULT_REGISTRY.get_all()
    print(f"Generating start and solved PNG images for {len(plugins)} games into {OUTPUT_DIR}...\n")

    for idx, plugin in enumerate(plugins):
        pid = plugin.puzzle_id.lower()
        key = PUZZLE_KEY_ALIASES.get(pid, pid)
        title = plugin.title.upper()
        print(f"[{idx + 1}/{len(plugins)}] Generating {title} ({key})...")

        # Deterministic generation with seed=42 and beginner-friendly difficulty
        try:
            res = plugin.generate(seed=42, difficulty="easy")
        except Exception:
            try:
                res = plugin.generate(seed=42, difficulty="medium")
            except Exception:
                res = plugin.generate(seed=42)

        # 1. Starting position
        start_raster = plugin.render_raster(res)
        start_tb = escpos_to_thermal_bitmap(start_raster)
        save_png(start_tb, f"{key}_start.png")

        # 2. Solved position
        solved_fn = SOLVED_RENDERERS.get(pid)
        if solved_fn:
            solved_tb = solved_fn(plugin, res)
        else:
            solved_tb = start_tb
        save_png(solved_tb, f"{key}_solved.png")

    print("\n[SUCCESS] All 40 puzzle guide images generated successfully!")
    generate_puzzle_guide_markdown()


if __name__ == "__main__":
    generate_all_images()
