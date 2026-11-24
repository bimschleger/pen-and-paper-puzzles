#!/usr/bin/env python3
"""
Automated Test Suite: Firmware Parity & C++ Compilation Verification
Validates:
1. Generator Inventory Parity: Checks whether every puzzle in DEFAULT_REGISTRY has a corresponding
   C++ generator (.h and .cpp) in esp32-firmware/src/generators/.
2. Arduino Sketch Synchronization: Verifies that scripts/sync_arduino_sketch.sh leaves zero drift
   between esp32-firmware/ and PenAndPaperPuzzles/.
3. Host C++ Syntax & Build Compilation: Compiles esp32-firmware/test/test_offline_generators.cpp
   using the host C++ compiler (clang++ or g++) to guarantee zero syntax or linkage regressions.
"""

import os
import sys
import re
import shutil
import subprocess
import tempfile
from typing import Dict, List, Tuple

# Add server directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.puzzles.registry import DEFAULT_REGISTRY

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FW_DIR = os.path.join(ROOT_DIR, "esp32-firmware")
SKETCH_DIR = os.path.join(ROOT_DIR, "PenAndPaperPuzzles")
GEN_DIR = os.path.join(FW_DIR, "src", "generators")
TEST_CPP = os.path.join(FW_DIR, "test", "test_offline_generators.cpp")

# Mapping from puzzle_id to expected C++ generator file prefix
GENERATOR_MAP = {
    "sudoku": ("SudokuGen.h", "SudokuGen.cpp"),
    "wordsearch": ("WordSearchGen.h", "WordSearchGen.cpp"),
    "nonogram": ("NonogramGen.h", "NonogramGen.cpp"),
    "queens": ("QueensGen.h", "QueensGen.cpp"),
    "jumble": ("JumbleGen.h", "JumbleGen.cpp"),
    "binary": ("BinaryGen.h", "BinaryGen.cpp"),
    "mines": ("MinesGen.h", "MinesGen.cpp"),
    "tents": ("TentsGen.h", "TentsGen.cpp"),
    "bridges": ("BridgesGen.h", "BridgesGen.cpp"),
    "killer": ("KillerGen.h", "KillerGen.cpp"),
    "cryptogram": ("CryptogramGen.h", "CryptogramGen.cpp"),
    "tango": ("TangoGen.h", "TangoGen.cpp"),
    "ladder": ("LadderGen.h", "LadderGen.cpp"),
    "wheel": ("WheelGen.h", "WheelGen.cpp"),
    "lights": ("LightsGen.h", "LightsGen.cpp"),
    "loop": ("LoopGen.h", "LoopGen.cpp"),
    "towers": ("TowersGen.h", "TowersGen.cpp"),
    "inequality": ("InequalityGen.h", "InequalityGen.cpp"),
    "maze": ("MazeGen.h", "MazeGen.cpp"),
    "sudokito": ("SudokitoGen.h", "SudokitoGen.cpp"),
}


def test_generator_parity(strict: bool = True) -> Tuple[List[str], List[str]]:
    print("Test 1: Verifying Python <-> ESP32 C++ Generator Inventory Parity...")
    all_plugins = DEFAULT_REGISTRY.get_all()

    present: List[str] = []
    missing: List[str] = []

    for plugin in all_plugins:
        pid = plugin.puzzle_id
        title = plugin.title
        h_file, cpp_file = GENERATOR_MAP.get(pid, (f"{title.capitalize()}Gen.h", f"{title.capitalize()}Gen.cpp"))
        h_path = os.path.join(GEN_DIR, h_file)
        cpp_path = os.path.join(GEN_DIR, cpp_file)

        if os.path.exists(h_path) and os.path.exists(cpp_path):
            present.append(f"{title} ({h_file})")
            print(f"  [OK] {title:<12} -> {h_file} & {cpp_file}")
        else:
            missing.append(f"{title} ({pid}: {h_file})")
            print(f"  [MISSING] {title:<12} -> Missing {h_file} / {cpp_file}")

    print(f"\nInventory: {len(present)} present, {len(missing)} missing out of {len(all_plugins)} games.")

    if strict and missing:
        raise AssertionError(f"Strict parity failure: Missing C++ generators for: {', '.join(missing)}")

    return present, missing


def test_arduino_sketch_sync():
    print("\nTest 2: Verifying Arduino Sketch Synchronization Parity (non-mutating --check)...")
    sync_script = os.path.join(ROOT_DIR, "scripts", "sync_arduino_sketch.sh")
    assert os.path.exists(sync_script), f"Missing sync script at {sync_script}"

    # Verify parity without mutating PenAndPaperPuzzles/
    res = subprocess.run(["/bin/bash", sync_script, "--check"], cwd=ROOT_DIR, capture_output=True, text=True)
    assert res.returncode == 0, f"Arduino sketch sync drift detected:\n{res.stderr}\n{res.stdout}"

    # Verify key synced files exist in PenAndPaperPuzzles/
    expected_files = [
        "config.h",
        "EscPosPrinter.h",
        "EscPosPrinter.cpp",
        "ThermalFonts.h",
        "OfflinePuzzleComposer.h",
        "OfflinePuzzleComposer.cpp",
        "PenAndPaperPuzzles.ino",
    ]
    for f in expected_files:
        path = os.path.join(SKETCH_DIR, f)
        assert os.path.exists(path), f"Missing synchronized sketch file: {path}"

    print("  -> Passed! Arduino sketch directory PenAndPaperPuzzles/ is cleanly synchronized.")


def test_host_cpp_compilation():
    print("\nTest 3: Verifying Host C++ Offline Generator Compilation (Prod, Host Test, ESP32-S3)...")
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        print("  -> Skipped: No host C++ compiler (clang++/g++) available in environment.")
        return

    base_flags = [
        compiler,
        "-std=c++17",
        "-I", os.path.join(FW_DIR, "test"),
        "-I", os.path.join(FW_DIR, "include"),
        "-I", os.path.join(FW_DIR, "src"),
    ]
    prod_bin = os.path.join(FW_DIR, "test", "test_runner_parity_prod")
    host_bin = os.path.join(FW_DIR, "test", "test_runner_parity_host")

    try:
        # 1. Production ESP32 profile (no HOST_TEST -> strips SOLUTIONS arrays & host accessors)
        prod_cmd = base_flags + [TEST_CPP, "-o", prod_bin]
        build_prod = subprocess.run(prod_cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        assert build_prod.returncode == 0, (
            f"Production-profile C++ compilation failed for {TEST_CPP}:\n{build_prod.stderr}\n{build_prod.stdout}"
        )
        run_prod = subprocess.run([prod_bin], cwd=ROOT_DIR, capture_output=True, text=True)
        assert run_prod.returncode == 0, (
            f"Execution of production-profile offline generator test failed:\n{run_prod.stderr}\n{run_prod.stdout}"
        )

        # 2. Host test profile (-DHOST_TEST -> enables solution arrays & MazeGen::solvePath)
        host_cmd = base_flags + ["-DHOST_TEST", TEST_CPP, "-o", host_bin]
        build_host = subprocess.run(host_cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        assert build_host.returncode == 0, (
            f"Host-test C++ compilation (-DHOST_TEST) failed for {TEST_CPP}:\n{build_host.stderr}\n{build_host.stdout}"
        )
        run_host = subprocess.run([host_bin], cwd=ROOT_DIR, capture_output=True, text=True)
        assert run_host.returncode == 0, (
            f"Execution of host-test offline generator test failed:\n{run_host.stderr}\n{run_host.stdout}"
        )

        # 3. ESP32-S3 syntax check (-fsyntax-only -DCONFIG_IDF_TARGET_ESP32S3)
        s3_cmd = base_flags + ["-fsyntax-only", "-DCONFIG_IDF_TARGET_ESP32S3", TEST_CPP]
        s3_res = subprocess.run(s3_cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        assert s3_res.returncode == 0, (
            f"ESP32-S3 syntax check failed for {TEST_CPP}:\n{s3_res.stderr}\n{s3_res.stdout}"
        )
        print("  -> Passed! C++ firmware generator suite compiles cleanly across Prod, -DHOST_TEST, and ESP32-S3 syntax profiles.")
    finally:
        for path in (prod_bin, host_bin):
            if os.path.exists(path):
                os.remove(path)


def test_rule_7_flat_includes():
    print("\nTest 4: Verifying Rule 7 (Zero Relative Include Paths in PenAndPaperPuzzles/)...")
    assert os.path.exists(SKETCH_DIR), f"PenAndPaperPuzzles dir not found at {SKETCH_DIR}"

    relative_includes = []
    for root, _, files in os.walk(SKETCH_DIR):
        for f in files:
            if f.endswith((".h", ".cpp", ".ino")):
                fpath = os.path.join(root, f)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    for line_num, line in enumerate(fh, 1):
                        if re.search(r'#include\s*["<]\.\./', line):
                            relative_includes.append(f"{f}:{line_num}: {line.strip()}")

    assert not relative_includes, (
        f"Rule 7 Violation: Found relative include paths in PenAndPaperPuzzles/:\n" + "\n".join(relative_includes)
    )
    print("  -> Passed! Zero relative #include paths found in PenAndPaperPuzzles/ (100% flat includes).")


def test_rule_14_offline_appliance_libraries():
    print("\nTest 5: Verifying Rule 14 (Offline Appliance Standards: No HTTPClient/ArduinoJson)...")
    src_dir = os.path.join(FW_DIR, "src")
    assert os.path.exists(src_dir), f"src dir not found at {src_dir}"

    violations = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith((".h", ".cpp")):
                fpath = os.path.join(root, f)
                rel_path = os.path.relpath(fpath, src_dir)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()

                if "HTTPClient" in content:
                    violations.append(f"{rel_path}: Contains prohibited HTTPClient")
                if "ArduinoJson" in content:
                    violations.append(f"{rel_path}: Contains prohibited ArduinoJson")
                if "WiFiClient" in content and rel_path not in ("printer/EscPosPrinter.h", "printer/EscPosPrinter.cpp"):
                    violations.append(f"{rel_path}: Contains WiFiClient outside printer/EscPosPrinter")

    assert not violations, (
        f"Rule 14 Violation: Prohibited network/cloud client libraries found:\n" + "\n".join(violations)
    )
    print("  -> Passed! Zero occurrences of HTTPClient or ArduinoJson in esp32-firmware/src/.")


def test_softap_portal_parity():
    print("\nTest 6: Verifying SoftAP Captive Portal Parity (PortalHtml.h matches portal.html)...")
    portal_html_path = os.path.join(ROOT_DIR, "portal.html")
    portal_h_path = os.path.join(FW_DIR, "src", "time", "PortalHtml.h")

    assert os.path.exists(portal_html_path), f"portal.html not found at {portal_html_path}"
    assert os.path.exists(portal_h_path), f"PortalHtml.h not found at {portal_h_path}"

    with open(portal_html_path, "rb") as f:
        html_bytes = f.read()

    with open(portal_h_path, "r", encoding="utf-8") as f:
        header_text = f.read()

    # Extract hex bytes from header
    hex_values = re.findall(r"0x([0-9A-Fa-f]{2})", header_text)
    assert hex_values, f"No hex bytes found in {portal_h_path}"
    compressed_bytes = bytes(int(h, 16) for h in hex_values)

    import gzip
    decompressed = gzip.decompress(compressed_bytes)
    assert decompressed == html_bytes, (
        f"PortalHtml.h decompressed content does not match portal.html! Run scripts/build_portal_header.py to synchronize."
    )
    print("  -> Passed! PortalHtml.h accurately reflects compressed portal.html.")


def test_offline_puzzle_enum_ordering_parity():
    print("\nTest 7: Verifying OfflinePuzzleType Enum Ordering Parity with DEFAULT_REGISTRY...")
    config_h_path = os.path.join(FW_DIR, "src", "config", "OfflineConfigManager.h")
    assert os.path.exists(config_h_path), f"OfflineConfigManager.h not found at {config_h_path}"

    with open(config_h_path, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r"enum\s+OfflinePuzzleType\s*:\s*uint8_t\s*\{([^}]+)\};", content)
    assert match, "Could not find enum OfflinePuzzleType in OfflineConfigManager.h"

    raw_items = [item.strip() for item in match.group(1).split(",") if item.strip()]
    enum_names = []
    for item in raw_items:
        # Strip comments and assignments
        name = item.split("//")[0].split("/*")[0].split("=")[0].strip()
        if name and name != "OFFLINE_PUZZLE_TOTAL":
            enum_names.append(name)

    all_plugins = DEFAULT_REGISTRY.get_all()
    assert len(enum_names) == len(all_plugins), (
        f"Enum length mismatch: OfflinePuzzleType has {len(enum_names)} items, "
        f"DEFAULT_REGISTRY has {len(all_plugins)} plugins"
    )

    ENUM_MAP = {
        "PUZZLE_SUDOKU": "sudoku",
        "PUZZLE_WORDSEARCH": "wordsearch",
        "PUZZLE_NONOGRAM": "nonogram",
        "PUZZLE_QUEENS": "queens",
        "PUZZLE_JUMBLE": "jumble",
        "PUZZLE_BINARY": "binary",
        "PUZZLE_MINES": "mines",
        "PUZZLE_TENTS": "tents",
        "PUZZLE_BRIDGES": "bridges",
        "PUZZLE_KILLER": "killer",
        "PUZZLE_CRYPTOGRAM": "cryptogram",
        "PUZZLE_TANGO": "tango",
        "PUZZLE_LADDER": "ladder",
        "PUZZLE_WHEEL": "wheel",
        "PUZZLE_LIGHTS": "lights",
        "PUZZLE_LOOP": "loop",
        "PUZZLE_TOWERS": "towers",
        "PUZZLE_INEQUALITY": "inequality",
        "PUZZLE_MAZE": "maze",
        "PUZZLE_SUDOKITO": "sudokito",
    }

    for i, enum_name in enumerate(enum_names):
        expected_id = ENUM_MAP.get(enum_name)
        actual_id = all_plugins[i].puzzle_id.lower()
        assert expected_id == actual_id, (
            f"Enum parity mismatch at index {i} (bit {i}): "
            f"C++ has '{enum_name}' (maps to '{expected_id}'), but DEFAULT_REGISTRY has '{actual_id}'!"
        )

    print(f"  -> Passed! All {len(enum_names)} enum entries in OfflinePuzzleType match DEFAULT_REGISTRY 1:1.")


def test_rule_19_ram_and_rodata_budgets():
    print("\nTest 8: Verifying Rule 19 ESP32 Band RAM (<= 18,432 B) & Curated .rodata Budgets (<= 38,000 B prod)...")
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        print("  -> Skipped: No host C++ compiler (clang++/g++) available in environment.")
        return

    probe_src = r"""
#include <iostream>
#include "Arduino.h"
#include "printer/EscPosPrinter.h"
#include "printer/ThermalCanvas.h"
#include "printer/ThermalFonts.h"
#include "generators/StarsDataset.h"
#include "generators/KillerDataset.h"
#include "generators/TowersDataset.h"
#include "generators/InequalityDataset.h"
#include "generators/BpeTextDict.h"
#include "generators/JumbleDataset.h"
#include "generators/CryptogramDataset.h"
#include "generators/GameRulesDataset.h"
#include "generators/WordSearchGen.h"
#include "generators/WordSearchDataset.h"
#include "generators/LadderDataset.h"
int main() {
    size_t stars = sizeof(STARS_EASY_REGIONS) + sizeof(STARS_MEDIUM_REGIONS) + sizeof(STARS_HARD_REGIONS) + sizeof(STARS_EXTREME_REGIONS);
#ifdef HOST_TEST
    stars += sizeof(STARS_EASY_SOLUTIONS) + sizeof(STARS_MEDIUM_SOLUTIONS) + sizeof(STARS_HARD_SOLUTIONS) + sizeof(STARS_EXTREME_SOLUTIONS);
#endif
    size_t killer = sizeof(KILLER_EASY_DATASET) + sizeof(KILLER_MEDIUM_DATASET) + sizeof(KILLER_HARD_DATASET) + sizeof(KILLER_EXTREME_DATASET);
    size_t towers = sizeof(TOWERS_EASY_DATASET) + sizeof(TOWERS_MEDIUM_DATASET) + sizeof(TOWERS_HARD_DATASET) + sizeof(TOWERS_EXTREME_DATASET);
    size_t ineq = sizeof(INEQUALITY_EASY_DATASET) + sizeof(INEQUALITY_MEDIUM_DATASET) + sizeof(INEQUALITY_HARD_DATASET) + sizeof(INEQUALITY_EXTREME_DATASET);
    size_t text_rodata = sizeof(MP_BPE_PAIRS)
        + sizeof(JUMBLE_STRINGS) + sizeof(JUMBLE_DATASET)
        + sizeof(CRYPTOGRAM_STRINGS) + sizeof(EASY_CRYPTOGRAMS) + sizeof(MEDIUM_CRYPTOGRAMS) + sizeof(HARD_CRYPTOGRAMS)
        + sizeof(GAME_RULES_STRINGS) + sizeof(GUIDE_OPS_TABLE) + sizeof(GAME_RULES)
        + sizeof(WS_STRINGS) + sizeof(WS_EASY_OFFSETS) + sizeof(WS_MEDIUM_OFFSETS) + sizeof(WS_HARD_OFFSETS)
        + sizeof(LADDER_STRINGS) + sizeof(EASY_LADDERS) + sizeof(MEDIUM_LADDERS) + sizeof(HARD_LADDERS);
    size_t fonts = sizeof(THERMAL_GRID_ASCII_MAP) + sizeof(THERMAL_FONT_DEFS)
        + sizeof(TF_CAPTION_16_BITMAP) + sizeof(TF_CAPTION_16_GLYPHS)
        + sizeof(TF_BODY_20_BITMAP) + sizeof(TF_BODY_20_GLYPHS)
        + sizeof(TF_SUBHEAD_22_BITMAP) + sizeof(TF_SUBHEAD_22_GLYPHS)
        + sizeof(TF_DISPLAY_32_BITMAP) + sizeof(TF_DISPLAY_32_GLYPHS)
        + sizeof(TF_GRID_12X14_BITMAP) + sizeof(TF_GRID_12X14_GLYPHS)
        + sizeof(TF_GRID_18X21_BITMAP) + sizeof(TF_GRID_18X21_GLYPHS);
    std::cout << (ThermalCanvas::BAND_HEIGHT * 72) << " " << (stars + killer + towers + ineq) << " " << fonts << " " << text_rodata << "\n";
    return 0;
}
"""
    base_flags = [
        compiler,
        "-std=c++17",
        "-I", os.path.join(FW_DIR, "test"),
        "-I", os.path.join(FW_DIR, "include"),
        "-I", os.path.join(FW_DIR, "src"),
    ]
    with tempfile.TemporaryDirectory() as td:
        src_path = os.path.join(td, "budget_probe.cpp")
        with open(src_path, "w", encoding="utf-8") as fh:
            fh.write(probe_src)

        results = {}
        for label, extra in (("prod", []), ("host", ["-DHOST_TEST"])):
            exe = os.path.join(td, f"probe_{label}")
            build = subprocess.run(base_flags + extra + [src_path, "-o", exe], cwd=ROOT_DIR, capture_output=True, text=True)
            assert build.returncode == 0, f"Budget probe compilation ({label}) failed:\n{build.stderr}"
            run = subprocess.run([exe], cwd=ROOT_DIR, capture_output=True, text=True)
            assert run.returncode == 0, f"Budget probe execution ({label}) failed:\n{run.stderr}"
            band_bytes, rodata_bytes, fonts_rodata, text_rodata = (int(tok) for tok in run.stdout.strip().split())
            results[label] = (band_bytes, rodata_bytes, fonts_rodata, text_rodata)

    band_bytes, prod_rodata, fonts_rodata, text_rodata = results["prod"]
    _, host_rodata, _, _ = results["host"]
    stripped_savings = host_rodata - prod_rodata

    assert band_bytes <= 18432, f"ThermalCanvas band buffer {band_bytes} B exceeds 18,432 B budget (Rule 19)"
    assert prod_rodata <= 38000, f"Production curated .rodata {prod_rodata} B exceeds 38,000 B budget (Rule 19)"
    assert fonts_rodata <= 22000, f"ThermalFonts.h .rodata {fonts_rodata} B exceeds 22,000 B budget (Rule 19)"
    assert text_rodata <= 68000, f"BPE text datasets .rodata {text_rodata} B exceeds 68,000 B budget (Rule 19)"
    assert stripped_savings >= 15000, (
        f"Expected #ifdef HOST_TEST solution stripping to save >= 15,000 B, got {stripped_savings} B (prod={prod_rodata}, host={host_rodata})"
    )
    print(f"  -> Passed! Band RAM={band_bytes:,} B (<= 18,432 B), Prod .rodata={prod_rodata:,} B (saves {stripped_savings:,} B vs HOST_TEST), Text .rodata={text_rodata:,} B (<= 68,000 B), ThermalFonts={fonts_rodata:,} B (<= 22,000 B).")

    # Verify all 20 generators gate STYLE_ASCII printToReceipt() in STYLE_HYBRID builds
    gen_dir = os.path.join(FW_DIR, "src", "generators")
    for fname in sorted(os.listdir(gen_dir)):
        if fname.endswith("Gen.cpp") or fname.endswith("Gen.h"):
            content = open(os.path.join(gen_dir, fname), encoding="utf-8").read()
            assert "#if (OFFLINE_PRINT_STYLE == STYLE_ASCII) || defined(HOST_TEST)" in content, (
                f"{fname} must gate printToReceipt() behind #if (OFFLINE_PRINT_STYLE == STYLE_ASCII) || defined(HOST_TEST) (Rule 19)"
            )


def run_firmware_tests(strict: bool = True):
    print("=" * 60)
    print("RUNNING TIER 4: Firmware Parity & C++ Compilation Verification")
    print("=" * 60)
    test_generator_parity(strict=strict)
    test_arduino_sketch_sync()
    test_host_cpp_compilation()
    test_rule_7_flat_includes()
    test_rule_14_offline_appliance_libraries()
    test_softap_portal_parity()
    test_offline_puzzle_enum_ordering_parity()
    test_rule_19_ram_and_rodata_budgets()
    print("\n[SUCCESS] Tier 4 Firmware verification completed!\n")


if __name__ == "__main__":
    strict_flag = "--no-strict" not in sys.argv
    run_firmware_tests(strict=strict_flag)
