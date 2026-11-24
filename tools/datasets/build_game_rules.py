#!/usr/bin/env python3
"""
Pen and Paper Puzzles - Unified Game Rules & Guide Compiler Pipeline
Reads canonical JSON from server/data/game_rules.json and:
1. Generates esp32-firmware/src/generators/GameRulesDataset.h
2. Generates docs/GAME_RULES_FAQ.md
3. Injects canonical game rules into portal.html and builds PortalHtml.h
4. Injects canonical game rules into simulator/receipt_simulator.html
5. Synchronizes Arduino IDE sketch via scripts/sync_arduino_sketch.sh
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpe_codec  # noqa: E402
from build_portal_header import build_portal_header  # noqa: E402

RULES_JSON_PATH = ROOT_DIR / "server" / "data" / "game_rules.json"
GAME_RULES_H_PATH = ROOT_DIR / "esp32-firmware" / "src" / "generators" / "GameRulesDataset.h"
DOCS_MD_PATH = ROOT_DIR / "docs" / "GAME_RULES_FAQ.md"
PORTAL_HTML_PATH = ROOT_DIR / "portal.html"
SIMULATOR_HTML_PATH = ROOT_DIR / "simulator" / "receipt_simulator.html"
SYNC_SCRIPT = ROOT_DIR / "scripts" / "sync_arduino_sketch.sh"

OP_CODE_ENUM = {
    "grid": "GOP_GRID",
    "rect": "GOP_RECT",
    "frect": "GOP_FRECT",
    "hatch": "GOP_HATCH",
    "hline": "GOP_HLINE",
    "vline": "GOP_VLINE",
    "dhline": "GOP_DHLINE",
    "line": "GOP_LINE",
    "circ": "GOP_CIRC",
    "text": "GOP_TEXT",
}


def escape_cpp_string(s: str) -> str:
    """Escapes quotes and backslashes for C++ string literals."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def compact_games_for_html(games: list) -> list:
    """Strips legacy ASCII move grid/highlight bloat while keeping captions and diagram_ops."""
    compacted = []
    for g in games:
        gc = {k: v for k, v in g.items() if k not in ("valid_move", "invalid_move")}
        gc["valid_move"] = {"caption": g.get("valid_move", {}).get("caption", "")}
        gc["invalid_move"] = {"caption": g.get("invalid_move", {}).get("caption", "")}
        compacted.append(gc)
    return compacted


def _encode_guide_op(op_item: list, blob: bpe_codec.BpeBlobBuilder) -> str:
    panel = int(op_item[0])
    kind = op_item[1]
    enum_name = OP_CODE_ENUM[kind]
    if kind == "text":
        # [panel, "text", dx, y, scale, "STR"]
        a, b, c = int(op_item[2]), int(op_item[3]), int(op_item[4])
        txt_off = blob.add(bpe_codec.to_thermal_ascii(str(op_item[5])))
        return f"{{ {txt_off}, {a}, {b}, {c}, 0, 0, {panel}, {enum_name} }}"
    ints = [int(v) for v in op_item[2:]]
    while len(ints) < 5:
        ints.append(0)
    return f"{{ 0xFFFF, {ints[0]}, {ints[1]}, {ints[2]}, {ints[3]}, {ints[4]}, {panel}, {enum_name} }}"


def generate_cpp_header(data: dict) -> None:
    print(f"Generating C++ GameRulesDataset.h -> {GAME_RULES_H_PATH}...")
    games = data.get("games", [])
    vocab = bpe_codec.load_bpe_dict()
    blob = bpe_codec.BpeBlobBuilder(vocab)

    flat_ops = []
    op_spans = []
    for g in games:
        ops = g.get("diagram_ops", [])
        op_spans.append((len(flat_ops), len(ops)))
        for item in ops:
            flat_ops.append(_encode_guide_op(item, blob))

    rule_entries = []
    for g, (ops_off, ops_cnt) in zip(games, op_spans):
        rules_raw = g.get("rules", [])[:4]
        rule_count = len(rules_raw)
        rules_offs = [str(blob.add(bpe_codec.to_thermal_ascii(r))) for r in rules_raw]
        while len(rules_offs) < 4:
            rules_offs.append("0xFFFF")

        anchors_raw = g.get("opening_anchors", [])[:2]
        anchor_count = len(anchors_raw)
        anchors_offs = [str(blob.add(bpe_codec.to_thermal_ascii(a))) for a in anchors_raw]
        while len(anchors_offs) < 2:
            anchors_offs.append("0xFFFF")

        faqs = g.get("faq", [])[:2]
        faq_count = len(faqs)
        faq_offs = []
        for item in faqs:
            q_off = blob.add(bpe_codec.to_thermal_ascii(item.get("q", "")))
            a_off = blob.add(bpe_codec.to_thermal_ascii(item.get("a", "")))
            faq_offs.append(f"{{{q_off}, {a_off}}}")
        while len(faq_offs) < 2:
            faq_offs.append("{0xFFFF, 0xFFFF}")

        key_off = blob.add(bpe_codec.to_thermal_ascii(g["key"]))
        title_off = blob.add(bpe_codec.to_thermal_ascii(g["title"]))
        instr_off = blob.add(bpe_codec.to_thermal_ascii(g["instruction"]))
        obj_off = blob.add(bpe_codec.to_thermal_ascii(g["objective"]))
        val_off = blob.add(bpe_codec.to_thermal_ascii(g.get("valid_move", {}).get("caption", "")))
        inv_off = blob.add(bpe_codec.to_thermal_ascii(g.get("invalid_move", {}).get("caption", "")))

        rule_entries.extend([
            "    {",
            f'        {g["id"]},',
            f"        {key_off},",
            f"        {title_off},",
            f"        {instr_off},",
            f"        {obj_off},",
            f'        {{ {", ".join(rules_offs)} }},',
            f"        {rule_count},",
            f"        {val_off},",
            f"        {inv_off},",
            f'        {{ {", ".join(anchors_offs)} }},',
            f"        {anchor_count},",
            f'        {{ {", ".join(faq_offs)} }},',
            f"        {faq_count},",
            f"        {ops_off},",
            f"        {ops_cnt}",
            "    },",
        ])

    lines = [
        "// Automatically generated from server/data/game_rules.json by tools/datasets/build_game_rules.py",
        "// Do not edit directly!",
        "#ifndef GAME_RULES_DATASET_H",
        "#define GAME_RULES_DATASET_H",
        "",
        "#include <Arduino.h>",
        '#include "BpeTextDict.h"',
        "",
        "enum GuideOpCode : uint8_t {",
        "    GOP_GRID = 0,",
        "    GOP_RECT = 1,",
        "    GOP_FRECT = 2,",
        "    GOP_HATCH = 3,",
        "    GOP_HLINE = 4,",
        "    GOP_VLINE = 5,",
        "    GOP_DHLINE = 6,",
        "    GOP_LINE = 7,",
        "    GOP_CIRC = 8,",
        "    GOP_TEXT = 9",
        "};",
        "",
        "struct GuideOp {",
        "    uint16_t textOff;",
        "    int16_t a, b, c, d, e;",
        "    uint8_t panel;",
        "    uint8_t op;",
        "};",
        "",
        "struct GameFaqItem {",
        "    uint16_t questionOff;",
        "    uint16_t answerOff;",
        "};",
        "",
        "struct GameRuleDef {",
        "    uint8_t id;",
        "    uint16_t keyOff;",
        "    uint16_t titleOff;",
        "    uint16_t instructionOff;",
        "    uint16_t objectiveOff;",
        "    uint16_t rulesOff[4];",
        "    uint8_t ruleCount;",
        "    uint16_t validCaptionOff;",
        "    uint16_t invalidCaptionOff;",
        "    uint16_t openingAnchorsOff[2];",
        "    uint8_t anchorCount;",
        "    GameFaqItem faq[2];",
        "    uint8_t faqCount;",
        "    uint16_t opsOffset;",
        "    uint8_t opsCount;",
        "};",
        "",
    ]
    lines.extend(blob.format_c_array("GAME_RULES_STRINGS"))
    lines.extend([
        "",
        f"static const size_t TOTAL_GUIDE_OPS = {len(flat_ops)};",
        "static const GuideOp GUIDE_OPS_TABLE[TOTAL_GUIDE_OPS] PROGMEM = {",
    ])
    for i, op_line in enumerate(flat_ops):
        comma = "," if i + 1 < len(flat_ops) else ""
        lines.append(f"    {op_line}{comma}")
    lines.extend([
        "};",
        "",
        f"static const size_t TOTAL_GAME_RULES = {len(games)};",
        "static const GameRuleDef GAME_RULES[TOTAL_GAME_RULES] PROGMEM = {",
    ])
    lines.extend(rule_entries)

    lines.append("};")
    lines.append("")
    lines.append("inline const GameRuleDef* getGameRuleDefById(uint8_t id) {")
    lines.append("    for (size_t i = 0; i < TOTAL_GAME_RULES; i++) {")
    lines.append("        if (pgm_read_byte(&(GAME_RULES[i].id)) == id) {")
    lines.append("            return &GAME_RULES[i];")
    lines.append("        }")
    lines.append("    }")
    lines.append("    return nullptr;")
    lines.append("}")
    lines.append("")
    lines.append("#endif // GAME_RULES_DATASET_H")
    lines.append("")

    GAME_RULES_H_PATH.parent.mkdir(parents=True, exist_ok=True)
    GAME_RULES_H_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Successfully wrote {GAME_RULES_H_PATH}")


def generate_markdown_docs(data: dict) -> None:
    print(f"Generating Markdown Docs -> {DOCS_MD_PATH}...")
    games = data.get("games", [])
    lines = [
        "# Pen and Paper Puzzles: Comprehensive Game Rules & How-to-Play Guide",
        "",
        f"This authoritative guide contains complete rules, core objectives, opening deduction anchors, and visual move specifications for all {len(games)} games in Pen and Paper Puzzles.",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
    ]
    for g in games:
        lines.append(f"- [{g['title']}](#{g['key']}) - {g['instruction']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for g in games:
        lines.append(f"<a name=\"{g['key']}\"></a>")
        lines.append(f"## --- {g['title']} ---")
        lines.append("")
        lines.append(f"> **Instruction**: `{g['instruction']}`")
        lines.append("")
        lines.append(f"**Objective**: {g['objective']}")
        lines.append("")
        lines.append("### Rules of Play")
        for r in g.get("rules", []):
            lines.append(f"- {r}")
        lines.append("")

        lines.append("### Move Examples")
        lines.append("")
        lines.append(f"**Valid Move**: {g.get('valid_move', {}).get('caption', '')}")
        v_grid = g.get('valid_move', {}).get('grid', [])
        if v_grid:
            lines.append("```text")
            for row in v_grid:
                lines.append("  " + " ".join(row))
            lines.append("```")
        lines.append("")

        lines.append(f"**Invalid Move**: {g.get('invalid_move', {}).get('caption', '')}")
        iv_grid = g.get('invalid_move', {}).get('grid', [])
        if iv_grid:
            lines.append("```text")
            for row in iv_grid:
                lines.append("  " + " ".join(row))
            lines.append("```")
        lines.append("")

        lines.append("### Where to Start (First Deductions)")
        for a in g.get("opening_anchors", []):
            lines.append(f"- **Tip**: {a}")
        lines.append("")

        lines.append("### Frequently Asked Questions")
        for item in g.get("faq", []):
            lines.append(f"- **Q: {item['q']}**")
            lines.append(f"  *A: {item['a']}*")
        lines.append("")
        lines.append("---")
        lines.append("")

    DOCS_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Successfully wrote {DOCS_MD_PATH}")


def inject_portal_html(data: dict) -> None:
    if not PORTAL_HTML_PATH.exists():
        raise FileNotFoundError(f"portal.html not found at {PORTAL_HTML_PATH}")

    content = PORTAL_HTML_PATH.read_text(encoding="utf-8")
    games_json = json.dumps(compact_games_for_html(data.get("games", [])), separators=(",", ":"))
    start_tag = "/* [[START_GAME_RULES_DATA]] */"
    end_tag = "/* [[END_GAME_RULES_DATA]] */"
    rules_block = f"{start_tag}\nconst GAME_RULES = {games_json};\n{end_tag}"

    if start_tag in content and end_tag in content:
        start_idx = content.find(start_tag)
        end_idx = content.find(end_tag) + len(end_tag)
        content = content[:start_idx] + rules_block + content[end_idx:]
    elif "const GAME_RULES = [" in content:
        start_idx = content.find("const GAME_RULES = [")
        end_marker = "let currentMask ="
        end_idx = content.find(end_marker)
        if end_idx != -1:
            content = content[:start_idx] + rules_block + "\n\n" + content[end_idx:]
    elif "/* [[GAME_RULES_DATA]] */" in content:
        content = content.replace("/* [[GAME_RULES_DATA]] */", rules_block)
    else:
        raise ValueError("Missing GAME_RULES marker in portal.html")

    PORTAL_HTML_PATH.write_text(content, encoding="utf-8")
    print(f"  Injected canonical GAME_RULES into {PORTAL_HTML_PATH}")


def inject_simulator_html(data: dict) -> None:
    if not SIMULATOR_HTML_PATH.exists():
        print(f"  Simulator HTML not found at {SIMULATOR_HTML_PATH}, skipping.")
        return

    content = SIMULATOR_HTML_PATH.read_text(encoding="utf-8")
    games_json = json.dumps(compact_games_for_html(data.get("games", [])), separators=(",", ":"))
    start_tag = "/* [[START_GAME_RULES_DATA]] */"
    end_tag = "/* [[END_GAME_RULES_DATA]] */"
    rules_block = f"{start_tag}\n    const GAME_RULES = {games_json};\n    {end_tag}"

    if start_tag in content and end_tag in content:
        start_idx = content.find(start_tag)
        end_idx = content.find(end_tag) + len(end_tag)
        content = content[:start_idx] + rules_block + content[end_idx:]
        SIMULATOR_HTML_PATH.write_text(content, encoding="utf-8")
        print(f"  Injected canonical GAME_RULES into {SIMULATOR_HTML_PATH}")
    else:
        raise ValueError("Missing GAME_RULES markers in simulator HTML")


def sync_arduino() -> None:
    if SYNC_SCRIPT.exists() and os.access(SYNC_SCRIPT, os.X_OK):
        print("Running sync_arduino_sketch.sh...")
        res = subprocess.run([str(SYNC_SCRIPT)], capture_output=True, text=True)
        if res.returncode == 0:
            print("  Arduino sketch synchronized successfully.")
        else:
            print(f"  Warning: sync_arduino_sketch.sh returned {res.returncode}: {res.stderr}")


def main(sync_sketch: bool = True) -> None:
    if not RULES_JSON_PATH.exists():
        raise FileNotFoundError(f"Rules JSON not found at {RULES_JSON_PATH}")

    with open(RULES_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    generate_cpp_header(data)
    generate_markdown_docs(data)
    inject_portal_html(data)
    build_portal_header()
    inject_simulator_html(data)
    if sync_sketch:
        sync_arduino()
    print("Game rules compiler pipeline completed successfully!")


if __name__ == "__main__":
    main()

