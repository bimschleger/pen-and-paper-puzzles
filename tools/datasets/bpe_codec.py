#!/usr/bin/env python3
"""
Shared 160-token Byte-Pair Encoding (BPE) codec for 7-bit printable ASCII
firmware datasets (Rule 22: 32 <= ord(ch) < 127).

Unused byte values 1..31 (31) and 127..255 (129) = 160 token slots.
Byte 0 is reserved as NUL string terminator; offset 0xFFFF represents nullptr.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

TOK_BYTES: List[int] = list(range(1, 32)) + list(range(127, 256))
MAX_BPE_TOKENS = len(TOK_BYTES)  # 160
MAX_BPE_DEPTH = 15  # Guarantees decoder stack[32] never overflows

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DICT_PATH = ROOT_DIR / "tools" / "datasets" / "bpe_dict.json"
DEFAULT_HEADER_PATH = ROOT_DIR / "esp32-firmware" / "src" / "generators" / "BpeTextDict.h"


def to_thermal_ascii(text: str) -> str:
    """Normalize non-ASCII punctuation/emojis in thermal guide prose to 7-bit printable ASCII."""
    s = (
        text.replace("\u2014", " - ")
        .replace("\u2013", "-")
        .replace("\u2600\ufe0f", "0")
        .replace("\u2600", "0")
        .replace("\U0001f319", "1")
        .replace("\ufe0f", "")
    )
    return "".join(ch if 32 <= ord(ch) < 127 else "" for ch in s)


def train_bpe(strings: List[str], max_tokens: int = MAX_BPE_TOKENS) -> List[List[int]]:
    """Train up to max_tokens BPE merge pairs with bounded tree depth."""
    seqs: List[List[int]] = []
    for s in strings:
        if not s:
            continue
        b = s.encode("ascii")
        for ch in b:
            if ch < 32 or ch >= 127:
                raise ValueError(f"Non-printable ASCII byte {ch} in {s!r}")
        seqs.append(list(b))

    depths = [0] * 256
    vocab: List[List[int]] = []

    for tb in TOK_BYTES[:max_tokens]:
        pairs: Counter = Counter()
        for seq in seqs:
            for i in range(len(seq) - 1):
                a, b = seq[i], seq[i + 1]
                if max(depths[a], depths[b]) + 1 <= MAX_BPE_DEPTH:
                    pairs[(a, b)] += 1
        if not pairs:
            break
        (a, b), cnt = pairs.most_common(1)[0]
        if cnt < 4:
            break
        vocab.append([a, b])
        depths[tb] = max(depths[a], depths[b]) + 1
        for s_idx, seq in enumerate(seqs):
            if len(seq) < 2:
                continue
            out: List[int] = []
            i = 0
            n = len(seq)
            while i < n:
                if i + 1 < n and seq[i] == a and seq[i + 1] == b:
                    out.append(tb)
                    i += 2
                else:
                    out.append(seq[i])
                    i += 1
            seqs[s_idx] = out

    return vocab


def encode_bpe(text: str, vocab: List[List[int]]) -> bytes:
    """Encode a 7-bit printable ASCII string using the trained BPE pairs."""
    b = text.encode("ascii")
    for ch in b:
        if ch < 32 or ch >= 127:
            raise ValueError(f"Non-printable ASCII byte {ch} in {text!r}")
    seq = list(b)
    for tb, (a, b2) in zip(TOK_BYTES, vocab):
        if len(seq) < 2:
            break
        out: List[int] = []
        i = 0
        n = len(seq)
        while i < n:
            if i + 1 < n and seq[i] == a and seq[i + 1] == b2:
                out.append(tb)
                i += 2
            else:
                out.append(seq[i])
                i += 1
        seq = out
    return bytes(seq)


def decode_bpe(encoded: bytes, vocab: List[List[int]]) -> str:
    """Reference Python decoder mirroring mp_bpe_decode_pgm()."""
    out: List[int] = []
    for b in encoded:
        if b == 0:
            break
        stack = [b]
        while stack:
            tok = stack.pop()
            if 32 <= tok < 127:
                out.append(tok)
            else:
                idx = (tok - 1) if tok < 32 else (tok - 127 + 31)
                left, right = vocab[idx]
                stack.append(right)
                stack.append(left)
    return bytes(out).decode("ascii")


class BpeBlobBuilder:
    """Deduplicating flat PROGMEM byte-blob builder for BPE-encoded C strings."""

    def __init__(self, vocab: List[List[int]]):
        self.vocab = vocab
        self.buf = bytearray()
        self.offsets: Dict[str, int] = {}

    def add(self, text: str) -> int:
        if text in self.offsets:
            return self.offsets[text]
        off = len(self.buf)
        if off >= 0xFFFF:
            raise OverflowError(f"BPE blob exceeded uint16_t capacity ({off} >= 65535)")
        enc = encode_bpe(text, self.vocab)
        if decode_bpe(enc, self.vocab) != text:
            raise RuntimeError(f"BPE round-trip mismatch for {text!r}")
        self.buf.extend(enc)
        self.buf.append(0)
        self.offsets[text] = off
        return off

    def format_c_array(self, name: str, cols: int = 16) -> List[str]:
        lines = [
            f"static const size_t {name}_LEN = {len(self.buf)};",
            f"static const uint8_t {name}[{len(self.buf)}] PROGMEM = {{",
        ]
        for i in range(0, len(self.buf), cols):
            chunk = self.buf[i : i + cols]
            hex_str = ", ".join(f"0x{b:02X}" for b in chunk)
            comma = "," if i + cols < len(self.buf) else ""
            lines.append(f"    {hex_str}{comma}")
        lines.append("};")
        return lines


def save_bpe_dict(vocab: List[List[int]], dict_path: Path = DEFAULT_DICT_PATH) -> None:
    dict_path.write_text(json.dumps({"pairs": vocab}, separators=(",", ":")), encoding="utf-8")


def load_bpe_dict(dict_path: Path = DEFAULT_DICT_PATH) -> List[List[int]]:
    data = json.loads(dict_path.read_text(encoding="utf-8"))
    return data["pairs"]


def write_bpe_header(vocab: List[List[int]], header_path: Path = DEFAULT_HEADER_PATH) -> None:
    padded = list(vocab) + [[0, 0]] * (MAX_BPE_TOKENS - len(vocab))
    lines = [
        "// Automatically generated by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef BPE_TEXT_DICT_H",
        "#define BPE_TEXT_DICT_H",
        "",
        "#include <Arduino.h>",
        "",
        f"static const uint8_t MP_BPE_PAIR_COUNT = {len(vocab)};",
        f"static const uint8_t MP_BPE_PAIRS[{MAX_BPE_TOKENS}][2] PROGMEM = {{",
    ]
    for i, (a, b) in enumerate(padded):
        comma = "," if i + 1 < len(padded) else ""
        lines.append(f"    {{0x{a:02X}, 0x{b:02X}}}{comma}")
    lines.extend([
        "};",
        "",
        "inline void mp_bpe_decode_pgm(const uint8_t* blob, uint16_t offset, char* dst, size_t dstCap) {",
        "    if (!dst || dstCap == 0) return;",
        "    dst[0] = '\\0';",
        "    if (offset == 0xFFFF) return;",
        "    size_t out = 0;",
        "    uint8_t stack[32];",
        "    uint8_t sp = 0;",
        "    const uint8_t* p = blob + offset;",
        "    while (true) {",
        "        uint8_t b = pgm_read_byte(p++);",
        "        if (b == 0) break;",
        "        stack[sp++] = b;",
        "        while (sp > 0) {",
        "            uint8_t tok = stack[--sp];",
        "            if (tok >= 32 && tok < 127) {",
        "                if (out + 1 < dstCap) {",
        "                    dst[out++] = (char)tok;",
        "                }",
        "            } else {",
        "                uint8_t idx = (tok < 32) ? (uint8_t)(tok - 1) : (uint8_t)(tok - 127 + 31);",
        "                uint8_t left = pgm_read_byte(&MP_BPE_PAIRS[idx][0]);",
        "                uint8_t right = pgm_read_byte(&MP_BPE_PAIRS[idx][1]);",
        "                if (sp + 2 <= sizeof(stack)) {",
        "                    stack[sp++] = right;",
        "                    stack[sp++] = left;",
        "                }",
        "            }",
        "        }",
        "    }",
        "    dst[out] = '\\0';",
        "}",
        "",
        "#endif // BPE_TEXT_DICT_H",
        "",
    ])
    header_path.write_text("\n".join(lines), encoding="utf-8")
