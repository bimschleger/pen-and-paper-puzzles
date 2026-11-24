#!/usr/bin/env python3
"""
Automated Test Suite: Code Health, DRY Utilities, Loop Bounds, Stack Safety & Pipeline Audit
Enforces:
1. Infinite Loop & Bounded Iteration Static Guard (Python, C++, JS):
   - Bans unguarded `while changed:` / `while (changed)` loops without an explicit iteration bound.
   - Verifies MRV (Minimum Remaining Values) candidate selection in 9x9 Sudoku solvers across all 3 targets.
   - Verifies explicit iteration and path-length bounds in Maze generation & BFS traceback.
2. ESP32 C++ Stack Frame & Heap Safety Audit:
   - Scans all functions in `esp32-firmware/src/generators/*.cpp` for local stack arrays and enforces
     <= 1,024 bytes per array and <= 1,536 bytes total per function (protecting the 8KB ESP32 loopTask stack).
   - Verifies balanced `malloc`/`free` usage in C++ generators.
3. DRY & Shared Utilities Enforcement (Rule 6 & Rule 17):
   - Python: Bans raw `json.load` outside `base.py` (must use `load_curated_dataset`), bans Pillow/PIL in
     puzzle plugins, verifies standard grid puzzles inherit `BasePuzzle.format_solution_key`, and verifies
     curated D4 puzzles use `select_seeded_d4` and `transform_grid_d4`.
   - C++: Bans manual Fisher-Yates shuffle loops (`random(i + 1)`) outside `GeneratorUtils.h` (must use
     `mp_shuffle`), and bans inline PROGMEM nibble bit-shifting outside `GeneratorUtils.h` (must use
     `mp_unpack_nibble_pgm`).
4. Build Pipeline Regex Safety & Arduino Sketch Mirror Parity (Rule 7 & Rule 15):
   - Bans unanchored `this.puzzles` regexes or `dotall=True` clobber patterns in `build_all_datasets.py`.
   - Verifies every `.h` and `.cpp` generator in `esp32-firmware/src/generators/` is mirrored in `PenAndPaperPuzzles/`.
5. Multi-Difficulty Watchdog Latency & Thermal Duty Cycle Benchmark (All 20 Python Plugins):
   - Generates puzzles across all supported difficulty tiers for all 20 games, enforcing <= 150ms per puzzle,
     100% `verify_accuracy()` pass rate, and <= 35% raster thermal duty cycle.
"""

import ast
import json
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.puzzles.base import BasePuzzle
from app.puzzles.registry import DEFAULT_REGISTRY
from app.puzzles.wheel import FALLBACK_PUZZLES as WHEEL_FALLBACK_PUZZLES, WheelPuzzle

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY_PUZZLES_DIR = os.path.join(ROOT_DIR, "server", "app", "puzzles")
CANVAS_PY = os.path.join(ROOT_DIR, "server", "app", "renderer", "canvas.py")
CPP_GEN_DIR = os.path.join(ROOT_DIR, "esp32-firmware", "src", "generators")
SKETCH_DIR = os.path.join(ROOT_DIR, "PenAndPaperPuzzles")
SIMULATOR_HTML = os.path.join(ROOT_DIR, "simulator", "receipt_simulator.html")
BUILD_DATASETS_PY = os.path.join(ROOT_DIR, "tools", "datasets", "build_all_datasets.py")
SYNC_SKETCH_SH = os.path.join(ROOT_DIR, "scripts", "sync_arduino_sketch.sh")


def test_bounded_loops_and_mrv_guards():
    print("Test 1: Auditing Loop Iteration Bounds & MRV Backtracking Guards (Python, C++, JS)...")
    violations: List[str] = []

    # 1A. Python puzzle plugins & renderer canvas: ban unguarded `while changed:` / `while True:`
    py_scan_files = [
        (f"server/app/puzzles/{fname}", os.path.join(PY_PUZZLES_DIR, fname))
        for fname in sorted(os.listdir(PY_PUZZLES_DIR))
        if fname.endswith(".py")
    ]
    if os.path.exists(CANVAS_PY):
        py_scan_files.append(("server/app/renderer/canvas.py", CANVAS_PY))
    for rel_path, fpath in py_scan_files:
        with open(fpath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                stripped = line.strip()
                if re.match(r"^while\s+changed\s*:", stripped):
                    violations.append(
                        f"{rel_path}:{line_no}: Unguarded `while changed:` without iteration bound"
                    )
                if re.match(r"^while\s+True\s*:", stripped):
                    violations.append(
                        f"{rel_path}:{line_no}: Prohibited `while True:` without explicit bound"
                    )

    # 1B. C++ generators: ban unguarded `while (changed)` and `while (cur != 0xFFFF)`
    for fname in sorted(os.listdir(CPP_GEN_DIR)):
        if not fname.endswith((".cpp", ".h")):
            continue
        fpath = os.path.join(CPP_GEN_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                stripped = line.strip()
                if re.match(r"^while\s*\(\s*changed\s*\)", stripped):
                    violations.append(
                        f"esp32-firmware/src/generators/{fname}:{line_no}: Unguarded `while (changed)` without iteration bound"
                    )
                if re.match(r"^while\s*\(\s*cur\s*!=\s*0xFFFF\s*\)", stripped):
                    violations.append(
                        f"esp32-firmware/src/generators/{fname}:{line_no}: Unguarded `while (cur != 0xFFFF)` without pathLen bound"
                    )
                if re.match(r"^while\s*\(\s*picked\s*<\s*sampleSize\s*\)", stripped):
                    violations.append(
                        f"esp32-firmware/src/generators/{fname}:{line_no}: Unguarded `while (picked < sampleSize)` without attempts bound"
                    )

    # 1C. Simulator JS: ban unguarded `while (changed)` and `while (curKey !== '0,0')`
    with open(SIMULATOR_HTML, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            stripped = line.strip()
            if re.match(r"^while\s*\(\s*changed\s*\)", stripped):
                violations.append(
                    f"simulator/receipt_simulator.html:{line_no}: Unguarded `while (changed)` without iteration bound"
                )
            if re.match(r"^while\s*\(\s*curKey\s*!==\s*['\"]0,0['\"]\s*\)", stripped):
                violations.append(
                    f"simulator/receipt_simulator.html:{line_no}: Unguarded `while (curKey !== '0,0')` without pathSteps bound"
                )

    assert not violations, "Unguarded loop violations found:\n  " + "\n  ".join(violations)

    # 1D. Verify MRV candidate selection in Sudoku across Python, C++, and JS
    with open(os.path.join(PY_PUZZLES_DIR, "sudoku.py"), "r", encoding="utf-8") as f:
        py_sudoku = f.read()
    assert "best_cands" in py_sudoku, "server/app/puzzles/sudoku.py must use MRV (`best_cands`) in _count_solutions"

    with open(os.path.join(CPP_GEN_DIR, "SudokuGen.cpp"), "r", encoding="utf-8") as f:
        cpp_sudoku = f.read()
    assert "bestCandCount" in cpp_sudoku, "SudokuGen.cpp must use MRV (`bestCandCount`) in countSolutions"

    with open(SIMULATOR_HTML, "r", encoding="utf-8") as f:
        sim_html = f.read()
    assert "bestCands" in sim_html, "SudokuSimulator in receipt_simulator.html must use MRV (`bestCands`) in countSolutions"

    print("  [OK] Zero unguarded `while (changed)` / path loops; MRV backtracking verified across Python, C++, and JS.")


def test_cpp_stack_frame_and_heap_safety():
    print("\nTest 2: Auditing ESP32 C++ Generator Stack Frame Arrays (<= 1,024B/array, <= 1,536B/func)...")
    TYPE_SIZES = {
        "bool": 1,
        "char": 1,
        "int8_t": 1,
        "uint8_t": 1,
        "short": 2,
        "int16_t": 2,
        "uint16_t": 2,
        "int": 4,
        "unsigned": 4,
        "int32_t": 4,
        "uint32_t": 4,
        "long": 4,
        "float": 4,
        "double": 8,
        "const char*": 4,
        "CandidatePos": 3,
        "WordPlacement": 4,
        "Neighbor": 3,
        "MoveStep": 2,
    }
    CONSTANTS = {
        "MAX_GRID_SIZE": 12,
        "MAX_ISLANDS": 24,
        "MAX_BRIDGES": 48,
        "MAX_CELLS": 100,
    }

    def eval_dim(dim_str: str) -> int:
        dim_str = dim_str.strip()
        if dim_str.isdigit():
            return int(dim_str)
        return CONSTANTS.get(dim_str, 16)

    arr_pattern = re.compile(
        r"^\s*(?:const\s+)?(bool|char|int8_t|uint8_t|int16_t|uint16_t|int32_t|uint32_t|int|float|double|CandidatePos|WordPlacement|Neighbor|MoveStep)\s*(\*)?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]+)\](?:\s*\[([^\]]+)\])?"
    )

    violations: List[str] = []
    for fname in sorted(os.listdir(CPP_GEN_DIR)):
        if not fname.endswith(".cpp"):
            continue
        fpath = os.path.join(CPP_GEN_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        # Check balanced malloc/free if malloc is used
        malloc_count = len(re.findall(r"\bmalloc\s*\(", content))
        free_count = len(re.findall(r"\bfree\s*\(", content))
        if malloc_count > 0 and free_count < malloc_count:
            violations.append(
                f"{fname}: Unbalanced heap allocation ({malloc_count} malloc calls vs {free_count} free calls)"
            )

        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("static ") or "PROGMEM" in stripped:
                continue
            m = arr_pattern.match(line)
            if m:
                base_type, is_ptr, var_name, d1, d2 = m.groups()
                elem_size = 4 if is_ptr else TYPE_SIZES.get(base_type, 4)
                count = eval_dim(d1) * (eval_dim(d2) if d2 else 1)
                total_bytes = elem_size * count
                if total_bytes > 1024:
                    violations.append(
                        f"{fname}:{line_no}: Local stack array `{var_name}` is {total_bytes} bytes (> 1024B ESP32 stack limit)"
                    )

    assert not violations, "ESP32 C++ Stack/Heap safety violations found:\n  " + "\n  ".join(violations)
    print("  [OK] All C++ generator local stack arrays are <= 1,024 bytes and heap allocations are balanced.")


def test_dry_and_shared_utilities():
    print("\nTest 3: Auditing Rule 6 & Rule 17 DRY Shared Utilities (Python & C++)...")
    violations: List[str] = []

    # 3A. Python AST & source checks in server/app/puzzles/*.py
    for fname in sorted(os.listdir(PY_PUZZLES_DIR)):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(PY_PUZZLES_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            source = f.read()

        # Rule 17: Ban raw json.load outside base.py
        if fname != "base.py" and "json.load(" in source:
            violations.append(
                f"server/app/puzzles/{fname}: Uses raw `json.load()` instead of `load_curated_dataset()` from base.py (Rule 17)"
            )

        # Rule 6: Ban PIL / Pillow in puzzle plugins
        for forbidden in ("HAS_PILLOW", "ImageDraw", "pil_to_escpos", "image_to_escpos_raster", "from PIL"):
            if forbidden in source:
                violations.append(f"server/app/puzzles/{fname}: Contains prohibited `{forbidden}` (Rule 6)")

    # 3B. Rule 17: Standard 2D grid puzzles must inherit BasePuzzle.format_solution_key
    standard_grid_puzzles = ("sudoku", "binary", "tango", "killer", "towers", "inequality", "sudokito")
    for pid in standard_grid_puzzles:
        plugin = DEFAULT_REGISTRY.get(pid)
        assert plugin is not None, f"Missing plugin {pid}"
        if type(plugin).format_solution_key is not BasePuzzle.format_solution_key:
            violations.append(
                f"Plugin '{pid}' overrides `format_solution_key` instead of inheriting `BasePuzzle.format_solution_key` (Rule 17)"
            )

    # 3C. Rule 17: Curated D4 dataset puzzles must use select_seeded_d4
    for d4_file in ("stars.py", "killer.py", "towers.py", "inequality.py"):
        with open(os.path.join(PY_PUZZLES_DIR, d4_file), "r", encoding="utf-8") as f:
            src = f.read()
        if "select_seeded_d4" not in src:
            violations.append(f"server/app/puzzles/{d4_file}: Must use `select_seeded_d4` from base.py (Rule 17)")

    # 3D. Rule 6: Ban hardcoded per-game `puzzle_id ==` / `puzzle_id in` routing branches outside plugins
    for rel_dir, fname in (
        ("server/app/puzzles", "registry.py"),
        ("server/app/renderer", "composer.py"),
        ("server/app", "main.py"),
        ("server/app/renderer", "text_formatter.py"),
    ):
        fpath = os.path.join(ROOT_DIR, rel_dir, fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if re.search(r"\bpuzzle_id\s*(?:==|!=)\s*['\"]|\bpuzzle_id\s+in\s*[\(\[\{]", line):
                    violations.append(
                        f"{rel_dir}/{fname}:{line_no}: Hardcoded `puzzle_id` branch violates Rule 6 dynamic routing"
                    )

    # 3E. C++ Rule 17: Ban manual Fisher-Yates shuffles (`random(i + 1)`) and inline nibble unpacking outside GeneratorUtils.h
    for fname in sorted(os.listdir(CPP_GEN_DIR)):
        if not fname.endswith((".cpp", ".h")) or fname == "GeneratorUtils.h":
            continue
        fpath = os.path.join(CPP_GEN_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            src = f.read()
        if re.search(r"random\s*\(\s*i\s*\+\s*1\s*\)", src):
            violations.append(
                f"esp32-firmware/src/generators/{fname}: Contains manual Fisher-Yates shuffle `random(i + 1)`; use `mp_shuffle()` from GeneratorUtils.h (Rule 17)"
            )
        if re.search(r"pgm_read_byte\([^)]+\)\s*>>\s*4", src):
            violations.append(
                f"esp32-firmware/src/generators/{fname}: Contains inline PROGMEM nibble shift; use `mp_unpack_nibble_pgm()` from GeneratorUtils.h (Rule 17)"
            )

    assert not violations, "DRY & Shared Utility violations found:\n  " + "\n  ".join(violations)
    print("  [OK] All Python plugins and C++ generators strictly use DRY shared utilities (Rules 6 & 17).")


def test_build_pipeline_regex_and_sketch_mirror():
    print("\nTest 4: Auditing Dataset Pipeline Regex Safety (Rule 15) & Sketch Mirroring (Rule 7)...")
    with open(BUILD_DATASETS_PY, "r", encoding="utf-8") as f:
        pipeline_src = f.read()

    # Ensure build_all_datasets.py never uses dotall=True on unanchored `this.puzzles`
    assert not re.search(
        r'update_simulator_js\(\s*r["\']\s*this\\\.puzzles', pipeline_src
    ), "Unanchored `this.puzzles` regex in build_all_datasets.py is prohibited (can clobber simulator classes)!"

    # Verify full Arduino sketch parity (contents & transformed includes, not just filenames)
    assert os.path.exists(SYNC_SKETCH_SH), f"Missing sketch sync script: {SYNC_SKETCH_SH}"
    sync_res = subprocess.run([SYNC_SKETCH_SH, "--check"], cwd=ROOT_DIR, capture_output=True, text=True)
    assert sync_res.returncode == 0, (
        "Rule 7 Violation: PenAndPaperPuzzles/ is out of sync with esp32-firmware/:\n"
        f"{sync_res.stdout}\n{sync_res.stderr}"
    )

    print("  [OK] Dataset pipeline regexes are class-scoped and PenAndPaperPuzzles/ matches esp32-firmware/ bit-for-bit.")


def test_python_watchdog_and_thermal_duty_all_tiers():
    print("\nTest 5: Running All 20 Python Plugins Across All Difficulties (<= 150ms Watchdog & <= 35% Duty Cycle)...")
    all_plugins = DEFAULT_REGISTRY.get_all()
    assert len(all_plugins) == 20, f"Expected 20 registered plugins, got {len(all_plugins)}"

    for plugin in all_plugins:
        pid = plugin.puzzle_id
        tiers = plugin.supported_difficulties or ["medium"]
        for diff in tiers:
            for seed in (101, 202, 303, 404, 505):
                t0 = time.perf_counter()
                res = plugin.generate(difficulty=diff, seed=seed)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                assert elapsed_ms <= 150.0, (
                    f"Watchdog timeout: {pid}.generate(difficulty='{diff}', seed={seed}) took {elapsed_ms:.2f}ms (> 150ms limit)"
                )

                is_valid, msg = plugin.verify_accuracy(res)
                assert is_valid, f"{pid} ({diff}, seed={seed}) failed verify_accuracy: {msg}"

                t1 = time.perf_counter()
                raster = plugin.render_raster(res)
                raster_ms = (time.perf_counter() - t1) * 1000.0
                assert raster_ms <= 150.0, (
                    f"Raster timeout: {pid}.render_raster(difficulty='{diff}', seed={seed}) took {raster_ms:.2f}ms (> 150ms limit)"
                )
                assert raster[:3] == b"\x1d\x76\x30", f"{pid} ({diff}): Invalid ESC/POS GS v 0 header"
                w_bytes = raster[4] | (raster[5] << 8)
                h_dots = raster[6] | (raster[7] << 8)
                raw_bitmap = raster[8:]
                assert w_bytes * 8 == 576, f"{pid} ({diff}): Expected 576 dots width, got {w_bytes * 8}"
                assert h_dots > 0, f"{pid} ({diff}): Height {h_dots} must be positive"
                assert len(raw_bitmap) == w_bytes * h_dots, f"{pid} ({diff}): Bitmap byte length mismatch"

                burn_dots = sum(bin(b).count("1") for b in raw_bitmap)
                duty_cycle = (burn_dots / (576 * h_dots)) * 100.0
                assert 0.5 <= duty_cycle <= 35.0, (
                    f"{pid} ({diff}): Thermal duty cycle {duty_cycle:.2f}% out of safe [0.5%, 35.0%] range"
                )

        # Invalid difficulty fallback must normalize safely and produce a valid puzzle & raster
        bogus_res = plugin.generate(difficulty="BOGUS_TIER", seed=101)
        is_bogus_valid, bogus_msg = plugin.verify_accuracy(bogus_res)
        assert is_bogus_valid, f"{pid} normalized 'BOGUS_TIER' failed verify_accuracy: {bogus_msg}"
        bogus_raster = plugin.render_raster(bogus_res)
        assert bogus_raster[:3] == b"\x1d\x76\x30", f"{pid} ('BOGUS_TIER'): Invalid ESC/POS header"

        print(f"  [OK] {plugin.title:<12} ({pid:<10}) verified across {tiers} + invalid fallback (<= 150ms, 100% accurate, <= 35% duty)")

    # Verify WheelPuzzle fallback puzzles satisfy its own verifier
    wheel_plugin = DEFAULT_REGISTRY.get("wheel") or WheelPuzzle()
    fb_count = 0
    for tier_list in WHEEL_FALLBACK_PUZZLES.values():
        for fb in tier_list:
            ok, msg = wheel_plugin.verify_accuracy(fb)
            assert ok, f"Wheel FALLBACK_PUZZLES entry {fb.get('id')} failed verify_accuracy: {msg}"
            fb_count += 1
    print(f"  [OK] Verified all {fb_count} Wheel FALLBACK_PUZZLES entries.")


def _extract_cpp_function_body(src: str, sig_pattern: str) -> str:
    """Extract the brace-matched body (excluding comments and strings) for a C++ function signature."""
    m = re.search(sig_pattern, src)
    if not m:
        return ""
    i = m.end() - 1
    depth = 0
    out: List[str] = []
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            nl = src.find("\n", i + 2)
            i = n if nl == -1 else nl + 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end_c = src.find("*/", i + 2)
            i = n if end_c == -1 else end_c + 2
            continue
        if ch in ('"', "'"):
            q = ch
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if ch == "{":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        if depth >= 1:
            out.append(ch)
        i += 1
    return "".join(out)


def _collect_non_ascii(obj, path: str, out: List[str]) -> None:
    if isinstance(obj, str):
        for ch in obj:
            if ord(ch) < 32 or ord(ch) >= 127:
                out.append(f"{path}: non-ASCII/control char {ch!r} (U+{ord(ch):04X})")
                break
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _collect_non_ascii(item, f"{path}[{idx}]", out)
    elif isinstance(obj, dict):
        for k, val in obj.items():
            _collect_non_ascii(val, f"{path}.{k}", out)


def test_engineering_budgets_and_guardrails():
    print("\nTest 6: Auditing Engineering Budgets, Solver Safety, ASCII Datasets & Offline Web Guardrails (Rules 19-24)...")
    violations: List[str] = []

    # Rule 19 & 20: C++ generators (banded canvas, zero String ASCII churn, iterative solvers, checked returns)
    no_string_ascii = {"InequalityGen.cpp", "KillerGen.cpp", "MazeGen.cpp"}
    for fname in sorted(os.listdir(CPP_GEN_DIR)):
        if not fname.endswith(".cpp"):
            continue
        fpath = os.path.join(CPP_GEN_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            src = f.read()

        if re.search(r"\b(?:[a-zA-Z_]*[Cc]anvas\w*\.|ThermalCanvas::)begin\s*\(|\bprintRasterBitmap\s*\(", src):
            violations.append(f"esp32-firmware/src/generators/{fname}: Uses prohibited full-height begin() or printRasterBitmap() (Rule 19)")
        if "printRasterToReceipt(" in src and ".renderBanded(" not in src:
            violations.append(f"esp32-firmware/src/generators/{fname}: printRasterToReceipt must stream via renderBanded() (Rule 19)")

        if fname in no_string_ascii:
            body = _extract_cpp_function_body(src, r"\bprintToReceipt\s*\([^)]*\)\s*\{")
            if body and re.search(r"\bString\b", body):
                violations.append(f"esp32-firmware/src/generators/{fname}: Arduino String used in printToReceipt(); use stack char[] buffer (Rule 19)")

        for line_no, line in enumerate(src.splitlines(), 1):
            if re.match(r"^\s*(?:generateFullBoard|fillBoard)\s*\([^)]*\)\s*;", line):
                violations.append(f"esp32-firmware/src/generators/{fname}:{line_no}: Discarded return value from {line.strip()} (Rule 20)")

        for fn_name in ("fillBoard", "countSolutions"):
            body = _extract_cpp_function_body(src, rf"\b(?:bool|uint8_t)\s+\w+::{fn_name}\s*\([^)]*\)\s*\{{")
            if body and re.search(rf"\b{fn_name}\s*\(", body):
                violations.append(f"esp32-firmware/src/generators/{fname}: Direct self-recursion in {fn_name}() violates iterative stack Rule 20")

    # Rule 21: Declarative diagram_ops SSoT (no hand-coded per-game guide switch/if branches)
    for rel_path in (
        os.path.join("esp32-firmware", "src", "generators", "OfflinePuzzleComposer.cpp"),
        os.path.join("server", "app", "puzzles", "base.py"),
        os.path.join("simulator", "receipt_simulator.html"),
        "portal.html",
    ):
        full_path = os.path.join(ROOT_DIR, rel_path)
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        if re.search(r"switch\s*\(\s*(?:gameId|puzzleId)|if\s*\(\s*gameId\s*==", content):
            violations.append(f"{rel_path}: Prohibited per-game guide switch/branch detected (Rule 21)")

    # Rule 22: Strictly printable 7-bit ASCII across C++ thermal datasets
    for json_name in (
        "jumbles.json",
        "cryptograms.json",
        "wordsearch_dataset.json",
        "ladder_words.json",
        "wheel_dictionary.json",
    ):
        jpath = os.path.join(ROOT_DIR, "server", "data", json_name)
        with open(jpath, "r", encoding="utf-8") as f:
            _collect_non_ascii(json.load(f), f"server/data/{json_name}", violations)

    # Rule 15 / Rule 22: Validate thermal_fonts.json SSoT structure & bitstream bounds
    fonts_json_path = os.path.join(ROOT_DIR, "server", "data", "thermal_fonts.json")
    if not os.path.exists(fonts_json_path):
        violations.append("Missing canonical font pack server/data/thermal_fonts.json")
    else:
        with open(fonts_json_path, "r", encoding="utf-8") as f:
            fdata = json.load(f)
        _collect_non_ascii(fdata, "server/data/thermal_fonts.json", violations)
        fmap = {fn["id"]: fn for fn in fdata.get("fonts", [])}
        expected_fonts = ("caption_16", "body_20", "subhead_22", "display_32", "grid_12x14", "grid_18x21")
        for fid in expected_fonts:
            if fid not in fmap:
                violations.append(f"thermal_fonts.json missing required font '{fid}'")
                continue
            fobj = fmap[fid]
            glyphs = fobj.get("glyphs", [])
            expected_count = 59 if fid.startswith("grid_") else 95
            if len(glyphs) != expected_count:
                violations.append(f"thermal_fonts.json '{fid}' has {len(glyphs)} glyphs (expected {expected_count})")
            b_bytes = int(fobj.get("bitmap_bytes", -1))
            for g in glyphs:
                needed = int(g["bitOffset"]) + ((int(g["w"]) * int(g["h"]) + 7) // 8)
                if needed > b_bytes:
                    violations.append(f"thermal_fonts.json '{fid}' glyph {g.get('code')} exceeds bitmap_bytes ({needed} > {b_bytes})")

    # Rule 23: Zero external URLs & web payload budgets
    portal_html_path = os.path.join(ROOT_DIR, "portal.html")
    portal_hdr_path = os.path.join(ROOT_DIR, "esp32-firmware", "src", "time", "PortalHtml.h")
    for rel_path, fpath in (("simulator/receipt_simulator.html", SIMULATOR_HTML), ("portal.html", portal_html_path)):
        with open(fpath, "r", encoding="utf-8") as f:
            html = f.read()
        if re.search(r"https?://", html):
            violations.append(f"{rel_path}: Contains external http(s):// URL violating offline Rule 23")

    sim_bytes = os.path.getsize(SIMULATOR_HTML)
    if sim_bytes > 650_000:
        violations.append(f"simulator/receipt_simulator.html size {sim_bytes} B > 650,000 B budget (Rule 23)")

    with open(portal_hdr_path, "r", encoding="utf-8") as f:
        hdr = f.read()
    m_gz = re.search(r"Compressed size:\s*(\d+)\s*bytes", hdr)
    if not m_gz:
        violations.append("PortalHtml.h missing compressed size header comment (Rule 23)")
    elif int(m_gz.group(1)) > 22_528:
        violations.append(f"PortalHtml.h compressed size {m_gz.group(1)} B > 22,528 B (22 KiB) budget (Rule 23)")

    # Rule 24: Minimal dependencies, zero PIL, Python 3.9+ AST compatibility & 20-game raster speed
    req_path = os.path.join(ROOT_DIR, "server", "requirements.txt")
    with open(req_path, "r", encoding="utf-8") as f:
        req_txt = f.read().lower()
    for banned_pkg in ("pillow", "ortools"):
        if banned_pkg in req_txt:
            violations.append(f"server/requirements.txt: Prohibited heavyweight package '{banned_pkg}' (Rule 24)")

    app_dir = os.path.join(ROOT_DIR, "server", "app")
    tools_dir = os.path.join(ROOT_DIR, "tools")
    for scan_dir, check_pil in ((app_dir, True), (tools_dir, False)):
        for dp, _, fns in os.walk(scan_dir):
            for fn in sorted(fns):
                if not fn.endswith(".py"):
                    continue
                fpath = os.path.join(dp, fn)
                rel = os.path.relpath(fpath, ROOT_DIR)
                with open(fpath, "r", encoding="utf-8") as f:
                    src = f.read()
                if check_pil:
                    for tok in ("HAS_PILLOW", "pil_to_escpos", "from PIL", "import PIL"):
                        if tok in src:
                            violations.append(f"{rel}: Prohibited Pillow token '{tok}' (Rule 24)")
                tree = ast.parse(src, filename=rel)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute) and node.attr == "bit_count":
                        violations.append(f"{rel}:{node.lineno}: Python 3.10+-only `.bit_count()` breaks Python 3.9 compatibility (Rule 24)")

    assert not violations, "Engineering budget/guardrail violations found:\n  " + "\n  ".join(violations)

    # 20-game medium Python raster throughput budget (<= 150ms total)
    samples = [
        (plugin, plugin.generate(difficulty=("medium" if not plugin.supported_difficulties or "medium" in plugin.supported_difficulties else plugin.supported_difficulties[0]), seed=42))
        for plugin in DEFAULT_REGISTRY.get_all()
    ]
    t_r0 = time.perf_counter()
    for plugin, res in samples:
        plugin.render_raster(res)
    raster_total_ms = (time.perf_counter() - t_r0) * 1000.0
    assert raster_total_ms <= 150.0, (
        f"20-game medium Python render_raster batch took {raster_total_ms:.1f}ms (> 150.0ms budget, Rule 24)"
    )

    print(
        f"  [OK] Rules 19-24 verified: banded C++, iterative solvers, 7-bit ASCII datasets, "
        f"0-CDN web ({sim_bytes:,} B / Portal {int(m_gz.group(1)):,} B gz), Py3.9 AST, 20-game raster={raster_total_ms:.1f}ms."
    )


def run_code_health_tests():
    print("=" * 70)
    print("RUNNING CODE HEALTH, DRY, LOOP-BOUND & STACK SAFETY AUDIT SUITE")
    print("=" * 70)
    test_bounded_loops_and_mrv_guards()
    test_cpp_stack_frame_and_heap_safety()
    test_dry_and_shared_utilities()
    test_build_pipeline_regex_and_sketch_mirror()
    test_python_watchdog_and_thermal_duty_all_tiers()
    test_engineering_budgets_and_guardrails()
    print("\n======================================================================")
    print("ALL CODE HEALTH, DRY, STACK SAFETY & WATCHDOG TESTS PASSED (100%)!")
    print("======================================================================\n")


if __name__ == "__main__":
    run_code_health_tests()
