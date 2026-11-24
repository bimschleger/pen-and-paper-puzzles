#!/usr/bin/env python3
"""
Pen and Paper Puzzles - Build-Time 1-Bit Thermal Font Compiler
Bakes Helvetica Neue at native 203 DPI (1px = 1 thermal dot) via macOS CoreText
into canonical JSON (server/data/thermal_fonts.json).

Generates:
  - Proportional receipt fonts (ASCII 0x20..0x7E):
      0: caption_16  (HelveticaNeue-Medium 20pt)
      1: body_20     (HelveticaNeue 24pt)
      2: subhead_22  (HelveticaNeue-Bold 28pt)
      3: display_32  (HelveticaNeue-Bold 36pt)
  - Fixed-cell in-board puzzle glyph tables (59 GLYPH_TABLE chars):
      4: grid_12x14  (Drop-in native 1-bit replacement for 5x7 scale=2; 19pt in 16x16)
      5: grid_18x21  (Drop-in native 1-bit replacement for 5x7 scale=3; 28pt in 20x22)
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import zlib
import struct
from pathlib import Path
from typing import Dict, List, Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
OUT_JSON = ROOT_DIR / "server" / "data" / "thermal_fonts.json"

GRID_CHARS = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    " .:-+=*/()?![]_,\"'^|<>;@"
)[:-1]  # Exact 59 chars from ThermalCanvas GLYPH_TABLE

SWIFT_RASTERIZER = r'''
import CoreText
import CoreGraphics
import Foundation

struct FontSpec: Codable {
    let id: String
    let psName: String
    let ptSize: Double
    let threshold: Int
    let fixedW: Int
    let fixedH: Int
    let chars: String
}

struct GlyphOut: Codable {
    let code: Int
    let w: Int
    let h: Int
    let xOff: Int
    let yOff: Int
    let xAdv: Int
    let rowsHex: String
}

struct FontOut: Codable {
    let id: String
    let lineHeight: Int
    let baseline: Int
    let fixedW: Int
    let fixedH: Int
    let glyphs: [GlyphOut]
}

func renderProportional(spec: FontSpec) -> FontOut {
    let ctFont = CTFontCreateWithName(spec.psName as CFString, CGFloat(spec.ptSize), nil)
    let ascent = Int(ceil(CTFontGetAscent(ctFont)))
    let descent = Int(ceil(CTFontGetDescent(ctFont)))
    let lineHeight = ascent + descent + 2
    let baseline = ascent + 1

    let canvasW = Int(ceil(spec.ptSize * 2.0)) + 16
    let canvasH = lineHeight + 12
    let cs = CGColorSpaceCreateDeviceGray()
    var pixels = [UInt8](repeating: 0, count: canvasW * canvasH)

    var glyphs: [GlyphOut] = []
    for scalar in spec.chars.unicodeScalars {
        let ch = Character(scalar)
        let str = String(ch)
        var unichar = UniChar(scalar.value)
        var cgGlyph: CGGlyph = 0
        CTFontGetGlyphsForCharacters(ctFont, &unichar, &cgGlyph, 1)
        var adv = CGSize.zero
        CTFontGetAdvancesForGlyphs(ctFont, .horizontal, &cgGlyph, &adv, 1)
        let xAdv = max(1, Int(round(adv.width)))

        pixels.withUnsafeMutableBytes { ptr in
            memset(ptr.baseAddress!, 0, canvasW * canvasH)
        }
        guard let ctx = CGContext(
            data: &pixels,
            width: canvasW,
            height: canvasH,
            bitsPerComponent: 8,
            bytesPerRow: canvasW,
            space: cs,
            bitmapInfo: CGImageAlphaInfo.none.rawValue
        ) else { fatalError("CGContext failed") }

        ctx.setShouldAntialias(true)
        ctx.setAllowsAntialiasing(true)
        ctx.setShouldSmoothFonts(false)
        ctx.setFillColor(gray: 1.0, alpha: 1.0)

        let drawBaseY = CGFloat(canvasH - baseline - 4)
        let originX: CGFloat = 6.0
        var pos = CGPoint(x: originX, y: drawBaseY)
        CTFontDrawGlyphs(ctFont, &cgGlyph, &pos, 1, ctx)

        // Find tight bounding box above threshold
        var minX = canvasW, maxX = -1, minY = canvasH, maxY = -1
        for py in 0..<canvasH {
            for px in 0..<canvasW {
                if Int(pixels[py * canvasW + px]) >= spec.threshold {
                    if px < minX { minX = px }
                    if px > maxX { maxX = px }
                    if py < minY { minY = py }
                    if py > maxY { maxY = py }
                }
            }
        }

        if maxX < minX || maxY < minY {
            glyphs.append(GlyphOut(code: Int(scalar.value), w: 0, h: 0, xOff: 0, yOff: 0, xAdv: xAdv, rowsHex: ""))
            continue
        }

        let w = maxX - minX + 1
        let h = maxY - minY + 1
        let xOff = minX - Int(originX)
        let yOff = minY - 4  // relative to top of lineHeight box (baseline = ascent + 1)

        var bitBytes: [UInt8] = []
        var curByte: UInt8 = 0
        var bitCount = 0
        for py in minY...maxY {
            for px in minX...maxX {
                let bit: UInt8 = (Int(pixels[py * canvasW + px]) >= spec.threshold) ? 1 : 0
                curByte = (curByte << 1) | bit
                bitCount += 1
                if bitCount == 8 {
                    bitBytes.append(curByte)
                    curByte = 0
                    bitCount = 0
                }
            }
        }
        if bitCount > 0 {
            curByte <<= (8 - bitCount)
            bitBytes.append(curByte)
        }
        let hex = bitBytes.map { String(format: "%02x", $0) }.joined()
        glyphs.append(GlyphOut(code: Int(scalar.value), w: w, h: h, xOff: xOff, yOff: yOff, xAdv: xAdv, rowsHex: hex))
    }

    return FontOut(id: spec.id, lineHeight: lineHeight, baseline: baseline, fixedW: 0, fixedH: 0, glyphs: glyphs)
}

func renderFixedGrid(spec: FontSpec) -> FontOut {
    let ctFont = CTFontCreateWithName(spec.psName as CFString, CGFloat(spec.ptSize), nil)
    let boxW = spec.fixedW
    let boxH = spec.fixedH
    let canvasW = boxW + 16
    let canvasH = boxH + 16
    let cs = CGColorSpaceCreateDeviceGray()
    var pixels = [UInt8](repeating: 0, count: canvasW * canvasH)

    // Compute cap-height center baseline for clean vertical centering in cell
    let capH = CTFontGetCapHeight(ctFont)
    let baselineFromTop = Int(round((Double(boxH) + Double(capH)) / 2.0))

    var glyphs: [GlyphOut] = []
    for scalar in spec.chars.unicodeScalars {
        var unichar = UniChar(scalar.value)
        var cgGlyph: CGGlyph = 0
        CTFontGetGlyphsForCharacters(ctFont, &unichar, &cgGlyph, 1)
        var adv = CGSize.zero
        CTFontGetAdvancesForGlyphs(ctFont, .horizontal, &cgGlyph, &adv, 1)

        pixels.withUnsafeMutableBytes { ptr in
            memset(ptr.baseAddress!, 0, canvasW * canvasH)
        }
        guard let ctx = CGContext(
            data: &pixels,
            width: canvasW,
            height: canvasH,
            bitsPerComponent: 8,
            bytesPerRow: canvasW,
            space: cs,
            bitmapInfo: CGImageAlphaInfo.none.rawValue
        ) else { fatalError("CGContext failed") }

        ctx.setShouldAntialias(true)
        ctx.setAllowsAntialiasing(true)
        ctx.setShouldSmoothFonts(false)
        ctx.setFillColor(gray: 1.0, alpha: 1.0)

        // Draw at padded origin, then measure tight ink bbox and center inside boxW x boxH
        let pad = 8
        let drawBaseY = CGFloat(canvasH - pad - baselineFromTop)
        var pos = CGPoint(x: CGFloat(pad), y: drawBaseY)
        CTFontDrawGlyphs(ctFont, &cgGlyph, &pos, 1, ctx)

        var minX = canvasW, maxX = -1, minY = canvasH, maxY = -1
        for py in 0..<canvasH {
            for px in 0..<canvasW {
                if Int(pixels[py * canvasW + px]) >= spec.threshold {
                    if px < minX { minX = px }
                    if px > maxX { maxX = px }
                    if py < minY { minY = py }
                    if py > maxY { maxY = py }
                }
            }
        }

        if maxX < minX || maxY < minY {
            glyphs.append(GlyphOut(code: Int(scalar.value), w: 0, h: 0, xOff: 0, yOff: 0, xAdv: boxW, rowsHex: ""))
            continue
        }

        // Crop if slightly wider than boxW (e.g. 'W' or 'M')
        let rawW = maxX - minX + 1
        let rawH = maxY - minY + 1
        let w = min(boxW, rawW)
        let h = min(boxH, rawH)
        let srcX0 = minX + (rawW - w) / 2
        let srcY0 = minY + (rawH - h) / 2

        // Center horizontally in boxW; preserve baseline vertically for punctuation, center caps/digits
        let xOff = (boxW - w) / 2
        let ch = Character(scalar)
        let isPunctCenter = (ch == "-" || ch == "+" || ch == "=" || ch == "*" || ch == "<" || ch == ">")
        let yOff: Int
        if isPunctCenter {
            yOff = (boxH - h) / 2
        } else {
            yOff = max(0, min(boxH - h, srcY0 - pad))
        }

        var bitBytes: [UInt8] = []
        var curByte: UInt8 = 0
        var bitCount = 0
        for dy in 0..<h {
            for dx in 0..<w {
                let bit: UInt8 = (Int(pixels[(srcY0 + dy) * canvasW + (srcX0 + dx)]) >= spec.threshold) ? 1 : 0
                curByte = (curByte << 1) | bit
                bitCount += 1
                if bitCount == 8 {
                    bitBytes.append(curByte)
                    curByte = 0
                    bitCount = 0
                }
            }
        }
        if bitCount > 0 {
            curByte <<= (8 - bitCount)
            bitBytes.append(curByte)
        }
        let hex = bitBytes.map { String(format: "%02x", $0) }.joined()
        glyphs.append(GlyphOut(code: Int(scalar.value), w: w, h: h, xOff: xOff, yOff: yOff, xAdv: boxW, rowsHex: hex))
    }

    return FontOut(id: spec.id, lineHeight: boxH, baseline: baselineFromTop, fixedW: boxW, fixedH: boxH, glyphs: glyphs)
}

let args = CommandLine.arguments
let inputData = try Data(contentsOf: URL(fileURLWithPath: args[1]))
let specs = try JSONDecoder().decode([FontSpec].self, from: inputData)
var results: [FontOut] = []
for s in specs {
    if s.fixedW > 0 {
        results.append(renderFixedGrid(spec: s))
    } else {
        results.append(renderProportional(spec: s))
    }
}
let outData = try JSONEncoder().encode(results)
try outData.write(to: URL(fileURLWithPath: args[2]))
'''


def _write_png(path: Path, width: int, height: int, buf: bytearray) -> None:
    """Write a 1-bit (0=white, 1=black) PNG using stdlib zlib."""
    rows = bytearray()
    wb = (width + 7) // 8
    for y in range(height):
        rows.append(0)
        row_start = y * wb
        for b in range(wb):
            rows.append(buf[row_start + b] ^ 0xFF)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    idat = zlib.compress(bytes(rows), 9)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _render_preview_png(fonts_data: Dict[str, Any], preview_path: Path) -> None:
    """Render a 1:1 576px-wide preview PNG of all baked fonts."""
    W = 576
    H = 380
    wb = W // 8
    buf = bytearray(wb * H)

    def set_px(x: int, y: int) -> None:
        if 0 <= x < W and 0 <= y < H:
            buf[y * wb + (x >> 3)] |= 1 << (7 - (x & 7))

    def draw_str(font: Dict[str, Any], x: int, y: int, text: str) -> None:
        raw = base64.b64decode(font["bitmap_b64"])
        gmap = {g["code"]: g for g in font["glyphs"]}
        cur_x = x
        for ch in text:
            g = gmap.get(ord(ch))
            if not g:
                continue
            w, h, xo, yo, xa, boff = g["w"], g["h"], g["xOff"], g["yOff"], g["xAdv"], g["bitOffset"]
            if w > 0 and h > 0:
                for dy in range(h):
                    for dx in range(w):
                        bit_idx = dy * w + dx
                        byte_val = raw[boff + (bit_idx >> 3)]
                        if (byte_val >> (7 - (bit_idx & 7))) & 1:
                            set_px(cur_x + xo + dx, y + yo + dy)
            cur_x += xa

    f_map = {f["id"]: f for f in fonts_data["fonts"]}
    draw_str(f_map["display_32"], 20, 14, "PEN + PAPER PUZZLES")
    draw_str(f_map["subhead_22"], 20, 56, "SUDOKU   STARS   NONOGRAM   KILLER")
    draw_str(f_map["caption_16"], 20, 90, "DIFFICULTY: MEDIUM   |   TOTAL MINES: 12")
    draw_str(f_map["body_20"], 20, 118, "Fill every row, column, and 3x3 box with digits 1-9")
    draw_str(f_map["body_20"], 20, 144, "without repeating. Enjoy your day!")
    draw_str(f_map["grid_12x14"], 20, 190, "1 2 3 4 5 6 7 8 9 0  A B C D E F = X ?")
    draw_str(f_map["grid_18x21"], 20, 222, "1 2 3 4 5 6 7 8 9 0  A B C D E")
    draw_str(f_map["grid_18x21"], 20, 254, "F G H I J K L M N O P Q R S T")
    draw_str(f_map["body_20"], 20, 296, "For more puzzles, toggle the power on the front.")
    _write_png(preview_path, W, H, buf)


def build_fonts(preview_path: Path = None) -> None:
    ascii_chars = "".join(chr(c) for c in range(32, 127))
    specs = [
        {
            "id": "caption_16",
            "psName": "HelveticaNeue-Medium",
            "ptSize": 20.0,
            "threshold": 112,
            "fixedW": 0,
            "fixedH": 0,
            "chars": ascii_chars,
        },
        {
            "id": "body_20",
            "psName": "HelveticaNeue",
            "ptSize": 24.0,
            "threshold": 112,
            "fixedW": 0,
            "fixedH": 0,
            "chars": ascii_chars,
        },
        {
            "id": "subhead_22",
            "psName": "HelveticaNeue-Bold",
            "ptSize": 28.0,
            "threshold": 124,
            "fixedW": 0,
            "fixedH": 0,
            "chars": ascii_chars,
        },
        {
            "id": "display_32",
            "psName": "HelveticaNeue-Bold",
            "ptSize": 36.0,
            "threshold": 128,
            "fixedW": 0,
            "fixedH": 0,
            "chars": ascii_chars,
        },
        {
            "id": "grid_12x14",
            "psName": "HelveticaNeue-Bold",
            "ptSize": 19.0,
            "threshold": 116,
            "fixedW": 16,
            "fixedH": 16,
            "chars": GRID_CHARS,
        },
        {
            "id": "grid_18x21",
            "psName": "HelveticaNeue-Bold",
            "ptSize": 28.0,
            "threshold": 124,
            "fixedW": 20,
            "fixedH": 22,
            "chars": GRID_CHARS,
        },
    ]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        swift_file = td_path / "bake.swift"
        spec_file = td_path / "specs.json"
        raw_out_file = td_path / "raw_fonts.json"
        mod_cache = td_path / "swift_mod_cache"
        mod_cache.mkdir()

        swift_file.write_text(SWIFT_RASTERIZER, encoding="utf-8")
        spec_file.write_text(json.dumps(specs), encoding="utf-8")

        res = subprocess.run(
            ["swift", "-module-cache-path", str(mod_cache), str(swift_file), str(spec_file), str(raw_out_file)],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Swift CoreText rasterizer failed:\n{res.stderr}\n{res.stdout}")

        raw_fonts = json.loads(raw_out_file.read_text(encoding="utf-8"))

    # Pack per-font bitstreams & verify 7-bit ASCII
    fonts_out: List[Dict[str, Any]] = []
    total_bitmap_bytes = 0
    total_glyphs = 0

    for rf in raw_fonts:
        bitmap_buf = bytearray()
        glyphs_out = []
        for g in rf["glyphs"]:
            code = int(g["code"])
            if code < 32 or code >= 127:
                raise ValueError(f"Non-7-bit-ASCII code {code} in font {rf['id']}")
            g_bytes = bytes.fromhex(g["rowsHex"]) if g["rowsHex"] else b""
            bit_offset = len(bitmap_buf)
            bitmap_buf.extend(g_bytes)
            glyphs_out.append({
                "code": code,
                "w": g["w"],
                "h": g["h"],
                "xOff": g["xOff"],
                "yOff": g["yOff"],
                "xAdv": g["xAdv"],
                "bitOffset": bit_offset,
            })

        total_bitmap_bytes += len(bitmap_buf)
        total_glyphs += len(glyphs_out)
        fonts_out.append({
            "id": rf["id"],
            "lineHeight": rf["lineHeight"],
            "baseline": rf["baseline"],
            "fixedW": rf["fixedW"],
            "fixedH": rf["fixedH"],
            "bitmap_bytes": len(bitmap_buf),
            "bitmap_b64": base64.b64encode(bytes(bitmap_buf)).decode("ascii"),
            "glyphs": glyphs_out,
        })
        print(f"  Baked {rf['id']:12}: {len(glyphs_out):2d} glyphs, lineH={rf['lineHeight']:2d}, bitmap={len(bitmap_buf):5d} B")

    payload = {
        "version": 1,
        "source": "Helvetica Neue (CoreText 1-bit 203 DPI)",
        "grid_chars": GRID_CHARS,
        "fonts": fonts_out,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    desc_bytes = total_glyphs * 6
    print(f"Wrote {OUT_JSON} ({OUT_JSON.stat().st_size:,} B JSON | C++ binary est: {total_bitmap_bytes + desc_bytes:,} B)")

    if preview_path is not None:
        _render_preview_png(payload, preview_path)
        print(f"Wrote preview PNG to {preview_path}")


if __name__ == "__main__":
    preview = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    build_fonts(preview)
