#!/usr/bin/env python3
"""
Pen and Paper Puzzles - Unified Curated Datasets Pipeline
Reads canonical JSON datasets in server/data/*.json and:
1. Compiles C++ PROGMEM headers in esp32-firmware/src/generators/
2. Injects / updates datasets in simulator/receipt_simulator.html
3. Synchronizes Arduino IDE sketch (PenAndPaperPuzzles/) via scripts/sync_arduino_sketch.sh
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpe_codec
import build_game_rules

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SERVER_DATA_DIR = ROOT_DIR / "server" / "data"
FW_GEN_DIR = ROOT_DIR / "esp32-firmware" / "src" / "generators"
FW_PRINTER_DIR = ROOT_DIR / "esp32-firmware" / "src" / "printer"
SIMULATOR_HTML = ROOT_DIR / "simulator" / "receipt_simulator.html"
SYNC_SCRIPT = ROOT_DIR / "scripts" / "sync_arduino_sketch.sh"


_SIM_HTML_BUF: Optional[str] = None


def _validate_ascii(value: str, label: str, max_len: Optional[int] = None) -> str:
    """Assert printable 7-bit ASCII and optional maximum length for embedded C++ literals."""
    if not isinstance(value, str):
        raise ValueError(f"{label}: expected string, got {type(value).__name__}")
    for ch in value:
        if ord(ch) < 32 or ord(ch) >= 127:
            raise ValueError(f"{label}: non-ASCII/control character {ch!r} (U+{ord(ch):04X}) in {value!r}")
    if max_len is not None and len(value) > max_len:
        raise ValueError(f"{label}: length {len(value)} exceeds max {max_len}: {value!r}")
    return value


def pack_nibbles(arr: List[int]) -> List[int]:
    """Pack a sequence of 4-bit integers into big-endian nibble pairs (2 values per byte)."""
    out = []
    for i in range(0, len(arr), 2):
        high = arr[i] & 0x0F
        low = (arr[i + 1] & 0x0F) if i + 1 < len(arr) else 0
        out.append((high << 4) | low)
    return out


def update_simulator_js(
    pattern: str,
    js_code: str,
    label: str,
    dotall: bool = False,
    fallback_after_pattern: Optional[str] = None,
) -> None:
    """Replace or inject a JavaScript constant/property definition in receipt_simulator.html."""
    global _SIM_HTML_BUF
    if not SIMULATOR_HTML.exists():
        raise FileNotFoundError(f"Simulator HTML not found at {SIMULATOR_HTML}")
    flags = re.DOTALL if dotall else 0
    content = _SIM_HTML_BUF if _SIM_HTML_BUF is not None else SIMULATOR_HTML.read_text(encoding="utf-8")
    if re.search(pattern, content, flags=flags):
        content = re.sub(pattern, lambda _m: js_code, content, flags=flags)
        action = "Updated"
    elif fallback_after_pattern and re.search(fallback_after_pattern, content):
        content = re.sub(
            fallback_after_pattern,
            lambda m: m.group(1) + "\n" + js_code,
            content,
            count=1,
        )
        action = "Injected"
    else:
        raise RuntimeError(f"Failed to match simulator marker for {label} in {SIMULATOR_HTML}")

    if _SIM_HTML_BUF is not None:
        _SIM_HTML_BUF = content
    else:
        SIMULATOR_HTML.write_text(content, encoding="utf-8")
    print(f"  -> {action} {label} in {SIMULATOR_HTML}")


# =============================================================================
# 1. STARS DATASET
# =============================================================================
def build_stars_dataset() -> None:
    json_path = SERVER_DATA_DIR / "stars_dataset.json"
    header_path = FW_GEN_DIR / "StarsDataset.h"
    print(f"Building StarsDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    lines = [
        "// Automatically generated from server/data/stars_dataset.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef STARS_DATASET_H",
        "#define STARS_DATASET_H",
        "",
        "#include <Arduino.h>",
        "",
        "static const size_t NUM_STARS_EASY = 100;",
        "static const size_t NUM_STARS_MEDIUM = 100;",
        "static const size_t NUM_STARS_HARD = 100;",
        "static const size_t NUM_STARS_EXTREME = 100;",
        "",
    ]

    tier_specs = [
        ("EASY", 5, 1, len(dataset["easy"])),
        ("MEDIUM", 8, 1, len(dataset["medium"])),
        ("HARD", 9, 2, len(dataset["hard"])),
        ("EXTREME", 10, 2, len(dataset["extreme"])),
    ]

    for tier, size, stars, count in tier_specs:
        puzzles = dataset[tier.lower()]
        total_cells = size * size
        total_stars = size * stars
        packed_region_bytes = (total_cells + 1) // 2

        lines.append(f"// --- {tier} ({size}x{size}, {stars}-Star) ---")
        lines.append(f"static const uint8_t STARS_{tier}_REGIONS[{count}][{packed_region_bytes}] PROGMEM = {{")
        for p in puzzles:
            flat = [p["regions"][r][c] for r in range(size) for c in range(size)]
            packed_regions = pack_nibbles(flat)
            lines.append("    {" + ", ".join(map(str, packed_regions)) + "},")
        lines.append("};")
        lines.append("")

        lines.append("#ifdef HOST_TEST")
        lines.append(f"static const uint8_t STARS_{tier}_SOLUTIONS[{count}][{total_stars}] PROGMEM = {{")
        for p in puzzles:
            packed_solutions = [f"0x{(s[0] << 4) | (s[1] & 0x0F):02X}" for s in p["solution"]]
            lines.append(f"    {{{', '.join(packed_solutions)}}},")
        lines.append("};")
        lines.append("#endif")
        lines.append("")

    lines.append("#endif // STARS_DATASET_H\n")
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator
    if SIMULATOR_HTML.exists():
        sim_res = {}
        for tier in ["easy", "medium", "hard", "extreme"]:
            sim_res[tier] = []
            for p in dataset[tier]:
                r_str = "".join(str(cell) for row in p["regions"] for cell in row)
                s_str = "".join(f"{s[0]}{s[1]}" for s in p["solution"])
                sim_res[tier].append([r_str, s_str])

        js_code = "    const STARS_DATASET = " + json.dumps(sim_res, separators=(",", ":")) + ";"
        update_simulator_js(r"    const STARS_DATASET = \{.*?\};", js_code, "STARS_DATASET")


# =============================================================================
# 2. KILLER SUDOKU DATASET
# =============================================================================
def build_killer_dataset() -> None:
    json_path = SERVER_DATA_DIR / "killer_dataset.json"
    header_path = FW_GEN_DIR / "KillerDataset.h"
    print(f"Building KillerDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    lines = [
        "// Automatically generated from server/data/killer_dataset.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef KILLER_DATASET_H",
        "#define KILLER_DATASET_H",
        "",
        "#include <Arduino.h>",
        "",
        "static const size_t NUM_KILLER_EASY = 100;",
        "static const size_t NUM_KILLER_MEDIUM = 100;",
        "static const size_t NUM_KILLER_HARD = 100;",
        "static const size_t NUM_KILLER_EXTREME = 100;",
        "",
        "#ifdef HOST_TEST",
        "#define MP_KILLER_SOL_FIELD(n) uint8_t solution[n];",
        "#define MP_KILLER_SOL(...) , { __VA_ARGS__ }",
        "#else",
        "#define MP_KILLER_SOL_FIELD(n)",
        "#define MP_KILLER_SOL(...)",
        "#endif",
        "",
        "struct Killer4x4Entry {",
        "    uint8_t cage_map[8];",
        "    uint8_t cage_sums[8];",
        "    uint8_t num_cages;",
        "    MP_KILLER_SOL_FIELD(8)",
        "};",
        "",
        "struct Killer6x6Entry {",
        "    uint8_t cage_map[18];",
        "    uint8_t cage_sums[16];",
        "    uint8_t num_cages;",
        "    MP_KILLER_SOL_FIELD(18)",
        "};",
        "",
    ]

    killer_tiers = [
        ("easy", "KILLER_EASY_DATASET", "Killer4x4Entry", 4, 8, "EASY (4x4, Digits 1-4, Zero Singles, Pure Dominoes)"),
        ("medium", "KILLER_MEDIUM_DATASET", "Killer4x4Entry", 4, 8, "MEDIUM (4x4, Digits 1-4, Zero Singles)"),
        ("hard", "KILLER_HARD_DATASET", "Killer6x6Entry", 6, 16, "HARD (6x6, Digits 1-6, Zero Singles, 2-3 Cells)"),
        ("extreme", "KILLER_EXTREME_DATASET", "Killer6x6Entry", 6, 16, "EXTREME (6x6, Digits 1-6, Zero Singles)"),
    ]
    for tier, arr_name, struct_name, size, max_cages, comment in killer_tiers:
        lines.append(f"// --- {comment} ---")
        lines.append(f"static const {struct_name} {arr_name}[100] PROGMEM = {{")
        for p in dataset[tier]:
            c_map = [0] * (size * size)
            for cg in p["cages"]:
                cid = cg["id"]
                for r, c in cg["cells"]:
                    c_map[r * size + c] = cid
            c_packed = pack_nibbles(c_map)
            sol_flat = [p["solution"][r][c] for r in range(size) for c in range(size)]
            sol_packed = pack_nibbles(sol_flat)
            num_cages = len(p["cages"])
            assert num_cages <= max_cages, f"Killer {size}x{size} {tier} cages {num_cages} > {max_cages}"
            sums = [cg["sum"] for cg in p["cages"]] + [0] * (max_cages - num_cages)

            c_str = "{" + ", ".join(str(x) for x in c_packed) + "}"
            sums_str = "{" + ", ".join(str(x) for x in sums) + "}"
            s_args = ", ".join(str(x) for x in sol_packed)
            lines.append(f"    {{{c_str}, {sums_str}, {num_cages} MP_KILLER_SOL({s_args})}},")
        lines.append("};")
        lines.append("")

    lines.append("#endif // KILLER_DATASET_H\n")

    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator with compact representation: [size, box_rows, box_cols, c_map_hex, sums, sol]
    compact_js = {}
    for tier, puzzles in dataset.items():
        tier_list = []
        for p in puzzles:
            sz = p["size"]
            c_map = [0] * (sz * sz)
            for cg in p["cages"]:
                cid = cg["id"]
                if cid >= 16:
                    raise ValueError(f"Killer cage id {cid} exceeds hex nibble encoding")
                for cell in cg["cells"]:
                    c_map[cell[0] * sz + cell[1]] = cid
            c_map_str = "".join(f"{x:x}" for x in c_map)
            sums = [cg["sum"] for cg in p["cages"]]
            sol_str = "".join(str(p["solution"][r][c]) for r in range(sz) for c in range(sz))
            tier_list.append([sz, p["box_rows"], p["box_cols"], c_map_str, sums, sol_str])
        compact_js[tier] = tier_list
    js_code = "    const KILLER_DATASET = " + json.dumps(compact_js, separators=(",", ":")) + ";"
    update_simulator_js(r"    const KILLER_DATASET = \{.*?\};", js_code, "KILLER_DATASET")


# =============================================================================
# 3. WORD LADDER DATASET
# =============================================================================
def build_ladder_dataset(vocab: List[List[int]]) -> None:
    json_path = SERVER_DATA_DIR / "ladder_words.json"
    header_path = FW_GEN_DIR / "LadderDataset.h"
    print(f"Building LadderDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    blob = bpe_codec.BpeBlobBuilder(vocab)
    tier_entries: Dict[str, List[str]] = {}
    for tier in ("easy", "medium", "hard"):
        entries = []
        for item in dataset[tier]:
            w_len = item.get("wordLen", len(item["solution"][0]))
            total_w = item.get("totalWords", len(item["solution"]))
            words_str = _validate_ascii(item.get("words", " ".join(item["solution"])), f"ladder[{tier}].words")
            off = blob.add(words_str)
            entries.append(f"    {{ {w_len}, {total_w}, {off} }},")
        tier_entries[tier] = entries

    lines = [
        "// Automatically generated from server/data/ladder_words.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef LADDER_DATASET_H",
        "#define LADDER_DATASET_H",
        "",
        "#include <Arduino.h>",
        '#include "BpeTextDict.h"',
        "",
        "struct LadderDef {",
        "    uint8_t wordLen;",
        "    uint8_t totalWords;",
        "    uint16_t wordsOff;",
        "};",
        "",
        "static const size_t NUM_LADDER_PUZZLES_PER_DIFF = 50;",
        "",
    ]
    lines.extend(blob.format_c_array("LADDER_STRINGS"))
    lines.append("")

    for tier, var_name in [("easy", "EASY_LADDERS"), ("medium", "MEDIUM_LADDERS"), ("hard", "HARD_LADDERS")]:
        lines.append(f"static const LadderDef {var_name}[NUM_LADDER_PUZZLES_PER_DIFF] PROGMEM = {{")
        lines.extend(tier_entries[tier])
        lines.append("};")
        lines.append("")

    lines.append("#endif // LADDER_DATASET_H\n")
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator
    js_code = "    const LADDER_DATASET = " + json.dumps(dataset, separators=(",", ":")) + ";"
    update_simulator_js(r"    const LADDER_DATASET = \{.*?\};", js_code, "LADDER_DATASET")


# =============================================================================
# 4. WORD SEARCH DATASET
# =============================================================================
def build_wordsearch_dataset(vocab: List[List[int]]) -> None:
    json_path = SERVER_DATA_DIR / "wordsearch_dataset.json"
    header_path = FW_GEN_DIR / "WordSearchDataset.h"
    print(f"Building WordSearchDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    easy_words = dataset["easy"]
    medium_words = dataset["medium"]
    hard_words = dataset["hard"]

    blob = bpe_codec.BpeBlobBuilder(vocab)
    tier_offsets: Dict[str, List[int]] = {}
    for tier, words in [("easy", easy_words), ("medium", medium_words), ("hard", hard_words)]:
        offs = []
        for w in words:
            _validate_ascii(w, f"wordsearch[{tier}]", max_len=16)
            offs.append(blob.add(w))
        tier_offsets[tier] = offs

    lines = [
        "// Automatically generated from server/data/wordsearch_dataset.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef WORD_SEARCH_DATASET_H",
        "#define WORD_SEARCH_DATASET_H",
        "",
        "#include <Arduino.h>",
        '#include "WordSearchGen.h"',
        '#include "BpeTextDict.h"',
        "",
        f"static const size_t NUM_WS_EASY_WORDS = {len(easy_words)};",
        f"static const size_t NUM_WS_MEDIUM_WORDS = {len(medium_words)};",
        f"static const size_t NUM_WS_HARD_WORDS = {len(hard_words)};",
        "",
    ]
    lines.extend(blob.format_c_array("WS_STRINGS"))
    lines.append("")

    for tier, var_name, count_var in [
        ("easy", "WS_EASY_OFFSETS", "NUM_WS_EASY_WORDS"),
        ("medium", "WS_MEDIUM_OFFSETS", "NUM_WS_MEDIUM_WORDS"),
        ("hard", "WS_HARD_OFFSETS", "NUM_WS_HARD_WORDS"),
    ]:
        offs = tier_offsets[tier]
        lines.append(f"static const uint16_t {var_name}[{count_var}] PROGMEM = {{")
        for i in range(0, len(offs), 16):
            chunk = ", ".join(str(x) for x in offs[i : i + 16])
            comma = "," if i + 16 < len(offs) else ""
            lines.append(f"    {chunk}{comma}")
        lines.append("};")
        lines.append("")

    lines.extend([
        "inline size_t getWordSearchPoolCount(WordSearchDifficulty diff) {",
        "    switch (diff) {",
        "        case WS_EASY: return NUM_WS_EASY_WORDS;",
        "        case WS_HARD: return NUM_WS_HARD_WORDS;",
        "        case WS_MEDIUM:",
        "        default: return NUM_WS_MEDIUM_WORDS;",
        "    }",
        "}",
        "",
        "inline void getWordSearchWord(WordSearchDifficulty diff, size_t idx, char* dst, size_t dstCap) {",
        "    const uint16_t* offs = WS_MEDIUM_OFFSETS;",
        "    if (diff == WS_EASY) offs = WS_EASY_OFFSETS;",
        "    else if (diff == WS_HARD) offs = WS_HARD_OFFSETS;",
        "    uint16_t off = pgm_read_word(&offs[idx]);",
        "    mp_bpe_decode_pgm(WS_STRINGS, off, dst, dstCap);",
        "}",
        "",
        "#endif // WORD_SEARCH_DATASET_H\n",
    ])
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator
    for tier, var_name in [
        ("easy", "WORD_SEARCH_WORDS_EASY"),
        ("medium", "WORD_SEARCH_WORDS_MEDIUM"),
        ("hard", "WORD_SEARCH_WORDS_HARD"),
    ]:
        js_code = f"    const {var_name} = " + json.dumps(dataset[tier], separators=(",", ":")) + ";"
        update_simulator_js(rf"    const {var_name} = \[.*?\];", js_code, var_name)


# =============================================================================
# 5. CRYPTOGRAM DATASET
# =============================================================================
def build_cryptogram_dataset(vocab: List[List[int]]) -> None:
    json_path = SERVER_DATA_DIR / "cryptograms.json"
    header_path = FW_GEN_DIR / "CryptogramDataset.h"
    print(f"Building CryptogramDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        quotes = json.load(f)

    by_diff = {"easy": [], "medium": [], "hard": []}
    for q in quotes:
        d = q.get("diff", "easy").lower()
        if d in by_diff:
            by_diff[d].append(q)

    blob = bpe_codec.BpeBlobBuilder(vocab)
    tier_entries: Dict[str, List[str]] = {}
    for tier in ("easy", "medium", "hard"):
        entries = []
        for item in by_diff[tier][:100]:
            phrase = _validate_ascii(item["phrase"], f"cryptogram[{tier}].phrase")
            author = _validate_ascii(item["author"], f"cryptogram[{tier}].author")
            p_off = blob.add(phrase)
            a_off = blob.add(author)
            entries.append(f"    {{{p_off}, {a_off}}},")
        tier_entries[tier] = entries

    lines = [
        "// Automatically generated from server/data/cryptograms.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef CRYPTOGRAM_DATASET_H",
        "#define CRYPTOGRAM_DATASET_H",
        "",
        "#include <Arduino.h>",
        '#include "BpeTextDict.h"',
        "",
        "struct CryptogramQuote {",
        "    uint16_t phraseOff;",
        "    uint16_t authorOff;",
        "};",
        "",
        "static const size_t NUM_CRYPTOGRAMS_PER_DIFF = 100;",
        f"static const size_t TOTAL_CRYPTOGRAM_PUZZLES = {len(quotes)};",
        "",
    ]
    lines.extend(blob.format_c_array("CRYPTOGRAM_STRINGS"))
    lines.append("")

    for tier, var_name in [("easy", "EASY_CRYPTOGRAMS"), ("medium", "MEDIUM_CRYPTOGRAMS"), ("hard", "HARD_CRYPTOGRAMS")]:
        lines.append(f"static const CryptogramQuote {var_name}[NUM_CRYPTOGRAMS_PER_DIFF] PROGMEM = {{")
        lines.extend(tier_entries[tier])
        lines.append("};")
        lines.append("")

    lines.append("#endif // CRYPTOGRAM_DATASET_H\n")
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator
    js_code = (
        "    class CryptogramSimulator {\n"
        "      constructor() {\n"
        "        this.puzzles = " + json.dumps(quotes, separators=(",", ":")) + ";"
    )
    update_simulator_js(
        r"    class CryptogramSimulator \{\n      constructor\(\) \{\n        this\.puzzles = \[.*?\];",
        js_code,
        "CryptogramSimulator.puzzles",
    )


# =============================================================================
# 6. JUMBLE DATASET
# =============================================================================
def build_jumble_dataset(vocab: List[List[int]]) -> None:
    json_path = SERVER_DATA_DIR / "jumbles.json"
    header_path = FW_GEN_DIR / "JumbleDataset.h"
    print(f"Building JumbleDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        jumbles = json.load(f)

    blob = bpe_codec.BpeBlobBuilder(vocab)
    entries = []
    for item in jumbles:
        words = item["words"]
        circles = item["circles"]
        riddle = _validate_ascii(item["riddle"], "jumble.riddle")
        answer = _validate_ascii(item["answer"], "jumble.answer")

        masks = []
        for c_list in circles:
            mask = 0
            for idx in c_list:
                mask |= (1 << idx)
            masks.append(f"0x{mask:02X}")
        while len(masks) < 6:
            masks.append("0x00")

        words_str = _validate_ascii(" ".join(words), "jumble.words")
        w_off = blob.add(words_str)
        r_off = blob.add(riddle)
        a_off = blob.add(answer)
        entries.append(f"    {{ {len(words)}, {{{', '.join(masks)}}}, {w_off}, {r_off}, {a_off} }},")

    lines = [
        "// Automatically generated from server/data/jumbles.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef JUMBLE_DATASET_H",
        "#define JUMBLE_DATASET_H",
        "",
        "#include <Arduino.h>",
        '#include "BpeTextDict.h"',
        "",
        "struct CompactRiddleSet {",
        "    uint8_t numWords;",
        "    uint8_t circleMasks[6];",
        "    uint16_t wordsOff;",
        "    uint16_t riddleOff;",
        "    uint16_t answerOff;",
        "};",
        "",
        f"static const size_t TOTAL_JUMBLE_PUZZLES = {len(jumbles)};",
        "",
    ]
    lines.extend(blob.format_c_array("JUMBLE_STRINGS"))
    lines.append("")
    lines.append("static const CompactRiddleSet JUMBLE_DATASET[] PROGMEM = {")
    lines.extend(entries)
    lines.append("};")
    lines.append("")
    lines.append("#endif // JUMBLE_DATASET_H\n")
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator
    js_code = "    const JUMBLE_RIDDLES = " + json.dumps(jumbles, separators=(",", ":")) + ";"
    update_simulator_js(r"    const JUMBLE_RIDDLES = \[.*?\];", js_code, "JUMBLE_RIDDLES")


# =============================================================================
# 7. WHEEL DATASET
# =============================================================================
def build_wheel_dataset() -> None:
    json_path = SERVER_DATA_DIR / "wheel_dictionary.json"
    header_path = FW_GEN_DIR / "WheelDataset.h"
    print(f"Building WheelDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    puzzles = data.get("puzzles", [])
    by_diff = {"easy": [], "medium": [], "hard": []}
    for p in puzzles:
        d = p.get("difficulty", "medium").lower()
        if d in by_diff:
            by_diff[d].append(p)

    lines = [
        "// Automatically generated from server/data/wheel_dictionary.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef WHEEL_DATASET_H",
        "#define WHEEL_DATASET_H",
        "",
        "#include <Arduino.h>",
        "",
        "struct WheelPuzzleDef {",
        "    char center;",
        "    char outer[7];",
        "    uint8_t wordCount;",
        "    uint8_t good;",
        "    uint8_t great;",
        "    uint8_t genius;",
        "    uint8_t count4;",
        "    uint8_t count5;",
        "    uint8_t count6;",
        "    uint8_t count7plus;",
        "};",
        "",
        "static const size_t NUM_WHEEL_PUZZLES_PER_DIFF = 20;",
        "",
    ]

    for tier, var_name in [("easy", "EASY_WHEEL_PUZZLES"), ("medium", "MEDIUM_WHEEL_PUZZLES"), ("hard", "HARD_WHEEL_PUZZLES")]:
        items = by_diff[tier][:20]
        lines.append(f"static const WheelPuzzleDef {var_name}[NUM_WHEEL_PUZZLES_PER_DIFF] PROGMEM = {{")
        for p in items:
            center = _validate_ascii(p["center_letter"], f"wheel[{tier}].center", max_len=1)
            outer = _validate_ascii("".join(p["outer_letters"]), f"wheel[{tier}].outer", max_len=6)
            wc = p["word_count"]
            bm = p.get("benchmarks", {})
            lc = p.get("length_counts", {})
            good = bm.get("good", 15)
            great = bm.get("great", 25)
            genius = bm.get("genius", 35)
            c4 = lc.get("4", 0)
            c5 = lc.get("5", 0)
            c6 = lc.get("6", 0)
            c7 = lc.get("7+", 0)
            lines.append(f"    {{ '{center}', \"{outer}\", {wc}, {good}, {great}, {genius}, {c4}, {c5}, {c6}, {c7} }},")
        lines.append("};")
        lines.append("")

    lines.append("#endif // WHEEL_DATASET_H\n")
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator
    sim_wheel = {"easy": [], "medium": [], "hard": []}
    for tier in ["easy", "medium", "hard"]:
        for p in by_diff[tier][:20]:
            bm = p.get("benchmarks", {})
            lc = p.get("length_counts", {})
            sim_wheel[tier].append({
                "center": p["center_letter"],
                "outer": p["outer_letters"],
                "pangram": p.get("pangrams", [""])[0] if p.get("pangrams") else "",
                "wordCount": p["word_count"],
                "good": bm.get("good", 15),
                "great": bm.get("great", 25),
                "genius": bm.get("genius", 35),
                "count4": lc.get("4", 0),
                "count5": lc.get("5", 0),
                "count6": lc.get("6", 0),
                "count7plus": lc.get("7+", 0),
            })
    js_code = (
        "    class WheelSimulator {\n"
        "      constructor() {\n"
        "        this.puzzles = " + json.dumps(sim_wheel, separators=(",", ":")) + ";"
    )
    update_simulator_js(
        r"    class WheelSimulator \{\n      constructor\(\) \{\n        this\.puzzles = \{.*?\};",
        js_code,
        "WheelSimulator.puzzles",
    )


# =============================================================================
# 8. TOWERS DATASET
# =============================================================================
def build_towers_dataset() -> None:
    json_path = SERVER_DATA_DIR / "towers_dataset.json"
    header_path = FW_GEN_DIR / "TowersDataset.h"
    print(f"Building TowersDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    lines = [
        "// Automatically generated from server/data/towers_dataset.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef TOWERS_DATASET_H",
        "#define TOWERS_DATASET_H",
        "",
        "#include <Arduino.h>",
        "",
        "static const size_t NUM_TOWERS_EASY = 100;",
        "static const size_t NUM_TOWERS_MEDIUM = 100;",
        "static const size_t NUM_TOWERS_HARD = 100;",
        "static const size_t NUM_TOWERS_EXTREME = 100;",
        "",
        "#ifdef HOST_TEST",
        "#define MP_TOWERS_SOL_FIELD(n) uint8_t solution[n];",
        "#define MP_TOWERS_SOL(...) { __VA_ARGS__ },",
        "#else",
        "#define MP_TOWERS_SOL_FIELD(n)",
        "#define MP_TOWERS_SOL(...)",
        "#endif",
        "",
        "struct Towers4x4Entry {",
        "    MP_TOWERS_SOL_FIELD(8)",
        "    uint8_t clues[8];    // 16 clues: top(4), bottom(4), left(4), right(4)",
        "};",
        "",
        "struct Towers5x5Entry {",
        "    MP_TOWERS_SOL_FIELD(13)",
        "    uint8_t clues[10];    // 20 clues: top(5), bottom(5), left(5), right(5)",
        "};",
        "",
    ]

    tier_specs = [
        ("EASY", 4),
        ("MEDIUM", 4),
        ("HARD", 5),
        ("EXTREME", 5),
    ]

    for tier, size in tier_specs:
        puzzles = dataset[tier.lower()]
        entry_type = f"Towers{size}x{size}Entry"
        lines.append(f"// --- {tier} ({size}x{size}, Heights 1-{size}) ---")
        lines.append(f"static const {entry_type} TOWERS_{tier}_DATASET[100] PROGMEM = {{")
        for p in puzzles:
            sol_flat = [p["solution"][r][c] for r in range(size) for c in range(size)]
            sol_packed = pack_nibbles(sol_flat)
            clues_flat = p["clues"]["top"] + p["clues"]["bottom"] + p["clues"]["left"] + p["clues"]["right"]
            clues_packed = pack_nibbles(clues_flat)
            s_args = ", ".join(str(x) for x in sol_packed)
            c_str = "{" + ", ".join(str(x) for x in clues_packed) + "}"
            lines.append(f"    {{MP_TOWERS_SOL({s_args}) {c_str}}},")
        lines.append("};\n")

    lines.append("#endif // TOWERS_DATASET_H\n")
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator with compact representation: [size, clues_str, sol_str]
    compact_js = {}
    for tier, puzzles in dataset.items():
        tier_list = []
        for p in puzzles:
            sz = p["size"]
            cl = p["clues"]
            clues_str = "".join(str(x) for x in (cl["top"] + cl["bottom"] + cl["left"] + cl["right"]))
            sol_str = "".join(str(p["solution"][r][c]) for r in range(sz) for c in range(sz))
            tier_list.append([sz, clues_str, sol_str])
        compact_js[tier] = tier_list
    js_code = "    const TOWERS_DATASET = " + json.dumps(compact_js, separators=(",", ":")) + ";"
    update_simulator_js(
        r"    const TOWERS_DATASET = \{.*?\};",
        js_code,
        "TOWERS_DATASET",
        fallback_after_pattern=r"(const STARS_DATASET = \{.*?\};)",
    )


def pack_2bit(values: list) -> list:
    packed = []
    for i in range(0, len(values), 4):
        b = 0
        for j in range(4):
            v = (values[i + j] & 0x03) if (i + j) < len(values) else 0
            b |= v << ((3 - j) * 2)
        packed.append(b)
    return packed


# =============================================================================
# 9. INEQUALITY DATASET
# =============================================================================
def build_inequality_dataset() -> None:
    json_path = SERVER_DATA_DIR / "inequality_dataset.json"
    header_path = FW_GEN_DIR / "InequalityDataset.h"
    print(f"Building InequalityDataset from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    lines = [
        "// Automatically generated from server/data/inequality_dataset.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef INEQUALITY_DATASET_H",
        "#define INEQUALITY_DATASET_H",
        "",
        "#include <Arduino.h>",
        "",
        "static const size_t NUM_INEQUALITY_EASY = 100;",
        "static const size_t NUM_INEQUALITY_MEDIUM = 100;",
        "static const size_t NUM_INEQUALITY_HARD = 100;",
        "static const size_t NUM_INEQUALITY_EXTREME = 100;",
        "",
        "#ifdef HOST_TEST",
        "#define MP_INEQ_SOL_FIELD(n) uint8_t solution[n];",
        "#define MP_INEQ_SOL(...) { __VA_ARGS__ },",
        "#else",
        "#define MP_INEQ_SOL_FIELD(n)",
        "#define MP_INEQ_SOL(...)",
        "#endif",
        "",
        "struct Inequality4x4Entry {",
        "    MP_INEQ_SOL_FIELD(8)",
        "    uint8_t givens[8];   // 16 cells packed nibbles (0=empty, 1..4=given)",
        "    uint8_t edges_h[3];  // 12 edges packed at 2 bits/edge",
        "    uint8_t edges_v[3];  // 12 edges packed at 2 bits/edge",
        "};",
        "",
        "struct Inequality5x5Entry {",
        "    MP_INEQ_SOL_FIELD(13)",
        "    uint8_t givens[13];  // 25 cells packed nibbles",
        "    uint8_t edges_h[5];  // 20 edges packed at 2 bits/edge",
        "    uint8_t edges_v[5];  // 20 edges packed at 2 bits/edge",
        "};",
        "",
    ]

    tier_specs = [
        ("EASY", 4),
        ("MEDIUM", 4),
        ("HARD", 5),
        ("EXTREME", 5),
    ]

    for tier, size in tier_specs:
        puzzles = dataset[tier.lower()]
        entry_type = f"Inequality{size}x{size}Entry"
        lines.append(f"// --- {tier} ({size}x{size}, Digits 1-{size}) ---")
        lines.append(f"static const {entry_type} INEQUALITY_{tier}_DATASET[100] PROGMEM = {{")
        for p in puzzles:
            sol_flat = [p["solution"][r][c] for r in range(size) for c in range(size)]
            sol_packed = pack_nibbles(sol_flat)

            givens_grid = [0] * (size * size)
            for r, c, val in p["givens"]:
                givens_grid[r * size + c] = val
            givens_packed = pack_nibbles(givens_grid)

            eh_packed = pack_2bit([p["edges_h"][r][c] for r in range(size) for c in range(size - 1)])
            ev_packed = pack_2bit([p["edges_v"][r][c] for r in range(size - 1) for c in range(size)])

            s_args = ", ".join(str(x) for x in sol_packed)
            g_str = "{" + ", ".join(str(x) for x in givens_packed) + "}"
            eh_str = "{" + ", ".join(str(x) for x in eh_packed) + "}"
            ev_str = "{" + ", ".join(str(x) for x in ev_packed) + "}"

            lines.append(f"    {{MP_INEQ_SOL({s_args}) {g_str}, {eh_str}, {ev_str}}},")
        lines.append("};\n")

    lines.append("#endif // INEQUALITY_DATASET_H\n")
    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    # Update simulator with compact representation: [size, givens_str, eh_str, ev_str, sol_str]
    compact_js = {}
    for tier, puzzles in dataset.items():
        tier_list = []
        for p in puzzles:
            sz = p["size"]
            g_grid = ["0"] * (sz * sz)
            for r, c, val in p["givens"]:
                g_grid[r * sz + c] = str(val)
            eh_str = "".join(str(p["edges_h"][r][c]) for r in range(sz) for c in range(sz - 1))
            ev_str = "".join(str(p["edges_v"][r][c]) for r in range(sz - 1) for c in range(sz))
            sol_str = "".join(str(p["solution"][r][c]) for r in range(sz) for c in range(sz))
            tier_list.append([sz, "".join(g_grid), eh_str, ev_str, sol_str])
        compact_js[tier] = tier_list
    js_code = "    const INEQUALITY_DATASET = " + json.dumps(compact_js, separators=(",", ":")) + ";"
    update_simulator_js(
        r"    const INEQUALITY_DATASET = \{.*?\};",
        js_code,
        "INEQUALITY_DATASET",
        fallback_after_pattern=r"(const TOWERS_DATASET = \{.*?\};)",
    )


# =============================================================================
# 10. THERMAL FONTS (203 DPI 1-BIT PROPORTIONAL + IN-BOARD GLYPHS)
# =============================================================================
def build_thermal_fonts() -> None:
    import base64

    json_path = SERVER_DATA_DIR / "thermal_fonts.json"
    header_path = FW_PRINTER_DIR / "ThermalFonts.h"
    print(f"Building ThermalFonts from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    grid_chars = _validate_ascii(data["grid_chars"], "thermal_fonts.grid_chars")
    grid_map = [255] * 95
    for idx, ch in enumerate(grid_chars):
        code = ord(ch)
        if 32 <= code < 127:
            grid_map[code - 32] = idx

    enum_names = {
        "caption_16": "FONT_CAPTION_16",
        "body_20": "FONT_BODY_20",
        "subhead_22": "FONT_SUBHEAD_22",
        "display_32": "FONT_DISPLAY_32",
        "grid_12x14": "FONT_GRID_12x14",
        "grid_18x21": "FONT_GRID_18x21",
    }

    lines = [
        "// Automatically generated from server/data/thermal_fonts.json by tools/datasets/build_all_datasets.py",
        "// Do not edit directly!",
        "#ifndef THERMAL_FONTS_H",
        "#define THERMAL_FONTS_H",
        "",
        "#include <Arduino.h>",
        "",
        "enum ThermalFontId : uint8_t {",
        "    FONT_CAPTION_16 = 0,",
        "    FONT_BODY_20 = 1,",
        "    FONT_SUBHEAD_22 = 2,",
        "    FONT_DISPLAY_32 = 3,",
        "    FONT_GRID_12x14 = 4,",
        "    FONT_GRID_18x21 = 5,",
        "    THERMAL_FONT_COUNT = 6",
        "};",
        "",
        "struct ThermalGlyph {",
        "    uint8_t w;",
        "    uint8_t h;",
        "    int8_t xOff;",
        "    int8_t yOff;",
        "    uint8_t xAdv;",
        "    uint16_t bitOffset;",
        "};",
        "",
        "struct ThermalFontDef {",
        "    uint8_t lineHeight;",
        "    uint8_t baseline;",
        "    uint8_t fixedW;",
        "    uint8_t fixedH;",
        "    uint8_t glyphCount;",
        "    const ThermalGlyph* glyphs;",
        "    const uint8_t* bitmap;",
        "};",
        "",
        "static const uint8_t THERMAL_GRID_ASCII_MAP[95] PROGMEM = {",
    ]
    for i in range(0, 95, 16):
        chunk = ", ".join(str(v) for v in grid_map[i : i + 16])
        lines.append(f"    {chunk},")
    lines.append("};\n")

    font_defs_entries = []
    js_fonts: Dict[str, Any] = {"gridChars": grid_chars, "fonts": {}}

    for font in data["fonts"]:
        fid = font["id"]
        upper_id = fid.upper()
        raw_bytes = base64.b64decode(font["bitmap_b64"])

        lines.append(f"static const uint8_t TF_{upper_id}_BITMAP[] PROGMEM = {{")
        for i in range(0, len(raw_bytes), 20):
            chunk = ", ".join(f"0x{b:02X}" for b in raw_bytes[i : i + 20])
            lines.append(f"    {chunk},")
        lines.append("};\n")

        lines.append(f"static const ThermalGlyph TF_{upper_id}_GLYPHS[] PROGMEM = {{")
        js_glyphs = []
        for g in font["glyphs"]:
            code = int(g["code"])
            if code < 32 or code >= 127:
                raise ValueError(f"Non-ASCII glyph code {code} in {fid}")
            lines.append(
                f"    {{{g['w']}, {g['h']}, {g['xOff']}, {g['yOff']}, {g['xAdv']}, {g['bitOffset']}}},"
            )
            js_glyphs.append([g["w"], g["h"], g["xOff"], g["yOff"], g["xAdv"], g["bitOffset"]])
        lines.append("};\n")

        font_defs_entries.append(
            f"    {{{font['lineHeight']}, {font['baseline']}, {font['fixedW']}, {font['fixedH']}, "
            f"{len(font['glyphs'])}, TF_{upper_id}_GLYPHS, TF_{upper_id}_BITMAP}}"
        )
        js_fonts["fonts"][fid] = {
            "lh": font["lineHeight"],
            "bl": font["baseline"],
            "fw": font["fixedW"],
            "fh": font["fixedH"],
            "b64": font["bitmap_b64"],
            "g": js_glyphs,
        }

    lines.append("static const ThermalFontDef THERMAL_FONT_DEFS[THERMAL_FONT_COUNT] PROGMEM = {")
    for entry in font_defs_entries:
        lines.append(f"{entry},")
    lines.append("};\n")
    lines.append("#endif // THERMAL_FONTS_H\n")

    header_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Wrote {header_path}")

    js_code = (
        "    /* [[START_THERMAL_FONTS_DATA]] */\n"
        "    const THERMAL_FONTS = " + json.dumps(js_fonts, separators=(",", ":")) + ";\n"
        "    /* [[END_THERMAL_FONTS_DATA]] */"
    )
    update_simulator_js(
        r"    /\* \[\[START_THERMAL_FONTS_DATA\]\] \*/.*?/\* \[\[END_THERMAL_FONTS_DATA\]\] \*/",
        js_code,
        "THERMAL_FONTS",
        dotall=True,
    )


def build_shared_bpe_dict() -> List[List[int]]:
    print("Training shared 160-token BPE dictionary across text datasets...")
    strings: List[str] = []

    ladder = json.loads((SERVER_DATA_DIR / "ladder_words.json").read_text(encoding="utf-8"))
    for tier in ("easy", "medium", "hard"):
        for item in ladder[tier]:
            strings.append(item.get("words", " ".join(item["solution"])))

    ws = json.loads((SERVER_DATA_DIR / "wordsearch_dataset.json").read_text(encoding="utf-8"))
    for tier in ("easy", "medium", "hard"):
        strings.extend(ws[tier])

    cryptos = json.loads((SERVER_DATA_DIR / "cryptograms.json").read_text(encoding="utf-8"))
    for q in cryptos:
        if q.get("diff", "easy").lower() in ("easy", "medium", "hard"):
            strings.append(q["phrase"])
            strings.append(q["author"])

    jumbles = json.loads((SERVER_DATA_DIR / "jumbles.json").read_text(encoding="utf-8"))
    for item in jumbles:
        strings.append(" ".join(item["words"]))
        strings.append(item["riddle"])
        strings.append(item["answer"])

    rules = json.loads((SERVER_DATA_DIR / "game_rules.json").read_text(encoding="utf-8"))
    for g in rules.get("games", []):
        for s in (
            [
                g["key"], g["title"], g["instruction"], g["objective"],
                g.get("valid_move", {}).get("caption", ""),
                g.get("invalid_move", {}).get("caption", ""),
            ]
            + g.get("rules", [])[:4]
            + g.get("opening_anchors", [])[:2]
            + [fq.get("q", "") for fq in g.get("faq", [])[:2]]
            + [fq.get("a", "") for fq in g.get("faq", [])[:2]]
            + [str(op[5]) for op in g.get("diagram_ops", []) if op[1] == "text"]
        ):
            strings.append(bpe_codec.to_thermal_ascii(s))

    vocab = bpe_codec.train_bpe(strings)
    bpe_codec.save_bpe_dict(vocab)
    bpe_codec.write_bpe_header(vocab)
    print(f"  -> Wrote BpeTextDict.h ({len(vocab)} BPE pairs)")
    return vocab


def main() -> None:
    global _SIM_HTML_BUF
    print("==================================================================")
    print("STARTING UNIFIED CURATED DATASETS COMPILATION PIPELINE")
    print("==================================================================")
    if not SIMULATOR_HTML.exists():
        raise FileNotFoundError(f"Simulator HTML not found at {SIMULATOR_HTML}")

    vocab = build_shared_bpe_dict()

    _SIM_HTML_BUF = SIMULATOR_HTML.read_text(encoding="utf-8")
    try:
        build_stars_dataset()
        build_killer_dataset()
        build_ladder_dataset(vocab)
        build_wordsearch_dataset(vocab)
        build_cryptogram_dataset(vocab)
        build_jumble_dataset(vocab)
        build_wheel_dataset()
        build_towers_dataset()
        build_inequality_dataset()
        build_thermal_fonts()
        SIMULATOR_HTML.write_text(_SIM_HTML_BUF, encoding="utf-8")
        print(f"  -> Wrote buffered simulator dataset updates to {SIMULATOR_HTML}")
    finally:
        _SIM_HTML_BUF = None

    build_game_rules.main(sync_sketch=False)

    print("\nSynchronizing Arduino IDE sketch target...")
    subprocess.check_call([str(SYNC_SCRIPT)])

    print("==================================================================")
    print("ALL CURATED DATASETS SUCCESSFULLY COMPILED & SYNCHRONIZED!")
    print("==================================================================")


if __name__ == "__main__":
    main()

