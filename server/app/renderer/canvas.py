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
import math
import os

THERMAL_WIDTH_DOTS = 576
THERMAL_WIDTH_BYTES = 72  # 576 // 8
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

    def draw_char(self, x: int, y: int, char: str, scale: int = 2, color: int = 1):
        if scale <= 0:
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
