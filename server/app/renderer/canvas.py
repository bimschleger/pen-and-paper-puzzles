"""
Morning Puzzles - Thermal Drawing Canvas Engine
Provides unified 1-bit thermal raster primitives and GS v 0 byte packing
conforming strictly to:
  - 80mm thermal hardware standards (576 dots width / 72 bytes per row)
  - docs/THERMAL_80MM_PRINT_GUIDE.md
  - docs/THERMAL_DRAWING_SPEC.md

Renders exclusively through Pure-Python ThermalBitmap 1-bit primitives.
"""

from typing import Tuple, Dict, Any, List, Optional
import base64
import math
import os

THERMAL_WIDTH_DOTS = 576
THERMAL_WIDTH_BYTES = 72  # 576 // 8

FONT_CAPTION_16 = "caption_16"
FONT_BODY_20 = "body_20"
FONT_SUBHEAD_22 = "subhead_22"
FONT_DISPLAY_32 = "display_32"
FONT_GRID_12x14 = "grid_12x14"
FONT_GRID_18x21 = "grid_18x21"

_FONT_CACHE: Optional[Dict[str, Any]] = None


def _load_thermal_fonts() -> Dict[str, Any]:
    """Lazily loads and decodes server/data/thermal_fonts.json into fast lookup structures."""
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE

    from ..puzzles.base import load_curated_dataset

    raw = load_curated_dataset("thermal_fonts.json")
    if not raw:
        _FONT_CACHE = {"grid_map": {}, "fonts": {}}
        return _FONT_CACHE

    grid_chars = raw.get("grid_chars", "")
    grid_map = {ch: idx for idx, ch in enumerate(grid_chars)}
    fonts: Dict[str, Any] = {}
    for f in raw.get("fonts", []):
        bitmap = base64.b64decode(f["bitmap_b64"])
        glyphs = tuple(
            (g["w"], g["h"], g["xOff"], g["yOff"], g["xAdv"], g["bitOffset"])
            for g in f["glyphs"]
        )
        fonts[f["id"]] = {
            "line_height": f["lineHeight"],
            "baseline": f["baseline"],
            "fixed_w": f["fixedW"],
            "fixed_h": f["fixedH"],
            "bitmap": bitmap,
            "glyphs": glyphs,
        }
    _FONT_CACHE = {"grid_map": grid_map, "fonts": fonts}
    return _FONT_CACHE
_BIT_COUNTS = tuple(bin(b).count("1") for b in range(256))
_FULL_ONES = b"\xff" * THERMAL_WIDTH_BYTES
_FULL_ZEROS = b"\x00" * THERMAL_WIDTH_BYTES


def image_to_escpos_raster(image_bytes: bytes, width: int, height: int) -> bytes:
    """
    Wraps 1-bit bitmap bytes into the ESC/POS GS v 0 (raster bit image) command.
    ESC/POS GS v 0 format:
      0x1D 0x76 0x30 0x00 xL xH yL yH [data...]
    """
    width_bytes = (width + 7) // 8
    xl = width_bytes & 0xFF
    xh = (width_bytes >> 8) & 0xFF
    yl = height & 0xFF
    yh = (height >> 8) & 0xFF

    header = bytes([0x1D, 0x76, 0x30, 0x00, xl, xh, yl, yh])
    return header + image_bytes


def calculate_duty_cycle(raster_bytes: bytes) -> Dict[str, Any]:
    """
    Analyzes an ESC/POS GS v 0 byte stream to evaluate thermal printhead stress:
    - Average black pixel density (duty cycle) across the graphic
    - Peak black pixel density across any single horizontal scanline
    - Compliance with the 35% safe thermal duty cycle guideline
    """
    if len(raster_bytes) < 8:
        return {"error": "Invalid raster byte stream (too short)"}

    if raster_bytes[0] != 0x1D or raster_bytes[1] != 0x76 or raster_bytes[2] != 0x30:
        return {"error": "Not a GS v 0 raster command"}

    width_bytes = raster_bytes[4] | (raster_bytes[5] << 8)
    height_dots = raster_bytes[6] | (raster_bytes[7] << 8)
    data = raster_bytes[8:]

    expected_len = width_bytes * height_dots
    if len(data) < expected_len:
        return {"error": f"Truncated data: expected {expected_len} bytes, got {len(data)}"}

    total_bits = width_bytes * 8 * height_dots
    total_black_dots = 0
    max_line_black_dots = 0
    consec_dense = 0
    max_consec_dense = 0
    line_total_dots = width_bytes * 8

    if line_total_dots > 0:
        for y in range(height_dots):
            line_start = y * width_bytes
            line_bytes = data[line_start:line_start + width_bytes]
            line_black = sum(_BIT_COUNTS[b] for b in line_bytes)
            total_black_dots += line_black
            if line_black > max_line_black_dots:
                max_line_black_dots = line_black
            if line_black / float(line_total_dots) > 0.75:
                consec_dense += 1
                if consec_dense > max_consec_dense:
                    max_consec_dense = consec_dense
            else:
                consec_dense = 0

    avg_density = (total_black_dots / float(total_bits)) * 100.0 if total_bits > 0 else 0.0
    peak_line_density = (max_line_black_dots / float(line_total_dots)) * 100.0 if line_total_dots > 0 else 0.0

    return {
        "width_dots": line_total_dots,
        "width_bytes": width_bytes,
        "height_dots": height_dots,
        "total_black_pixels": total_black_dots,
        "total_pixels": total_bits,
        "average_duty_cycle_pct": round(avg_density, 2),
        "peak_scanline_duty_cycle_pct": round(peak_line_density, 2),
        "max_consecutive_dense_lines": max_consec_dense,
        "is_safe": avg_density <= 35.0 and max_consec_dense <= 16
    }


def _hatch_predicate(pat: int, px: int, py: int) -> bool:
    if pat == 1:
        return (px + py) % 8 == 0
    if pat == 2:
        return (px - py + 1000) % 8 == 0
    if pat == 3:
        return (px + py) % 10 == 0 or (px - py + 1000) % 10 == 0
    if pat == 4:
        return px % 8 == 0
    if pat == 5:
        return px % 4 == 0 and py % 4 == 0
    if pat == 6:
        return (px + py) % 8 == 0 and (px % 4 < 2)
    if pat == 7:
        return (px - py + 1000) % 8 == 0 and (px % 4 < 2)
    if pat == 8:
        rx = px % 8
        ry = py % 8
        return (rx == 4 and abs(ry - 4) <= 1) or (ry == 4 and abs(rx - 4) <= 1)
    if pat == 9:
        return (px + py) % 6 == 0 and (px - py + 1000) % 6 == 0
    return False


def _build_hatch_table() -> Dict[int, Tuple[bytes, ...]]:
    periods = {1: 8, 2: 8, 3: 10, 4: 1, 5: 4, 6: 8, 7: 8, 8: 8, 9: 6}
    table: Dict[int, Tuple[bytes, ...]] = {}
    for pat, period in periods.items():
        rows: List[bytes] = []
        for py in range(period):
            row = bytearray(THERMAL_WIDTH_BYTES)
            for px in range(THERMAL_WIDTH_DOTS):
                if _hatch_predicate(pat, px, py):
                    row[px >> 3] |= 1 << (7 - (px & 7))
            rows.append(bytes(row))
        table[pat] = tuple(rows)
    return table


_HATCH_TABLE = _build_hatch_table()


FONT_5X7 = {
    '0': [0x1E, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E],
    '1': [0x08, 0x18, 0x28, 0x08, 0x08, 0x08, 0x3E],
    '2': [0x1E, 0x21, 0x01, 0x0E, 0x18, 0x20, 0x3F],
    '3': [0x1E, 0x21, 0x01, 0x0E, 0x01, 0x21, 0x1E],
    '4': [0x02, 0x06, 0x0A, 0x12, 0x3F, 0x02, 0x02],
    '5': [0x3F, 0x20, 0x3E, 0x01, 0x01, 0x21, 0x1E],
    '6': [0x1E, 0x21, 0x20, 0x3E, 0x21, 0x21, 0x1E],
    '7': [0x3F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10],
    '8': [0x1E, 0x21, 0x21, 0x1E, 0x21, 0x21, 0x1E],
    '9': [0x1E, 0x21, 0x21, 0x1F, 0x01, 0x21, 0x1E],
    'A': [0x0C, 0x12, 0x21, 0x3F, 0x21, 0x21, 0x21],
    'B': [0x3E, 0x21, 0x21, 0x3E, 0x21, 0x21, 0x3E],
    'C': [0x1E, 0x21, 0x20, 0x20, 0x20, 0x21, 0x1E],
    'D': [0x3C, 0x22, 0x21, 0x21, 0x21, 0x22, 0x3C],
    'E': [0x3F, 0x20, 0x20, 0x3E, 0x20, 0x20, 0x3F],
    'F': [0x3F, 0x20, 0x20, 0x3E, 0x20, 0x20, 0x20],
    'G': [0x1E, 0x21, 0x20, 0x27, 0x21, 0x21, 0x1E],
    'H': [0x21, 0x21, 0x21, 0x3F, 0x21, 0x21, 0x21],
    'I': [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F],
    'J': [0x07, 0x02, 0x02, 0x02, 0x22, 0x22, 0x1C],
    'K': [0x21, 0x22, 0x24, 0x38, 0x24, 0x22, 0x21],
    'L': [0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x3F],
    'M': [0x21, 0x33, 0x2D, 0x21, 0x21, 0x21, 0x21],
    'N': [0x21, 0x31, 0x29, 0x25, 0x23, 0x21, 0x21],
    'O': [0x1E, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E],
    'P': [0x3E, 0x21, 0x21, 0x3E, 0x20, 0x20, 0x20],
    'Q': [0x1E, 0x21, 0x21, 0x21, 0x25, 0x22, 0x1D],
    'R': [0x3E, 0x21, 0x21, 0x3E, 0x24, 0x22, 0x21],
    'S': [0x1E, 0x21, 0x20, 0x1E, 0x01, 0x21, 0x1E],
    'T': [0x3F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    'U': [0x21, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E],
    'V': [0x21, 0x21, 0x21, 0x12, 0x12, 0x0C, 0x0C],
    'W': [0x21, 0x21, 0x21, 0x21, 0x2D, 0x33, 0x21],
    'X': [0x21, 0x12, 0x0C, 0x0C, 0x12, 0x21, 0x21],
    'Y': [0x21, 0x12, 0x0C, 0x04, 0x04, 0x04, 0x04],
    'Z': [0x3F, 0x02, 0x04, 0x08, 0x10, 0x20, 0x3F],
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C],
    ':': [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00],
    '-': [0x00, 0x00, 0x00, 0x3E, 0x00, 0x00, 0x00],
    '?': [0x1E, 0x21, 0x02, 0x04, 0x04, 0x00, 0x04],
    '!': [0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04],
    '[': [0x1E, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1E],
    ']': [0x1E, 0x02, 0x02, 0x02, 0x02, 0x02, 0x1E],
    '+': [0x00, 0x08, 0x08, 0x3E, 0x08, 0x08, 0x00],
    '=': [0x00, 0x3E, 0x00, 0x3E, 0x00, 0x00, 0x00],
    '*': [0x00, 0x2A, 0x1C, 0x3E, 0x1C, 0x2A, 0x00],
    '/': [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x00],
    '(': [0x04, 0x08, 0x10, 0x10, 0x10, 0x08, 0x04],
    ')': [0x10, 0x08, 0x04, 0x04, 0x04, 0x08, 0x10],
    '_': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3F],
    ',': [0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08],
    '"': [0x14, 0x14, 0x14, 0x00, 0x00, 0x00, 0x00],
    "'": [0x08, 0x08, 0x10, 0x00, 0x00, 0x00, 0x00],
    '^': [0x0C, 0x12, 0x21, 0x00, 0x00, 0x00, 0x00],
    '|': [0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08],
    '<': [0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02],
    '>': [0x10, 0x08, 0x04, 0x02, 0x04, 0x08, 0x10],
    ';': [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x04, 0x08],
}


class ThermalBitmap:
    """
    Pure Python 1-bit raster canvas for 80mm thermal receipt printers.
    Enforces strict 576-dot width (72 bytes/row), MSB-first packing,
    and 1=burn (black) polarity.
    """
    def __init__(self, width: int = THERMAL_WIDTH_DOTS, height: int = 100):
        self.width = width
        self.height = height
        self.width_bytes = (width + 7) // 8
        self.buffer = bytearray(self.width_bytes * height)

    def set_pixel(self, x: int, y: int, color: int = 1):
        if 0 <= x < self.width and 0 <= y < self.height:
            byte_idx = y * self.width_bytes + (x // 8)
            bit_mask = 1 << (7 - (x % 8))
            if color:
                self.buffer[byte_idx] |= bit_mask
            else:
                self.buffer[byte_idx] &= ~bit_mask

    def _fill_row_span(self, y: int, x0: int, x1: int, color: int):
        first_byte = x0 >> 3
        last_byte = (x1 - 1) >> 3
        start_mask = 0xFF >> (x0 & 7)
        end_mask = (0xFF << (7 - ((x1 - 1) & 7))) & 0xFF
        row_off = y * self.width_bytes
        buf = self.buffer
        if first_byte == last_byte:
            mask = start_mask & end_mask
            if color:
                buf[row_off + first_byte] |= mask
            else:
                buf[row_off + first_byte] &= ~mask
        else:
            mid_count = last_byte - first_byte - 1
            if color:
                buf[row_off + first_byte] |= start_mask
                if mid_count > 0:
                    s = row_off + first_byte + 1
                    fill = _FULL_ONES[:mid_count] if mid_count <= len(_FULL_ONES) else b"\xff" * mid_count
                    buf[s:s + mid_count] = fill
                buf[row_off + last_byte] |= end_mask
            else:
                buf[row_off + first_byte] &= ~start_mask
                if mid_count > 0:
                    s = row_off + first_byte + 1
                    fill = _FULL_ZEROS[:mid_count] if mid_count <= len(_FULL_ZEROS) else b"\x00" * mid_count
                    buf[s:s + mid_count] = fill
                buf[row_off + last_byte] &= ~end_mask

    def draw_hline(self, x: int, y: int, w: int, thickness: int = 1, color: int = 1):
        if thickness <= 0 or w <= 0:
            return
        x0 = max(0, x)
        x1 = min(x + w, self.width)
        y0 = max(0, y)
        y1 = min(y + thickness, self.height)
        if x0 >= x1 or y0 >= y1:
            return

        first_byte = x0 >> 3
        last_byte = (x1 - 1) >> 3
        start_mask = 0xFF >> (x0 & 7)
        end_mask = (0xFF << (7 - ((x1 - 1) & 7))) & 0xFF
        wb = self.width_bytes
        buf = self.buffer

        if first_byte == last_byte:
            mask = start_mask & end_mask
            if color:
                for row_off in range(y0 * wb, y1 * wb, wb):
                    buf[row_off + first_byte] |= mask
            else:
                inv = ~mask & 0xFF
                for row_off in range(y0 * wb, y1 * wb, wb):
                    buf[row_off + first_byte] &= inv
        else:
            mid_count = last_byte - first_byte - 1
            if color:
                fill = _FULL_ONES[:mid_count] if mid_count <= len(_FULL_ONES) else b"\xff" * mid_count
                for row_off in range(y0 * wb, y1 * wb, wb):
                    buf[row_off + first_byte] |= start_mask
                    if mid_count > 0:
                        s = row_off + first_byte + 1
                        buf[s:s + mid_count] = fill
                    buf[row_off + last_byte] |= end_mask
            else:
                inv_start = ~start_mask & 0xFF
                inv_end = ~end_mask & 0xFF
                fill = _FULL_ZEROS[:mid_count] if mid_count <= len(_FULL_ZEROS) else b"\x00" * mid_count
                for row_off in range(y0 * wb, y1 * wb, wb):
                    buf[row_off + first_byte] &= inv_start
                    if mid_count > 0:
                        s = row_off + first_byte + 1
                        buf[s:s + mid_count] = fill
                    buf[row_off + last_byte] &= inv_end

    def draw_vline(self, x: int, y: int, h: int, thickness: int = 1, color: int = 1):
        if thickness <= 0 or h <= 0:
            return
        if thickness > 1:
            self.draw_hline(x, y, thickness, thickness=h, color=color)
            return
        if not (0 <= x < self.width):
            return
        y0 = max(0, y)
        y1 = min(y + h, self.height)
        if y0 >= y1:
            return
        wb = self.width_bytes
        col_byte = x >> 3
        bit_mask = 1 << (7 - (x & 7))
        buf = self.buffer
        start = y0 * wb + col_byte
        stop = y1 * wb + col_byte
        if color:
            for idx in range(start, stop, wb):
                buf[idx] |= bit_mask
        else:
            inv = ~bit_mask & 0xFF
            for idx in range(start, stop, wb):
                buf[idx] &= inv

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, thickness: int = 1, color: int = 1):
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy

        for _ in range(dx - dy + 2):
            if thickness <= 1:
                self.set_pixel(x0, y0, color)
            else:
                half_t = thickness // 2
                for ty in range(-half_t, half_t + (thickness % 2)):
                    for tx in range(-half_t, half_t + (thickness % 2)):
                        self.set_pixel(x0 + tx, y0 + ty, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def draw_dashed_hline(self, x: int, y: int, w: int, dash_len: int = 4, gap_len: int = 4, thickness: int = 1, color: int = 1):
        if w <= 0 or dash_len <= 0 or gap_len < 0:
            return
        cur_x = x
        end_x = x + w
        step = dash_len + gap_len
        while cur_x < end_x:
            seg_w = min(dash_len, end_x - cur_x)
            self.draw_hline(cur_x, y, seg_w, thickness=thickness, color=color)
            cur_x += step

    def draw_dashed_vline(self, x: int, y: int, h: int, dash_len: int = 4, gap_len: int = 4, thickness: int = 1, color: int = 1):
        if h <= 0 or dash_len <= 0 or gap_len < 0:
            return
        cur_y = y
        end_y = y + h
        step = dash_len + gap_len
        while cur_y < end_y:
            seg_h = min(dash_len, end_y - cur_y)
            self.draw_vline(x, cur_y, seg_h, thickness=thickness, color=color)
            cur_y += step

    def draw_grid(
        self,
        x: int,
        y: int,
        cols: int,
        rows: int,
        cell_w: int,
        cell_h: int,
        outer_thick: int = 4,
        inner_thick: int = 1,
    ):
        if cols <= 0 or rows <= 0 or cell_w <= 0 or cell_h <= 0:
            return
        w = cols * cell_w
        h = rows * cell_h
        self.draw_rect(x, y, w, h, thickness=outer_thick, color=1)
        for r in range(1, rows):
            self.draw_hline(x, y + r * cell_h, w, thickness=inner_thick, color=1)
        for c in range(1, cols):
            self.draw_vline(x + c * cell_w, y, h, thickness=inner_thick, color=1)

    def draw_polygon(self, points: List[Tuple[int, int]], thickness: int = 1, color: int = 1):
        if len(points) < 2:
            return
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i + 1) % len(points)]
            self.draw_line(int(round(p1[0])), int(round(p1[1])), int(round(p2[0])), int(round(p2[1])), thickness=thickness, color=color)

    def draw_rect(self, x: int, y: int, w: int, h: int, thickness: int = 1, color: int = 1):
        self.draw_hline(x, y, w, thickness, color)
        self.draw_hline(x, y + h - thickness, w, thickness, color)
        self.draw_vline(x, y, h, thickness, color)
        self.draw_vline(x + w - thickness, y, h, thickness, color)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: int = 1):
        self.draw_hline(x, y, w, thickness=h, color=color)

    def fill_hatch(self, x: int, y: int, w: int, h: int, pattern_id: int):
        pat = pattern_id % 10
        if pat == 0 or w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        x1 = min(x + w, self.width)
        y0 = max(0, y)
        y1 = min(y + h, self.height)
        if x0 >= x1 or y0 >= y1:
            return

        if x1 <= THERMAL_WIDTH_DOTS:
            rows = _HATCH_TABLE[pat]
            period = len(rows)
            first_byte = x0 >> 3
            last_byte = (x1 - 1) >> 3
            start_mask = 0xFF >> (x0 & 7)
            end_mask = (0xFF << (7 - ((x1 - 1) & 7))) & 0xFF
            wb = self.width_bytes
            buf = self.buffer
            if first_byte == last_byte:
                mask = start_mask & end_mask
                for py in range(y0, y1):
                    buf[py * wb + first_byte] |= rows[py % period][first_byte] & mask
            else:
                for py in range(y0, y1):
                    pat_row = rows[py % period]
                    row_off = py * wb
                    buf[row_off + first_byte] |= pat_row[first_byte] & start_mask
                    for b in range(first_byte + 1, last_byte):
                        buf[row_off + b] |= pat_row[b]
                    buf[row_off + last_byte] |= pat_row[last_byte] & end_mask
            return

        for py in range(y0, y1):
            for px in range(x0, x1):
                if _hatch_predicate(pat, px, py):
                    self.set_pixel(px, py, 1)

    def _blit_glyph(self, x: int, y: int, w: int, h: int, bitmap: bytes, bit_offset: int, color: int):
        if w <= 0 or h <= 0:
            return
        if y + h <= 0 or y >= self.height or x + w <= 0 or x >= self.width:
            return
        bit_idx = 0
        for dy in range(h):
            py = y + dy
            in_y = 0 <= py < self.height
            for dx in range(w):
                if in_y:
                    byte_val = bitmap[bit_offset + (bit_idx >> 3)]
                    if (byte_val >> (7 - (bit_idx & 7))) & 1:
                        self.set_pixel(x + dx, py, color)
                bit_idx += 1

    def draw_char(self, x: int, y: int, char: str, scale: int = 2, color: int = 1):
        if scale <= 0:
            return
        if scale in (2, 3):
            fcache = _load_thermal_fonts()
            fid = FONT_GRID_12x14 if scale == 2 else FONT_GRID_18x21
            fdef = fcache["fonts"].get(fid)
            if fdef is not None:
                uc = char.upper() if char else " "
                g_idx = fcache["grid_map"].get(uc)
                if g_idx is not None and g_idx < len(fdef["glyphs"]):
                    w, h, xo, yo, _xa, boff = fdef["glyphs"][g_idx]
                    self._blit_glyph(x + xo, y + yo, w, h, fdef["bitmap"], boff, color)
                return
        glyph = FONT_5X7.get(char.upper(), FONT_5X7.get(' ', [0]*7))
        for row_idx, row_byte in enumerate(glyph):
            if row_byte == 0:
                continue
            py = y + row_idx * scale
            if py + scale <= 0 or py >= self.height:
                continue
            for col_idx in range(6):
                if (row_byte >> (5 - col_idx)) & 1:
                    px = x + col_idx * scale
                    if scale == 1:
                        self.set_pixel(px, py, color)
                    else:
                        self.draw_hline(px, py, scale, thickness=scale, color=color)

    def get_font_line_height(self, font_id: str) -> int:
        fdef = _load_thermal_fonts()["fonts"].get(font_id)
        return fdef["line_height"] if fdef else 0

    def _get_prop_glyph(self, fdef: Dict[str, Any], ch: str):
        code = ord(ch)
        idx = (code - 32) if 32 <= code < 127 else 0
        glyphs = fdef["glyphs"]
        if idx >= len(glyphs):
            idx = 0
        return glyphs[idx]

    def measure_text_font(self, text: str, font_id: str) -> int:
        if not text:
            return 0
        fdef = _load_thermal_fonts()["fonts"].get(font_id)
        if not fdef:
            return 0
        glyphs = fdef["glyphs"]
        n = len(glyphs)
        total = 0
        for ch in text:
            code = ord(ch)
            idx = (code - 32) if 32 <= code < 127 else 0
            if idx >= n:
                idx = 0
            total += glyphs[idx][4]
        return total

    def draw_text_font(self, x: int, y: int, text: str, font_id: str, color: int = 1):
        if not text:
            return
        fdef = _load_thermal_fonts()["fonts"].get(font_id)
        if not fdef:
            return
        bitmap = fdef["bitmap"]
        cur_x = x
        for ch in text:
            w, h, xo, yo, xa, boff = self._get_prop_glyph(fdef, ch)
            if w > 0 and h > 0:
                self._blit_glyph(cur_x + xo, y + yo, w, h, bitmap, boff, color)
            cur_x += xa

    def draw_centered_text_font(self, y: int, text: str, font_id: str, color: int = 1):
        if not text:
            return
        w = self.measure_text_font(text, font_id)
        self.draw_text_font((self.width - w) // 2, y, text, font_id, color=color)

    def draw_right_text_font(self, right_x: int, y: int, text: str, font_id: str, color: int = 1):
        if not text:
            return
        w = self.measure_text_font(text, font_id)
        self.draw_text_font(right_x - w, y, text, font_id, color=color)

    def _wrap_lines_font(self, text: str, max_width: int, fdef: Dict[str, Any]) -> List[Tuple[str, int]]:
        words = [w for w in text.split(" ") if w]
        if not words:
            return []
        space_adv = self._get_prop_glyph(fdef, " ")[4]
        glyphs = fdef["glyphs"]
        n = len(glyphs)

        def word_w(word: str) -> int:
            tot = 0
            for ch in word:
                c = ord(ch)
                idx = (c - 32) if 32 <= c < 127 else 0
                if idx >= n:
                    idx = 0
                tot += glyphs[idx][4]
            return tot

        lines: List[Tuple[str, int]] = []
        cur_words: List[str] = []
        cur_w = 0
        for wd in words:
            ww = word_w(wd)
            if not cur_words:
                cur_words.append(wd)
                cur_w = ww
            elif cur_w + space_adv + ww <= max_width:
                cur_words.append(wd)
                cur_w += space_adv + ww
            else:
                lines.append((" ".join(cur_words), cur_w))
                cur_words = [wd]
                cur_w = ww
        if cur_words:
            lines.append((" ".join(cur_words), cur_w))
        return lines

    def measure_wrapped_height_font(self, text: str, max_width: int, font_id: str, line_gap: int = 4) -> int:
        if not text:
            return 0
        fdef = _load_thermal_fonts()["fonts"].get(font_id)
        if not fdef:
            return 0
        lines = self._wrap_lines_font(text, max_width, fdef)
        if not lines:
            return 0
        lh = fdef["line_height"]
        return len(lines) * lh + (len(lines) - 1) * line_gap

    def draw_wrapped_text_font(
        self,
        x: int,
        y: int,
        max_width: int,
        text: str,
        font_id: str,
        align: str = "left",
        line_gap: int = 4,
        color: int = 1,
    ) -> int:
        if not text:
            return 0
        fdef = _load_thermal_fonts()["fonts"].get(font_id)
        if not fdef:
            return 0
        lines = self._wrap_lines_font(text, max_width, fdef)
        if not lines:
            return 0
        lh = fdef["line_height"]
        cur_y = y
        for line_str, line_w in lines:
            if align == "center":
                lx = x + (max_width - line_w) // 2
            elif align == "right":
                lx = x + max_width - line_w
            else:
                lx = x
            self.draw_text_font(lx, cur_y, line_str, font_id, color=color)
            cur_y += lh + line_gap
        return len(lines) * lh + (len(lines) - 1) * line_gap

    def draw_text(self, x: int, y: int, text: str, scale: int = 2, color: int = 1):
        cur_x = x
        char_w = 6 * scale + max(1, scale // 2)
        for ch in text:
            self.draw_char(cur_x, y, ch, scale=scale, color=color)
            cur_x += char_w

    def get_text_width(self, text: str, scale: int = 2) -> int:
        if not text or scale == 0:
            return 0
        char_w = 6 * scale + max(1, scale // 2)
        return len(text) * char_w

    def draw_centered_text(self, y: int, text: str, scale: int = 2, color: int = 1):
        w = self.get_text_width(text, scale=scale)
        x = (self.width - w) // 2
        self.draw_text(x, y, text, scale=scale, color=color)

    def draw_circle(self, cx: int, cy: int, radius: int, thickness: int = 2, color: int = 1):
        if radius <= 0:
            return
        r_inner_sq = max(0, radius - thickness) ** 2
        r_outer_sq = radius ** 2
        y0 = max(0, cy - radius)
        y1 = min(cy + radius + 1, self.height)
        for py in range(y0, y1):
            dy_sq = (py - cy) ** 2
            outer_dx = math.isqrt(r_outer_sq - dy_sq)
            if dy_sq >= r_inner_sq:
                lx = max(0, cx - outer_dx)
                rx = min(self.width, cx + outer_dx + 1)
                if lx < rx:
                    self._fill_row_span(py, lx, rx, color)
            else:
                k = math.isqrt(r_inner_sq - dy_sq - 1) + 1
                if k <= outer_dx:
                    lx0 = max(0, cx - outer_dx)
                    rx0 = min(self.width, cx - k + 1)
                    if lx0 < rx0:
                        self._fill_row_span(py, lx0, rx0, color)
                    lx1 = max(0, cx + k)
                    rx1 = min(self.width, cx + outer_dx + 1)
                    if lx1 < rx1:
                        self._fill_row_span(py, lx1, rx1, color)

    def fill_circle(self, cx: int, cy: int, radius: int, color: int = 1):
        if radius <= 0:
            return
        r_sq = radius * radius
        y0 = max(0, cy - radius)
        y1 = min(cy + radius + 1, self.height)
        for py in range(y0, y1):
            dy_sq = (py - cy) ** 2
            dx = math.isqrt(r_sq - dy_sq)
            x0 = max(0, cx - dx)
            x1 = min(self.width, cx + dx + 1)
            if x0 < x1:
                self._fill_row_span(py, x0, x1, color)

    def to_escpos(self) -> bytes:
        return image_to_escpos_raster(bytes(self.buffer), self.width, self.height)


def render_master_header_raster(
    title: str,
    subtitle: Optional[str] = "Enjoy Your Puzzles",
    mix_subtitle: Optional[str] = None,
) -> bytes:
    ref = ThermalBitmap(THERMAL_WIDTH_DOTS, 8)
    cur_y = 20 + ref.get_font_line_height(FONT_DISPLAY_32) + 4
    if subtitle:
        cur_y += ref.get_font_line_height(FONT_BODY_20) + 6
    cur_y += 13
    if mix_subtitle:
        cur_y += ref.get_font_line_height(FONT_CAPTION_16) + 8
    total_h = (cur_y + 7) & ~7

    bmp = ThermalBitmap(THERMAL_WIDTH_DOTS, total_h)
    bmp.draw_hline(20, 4, 536, thickness=2, color=1)
    bmp.draw_hline(20, 8, 536, thickness=1, color=1)
    cy = 20
    if title:
        bmp.draw_centered_text_font(cy, title, FONT_DISPLAY_32, color=1)
    cy += bmp.get_font_line_height(FONT_DISPLAY_32) + 4
    if subtitle:
        bmp.draw_centered_text_font(cy, subtitle, FONT_BODY_20, color=1)
        cy += bmp.get_font_line_height(FONT_BODY_20) + 6
    bmp.draw_hline(20, cy, 536, thickness=1, color=1)
    bmp.draw_hline(20, cy + 3, 536, thickness=2, color=1)
    cy += 13
    if mix_subtitle:
        bmp.draw_centered_text_font(cy, mix_subtitle, FONT_CAPTION_16, color=1)
    return bmp.to_escpos()


def render_puzzle_header_raster(
    title: str,
    difficulty: Optional[str] = None,
    instruction: str = "",
) -> bytes:
    ref = ThermalBitmap(THERMAL_WIDTH_DOTS, 8)
    cur_y = 36
    if difficulty:
        cur_y += ref.get_font_line_height(FONT_CAPTION_16) + 4
    if instruction:
        cur_y += 2 + ref.measure_wrapped_height_font(instruction, 536, FONT_BODY_20, line_gap=4) + 10
    total_h = (cur_y + 7) & ~7

    bmp = ThermalBitmap(THERMAL_WIDTH_DOTS, total_h)
    if title:
        tw = bmp.measure_text_font(title, FONT_SUBHEAD_22)
        tx = (THERMAL_WIDTH_DOTS - tw) // 2
        rule_y = 4 + bmp.get_font_line_height(FONT_SUBHEAD_22) // 2
        if tx - 14 > 20:
            bmp.draw_hline(20, rule_y, tx - 14 - 20, thickness=1, color=1)
        if tx + tw + 14 < 556:
            bmp.draw_hline(tx + tw + 14, rule_y, 556 - (tx + tw + 14), thickness=1, color=1)
        bmp.draw_text_font(tx, 4, title, FONT_SUBHEAD_22, color=1)
    cy = 36
    if difficulty:
        bmp.draw_centered_text_font(cy, f"DIFFICULTY: {difficulty}", FONT_CAPTION_16, color=1)
        cy += bmp.get_font_line_height(FONT_CAPTION_16) + 4
    if instruction:
        cy += 2
        bmp.draw_wrapped_text_font(20, cy, 536, instruction, FONT_BODY_20, align="center", line_gap=4, color=1)
    return bmp.to_escpos()


def render_divider_raster() -> bytes:
    bmp = ThermalBitmap(THERMAL_WIDTH_DOTS, 24)
    bmp.draw_hline(20, 11, 536, thickness=1, color=1)
    return bmp.to_escpos()


def render_master_footer_raster(
    closing_tagline: Optional[str] = "Enjoy your day!",
    include_schedule_hint: bool = False,
    leading_rule: bool = True,
) -> bytes:
    ref = ThermalBitmap(THERMAL_WIDTH_DOTS, 8)
    line1 = "For more puzzles, toggle the power on the front of the printer."
    line2 = "To change settings, toggle the power on the cable behind the printer."
    cur_y = 4
    if leading_rule:
        cur_y += 18
    if closing_tagline:
        cur_y += ref.get_font_line_height(FONT_SUBHEAD_22) + 8
    cur_y += ref.measure_wrapped_height_font(line1, 536, FONT_BODY_20, line_gap=4) + 10
    cur_y += ref.measure_wrapped_height_font(line2, 536, FONT_BODY_20, line_gap=4) + 10
    if include_schedule_hint:
        cur_y += ref.get_font_line_height(FONT_BODY_20) + 6
    cur_y += 12
    total_h = (cur_y + 7) & ~7

    bmp = ThermalBitmap(THERMAL_WIDTH_DOTS, total_h)
    cy = 4
    if leading_rule:
        bmp.draw_hline(20, cy + 6, 536, thickness=1, color=1)
        cy += 18
    if closing_tagline:
        bmp.draw_centered_text_font(cy, closing_tagline, FONT_SUBHEAD_22, color=1)
        cy += bmp.get_font_line_height(FONT_SUBHEAD_22) + 8
    cy += bmp.draw_wrapped_text_font(20, cy, 536, line1, FONT_BODY_20, align="center", line_gap=4, color=1) + 10
    cy += bmp.draw_wrapped_text_font(20, cy, 536, line2, FONT_BODY_20, align="center", line_gap=4, color=1) + 10
    if include_schedule_hint:
        bmp.draw_centered_text_font(cy, "To schedule daily puzzles, go to settings.", FONT_BODY_20, color=1)
        cy += bmp.get_font_line_height(FONT_BODY_20) + 6
    bmp.draw_hline(20, cy + 2, 536, thickness=1, color=1)
    return bmp.to_escpos()
