#!/usr/bin/env python3
"""
Automated Test Suite: On-Device (ESP32 C++) vs Off-Device (Python Server) Visual Consistency Verification

Validates that 1-bit thermal raster generation between:
  1. ESP32 firmware ThermalCanvas (C++ on-device)
  2. Python server ThermalBitmap / Pillow plugins (off-device)
are as visually consistent as possible for physical receipt printing:
  - Exact 576-dot width alignment
  - Identical bounding heights
  - Identical typography, line weights, box sizes, and circle radiuses
  - High pixel fidelity & bitwise similarity (Hamming distance & duty cycles)
"""

import json
import os
import shutil
import subprocess
import sys
from typing import Dict, Any, Tuple

# Add server directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.puzzles.registry import DEFAULT_REGISTRY

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FW_DIR = os.path.join(ROOT_DIR, "esp32-firmware")
RUNNER_CPP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visual_comparator_runner.cpp")


def count_bit_diffs(b1: bytes, b2: bytes) -> int:
    min_len = min(len(b1), len(b2))
    diffs = 0
    for i in range(min_len):
        diffs += bin(b1[i] ^ b2[i]).count("1")
    diffs += abs(len(b1) - len(b2)) * 8
    return diffs


def count_set_bits(b: bytes) -> int:
    return sum(bin(byte_val).count("1") for byte_val in b)


def compile_and_run_runner() -> list:
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        raise RuntimeError("No C++ compiler (clang++ or g++) found on host.")

    bin_path = "/tmp/visual_comparator_runner_bin"
    cmd = [
        compiler,
        "-std=c++17",
        "-DHOST_TEST",
        "-I", os.path.join(FW_DIR, "include"),
        "-I", os.path.join(FW_DIR, "test"),
        RUNNER_CPP,
        "-o", bin_path
    ]
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Compilation of visual comparator runner failed:\n{res.stderr}\n{res.stdout}")

    run_res = subprocess.run([bin_path], cwd=ROOT_DIR, capture_output=True, text=True)
    if run_res.returncode != 0:
        raise RuntimeError(f"Execution of visual comparator runner failed:\n{run_res.stderr}\n{run_res.stdout}")

    lines = [l for l in run_res.stdout.splitlines() if not l.startswith("[PRINTER")]
    json_text = "\n".join(lines)
    start = json_text.find("[")
    end = json_text.rfind("]") + 1
    if start == -1 or end == 0:
        raise RuntimeError(f"No JSON array found in runner output:\n{run_res.stdout}")
    return json.loads(json_text[start:end])


def compare_bitmaps(
    label: str,
    width: int,
    height: int,
    cpp_raw: bytes,
    cand_raw: bytes,
    cand_width: int,
    cand_height: int,
    cand_label: str = "Python",
) -> bool:
    assert cand_width == width, f"{label}: Width mismatch ({cand_label}={cand_width}, C++={width})"
    assert cand_height == height, f"{label}: Height mismatch ({cand_label}={cand_height}, C++={height})"

    total_pixels = width * height
    diff_bits = count_bit_diffs(cand_raw, cpp_raw)
    matching_pixels = total_pixels - diff_bits
    pixel_similarity = (matching_pixels / total_pixels) * 100.0

    cpp_burn = count_set_bits(cpp_raw)
    cand_burn = count_set_bits(cand_raw)
    cpp_duty = (cpp_burn / total_pixels) * 100.0
    cand_duty = (cand_burn / total_pixels) * 100.0

    intersection_burn = 0
    min_len = min(len(cand_raw), len(cpp_raw))
    for i in range(min_len):
        intersection_burn += bin(cand_raw[i] & cpp_raw[i]).count("1")
    union_burn = cpp_burn + cand_burn - intersection_burn
    iou = (intersection_burn / union_burn * 100.0) if union_burn > 0 else 100.0

    print(f"--- {label:<22} ({width}x{height} dots) [{cand_label}] ---")
    print(f"  Pixel Similarity : {pixel_similarity:6.2f}% ({matching_pixels}/{total_pixels} dots match)")
    print(f"  Ink Duty Cycle   : C++={cpp_duty:5.2f}%  |  {cand_label}={cand_duty:5.2f}%  (diff={abs(cpp_duty - cand_duty):.2f}%)")
    print(f"  Ink IoU Overlap  : {iou:6.2f}%")

    if diff_bits != 0 or abs(iou - 100.0) > 1e-6:
        print(
            f"  [FAILURE] Rule 8 parity violation ({cand_label}) for {label}: "
            f"diff_bits={diff_bits}, pixel_similarity={pixel_similarity:.2f}%, IoU={iou:.2f}%"
        )
        return False
    print(f"  -> Visual consistency ({cand_label}): 100.00% BIT-FOR-BIT EXACT MATCH")
    return True


def run_js_batch_comparison(items: list) -> list:
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("Node.js is required for 3-way visual parity verification.")

    sim_html_path = os.path.join(ROOT_DIR, "simulator", "receipt_simulator.html")
    with open(sim_html_path, "r", encoding="utf-8") as fh:
        html_content = fh.read()

    import re
    scripts = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html_content, re.S)
    assert scripts, "Could not locate inline <script> inside receipt_simulator.html"
    sim_js = "\n".join(scripts)

    stripped_items = [{k: v for k, v in item.items() if k != "raster_hex"} for item in items]

    js_harness = r"""
const fs = require('fs');
const vm = require('vm');

const simJs = fs.readFileSync(process.argv[2], 'utf8');
const items = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

function makeCaptureCanvas() {
  const canvas = { width: 0, height: 0, style: {}, _imageData: null, _vectorCalls: [] };
  canvas.getContext = function() {
    return {
      createImageData(w, h) {
        return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) };
      },
      putImageData(imgData, x, y) {
        canvas._imageData = imgData;
      },
      fillText() { canvas._vectorCalls.push('fillText'); },
      strokeRect() { canvas._vectorCalls.push('strokeRect'); },
      fillRect() { canvas._vectorCalls.push('fillRect'); },
      arc() { canvas._vectorCalls.push('arc'); },
    };
  };
  return canvas;
}

const dummyEl = () => ({
  value: '', checked: true, innerHTML: '', innerText: '', textContent: '',
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  appendChild() {}, addEventListener() {}, querySelector() { return dummyEl(); }, querySelectorAll() { return []; },
});

const sandbox = {
  console, Math, Array, Object, String, Number, Boolean, Set, Map, JSON, RegExp, Error,
  Uint8Array, Uint8ClampedArray, Int32Array, Date,
  atob: (b64) => Buffer.from(b64, 'base64').toString('binary'),
  performance: { now: () => Date.now() },
  setTimeout: () => 0, clearTimeout: () => {},
  addEventListener() {},
  window: null,
  document: {
    getElementById() { return dummyEl(); },
    createDocumentFragment() { return { children: [], appendChild() {} }; },
    createElement(tag) { return tag === 'canvas' ? makeCaptureCanvas() : dummyEl(); },
    querySelector() { return dummyEl(); },
    querySelectorAll() { return []; },
  },
  navigator: { clipboard: { writeText: async () => {} } },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(simJs, sandbox);

function imageDataToHex(imgData, width, height) {
  const rowBytes = Math.floor((width + 7) / 8);
  const out = Buffer.alloc(rowBytes * height);
  const rgba = imgData.data;
  for (let y = 0; y < height; y++) {
    for (let xb = 0; xb < rowBytes; xb++) {
      let byteVal = 0;
      for (let bit = 0; bit < 8; bit++) {
        const x = xb * 8 + bit;
        if (x < width) {
          const idx = (y * width + x) * 4;
          if (rgba[idx] < 128) byteVal |= (0x80 >> bit);
        }
      }
      out[y * rowBytes + xb] = byteVal;
    }
  }
  return out.toString('hex');
}

const results = items.map((item) => {
  const canvas = makeCaptureCanvas();
  const p = item.puzzle;
  if (p === 'guide') {
    sandbox.drawSimGuideCanvas(item.game_id, canvas);
  } else if (p === 'chrome') {
    if (item.kind === 'master_header') {
      sandbox.renderSimMasterHeader(canvas, 'PEN + PAPER PUZZLES', 'Enjoy Your Puzzles', 'DAILY 5-PUZZLE MIX');
    } else if (item.kind === 'puzzle_header') {
      sandbox.renderSimPuzzleHeader(canvas, 'SUDOKU', 'MEDIUM', 'Fill every row, column, and 3x3 box with digits 1-9 without repeating.');
    } else if (item.kind === 'divider') {
      sandbox.renderSimDivider(canvas);
    } else if (item.kind === 'master_footer') {
      sandbox.renderSimMasterFooter(canvas, 'Enjoy your day!', false, true);
    }
  } else if (p === 'jumble') {
    sandbox.renderOfflineJumble(canvas, item);
  } else if (p === 'wheel') {
    sandbox.renderOfflineWheel(canvas, {
      center: item.center_letter, outer: item.outer_letters,
      good: item.good, great: item.great, genius: item.genius,
      count4: item.count4 || 0, count5: item.count5 || 0,
      count6: item.count6 || 0, count7plus: item.count7plus || 0,
    });
  } else if (p === 'mines') {
    sandbox.renderOfflineMines(canvas, { puzzle: item.grid, minesCount: item.total_mines });
  } else if (p === 'tents') {
    sandbox.renderOfflineTents(canvas, { size: item.size, puzzle: item.grid, rowClues: item.row_clues, colClues: item.col_clues });
  } else if (p === 'stars') {
    const stars = item.stars_per_unit || (item.size >= 9 ? 2 : 1);
    sandbox.renderOfflineQueens(canvas, { regions: item.regions }, item.size, stars);
  } else if (p === 'wordsearch' || p === 'wordsearch_easy') {
    sandbox.renderOfflineWordSearch(canvas, {
      grid: item.grid, words: item.words,
      rows: item.grid.length, cols: item.grid[0].length,
    });
  } else if (p === 'sudoku') {
    sandbox.renderOfflineSudoku(canvas, { puzzle: item.grid });
  } else if (p === 'sudokito') {
    sandbox.renderOfflineSudokito(canvas, { puzzle: item.grid });
  } else if (p === 'loop') {
    sandbox.renderOfflineLoop(canvas, item);
  } else if (p === 'nonogram') {
    sandbox.renderOfflineNonogram(canvas, { size: item.size, rowClues: item.row_clues, colClues: item.col_clues });
  } else if (p === 'lights') {
    sandbox.renderOfflineLights(canvas, { size: item.size, puzzle: item.grid });
  } else if (p === 'killer') {
    sandbox.renderOfflineKiller(canvas, item);
  } else if (p === 'cryptogram') {
    sandbox.renderOfflineCryptogram(canvas, {
      author: item.author, ciphertext: item.ciphertext,
      clueStr: item.clue_str || '', clues: item.clues || [],
    });
  } else if (p === 'ladder') {
    sandbox.renderOfflineLadder(canvas, {
      start: item.start_word, target: item.target_word,
      wordLen: item.word_len, totalWords: item.total_words, solution: item.solution,
    });
  } else if (p === 'binary') {
    sandbox.renderOfflineBinary(canvas, { size: item.size, puzzle: item.grid });
  } else if (p === 'bridges') {
    sandbox.renderOfflineBridges(canvas, item);
  } else if (p === 'tango') {
    sandbox.renderOfflineTango(canvas, {
      size: item.size, puzzle: item.grid, edges_h: item.edges_h, edges_v: item.edges_v,
    });
  } else if (p === 'towers') {
    sandbox.renderOfflineTowers(canvas, item);
  } else if (p === 'inequality') {
    sandbox.renderOfflineInequality(canvas, item);
  } else if (p === 'maze') {
    const wt = item.wall_thickness || (item.size >= 30 ? 2 : (item.size === 10 ? 4 : 3));
    const cs = item.cell_size || Math.floor(480 / item.size);
    sandbox.renderOfflineMaze(canvas, {
      size: item.size, walls_h: item.walls_h, walls_v: item.walls_v,
      cellSize: cs, wallThickness: wt,
    });
  } else {
    throw new Error('Unhandled puzzle type in JS parity harness: ' + p);
  }

  return {
    width: canvas.width,
    height: canvas.height,
    vectorCalls: canvas._vectorCalls,
    hex: canvas._imageData ? imageDataToHex(canvas._imageData, canvas.width, canvas.height) : '',
  };
});

process.stdout.write(JSON.stringify(results));
"""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf_js, \
         tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf_harness, \
         tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf_data:
        tf_js.write(sim_js)
        tf_harness.write(js_harness)
        json.dump(stripped_items, tf_data)
        p_js, p_harness, p_data = tf_js.name, tf_harness.name, tf_data.name

    try:
        res = subprocess.run([node_bin, p_harness, p_js, p_data], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"JS parity harness failed:\n{res.stderr}\n{res.stdout}")
        return json.loads(res.stdout)
    finally:
        for fp in (p_js, p_harness, p_data):
            if os.path.exists(fp):
                os.remove(fp)


def test_visual_consistency():
    print("=" * 70)
    print("RUNNING 3-WAY VISUAL CONSISTENCY SUITE: C++ VS PYTHON VS WEB SIMULATOR")
    print("=" * 70)

    items = compile_and_run_runner()
    print(f"Loaded {len(items)} cases from C++ ThermalCanvas runner.\n")
    js_results = run_js_batch_comparison(items)
    assert len(js_results) == len(items), f"JS count {len(js_results)} != C++ count {len(items)}"

    GUIDE_KEY_TO_PLUGIN = {"search": "wordsearch", "stars": "queens"}
    covered_boards = set()
    covered_guides = set()
    overall_pass = True

    for idx, item in enumerate(items):
        p_name = item["puzzle"]
        diff_tag = item.get("difficulty") or item.get("key") or item.get("kind") or ""
        label = f"{p_name}:{diff_tag}" if diff_tag else p_name
        width = item["width"]
        height = item["height"]
        cpp_raw = bytes.fromhex(item["raster_hex"])

        if p_name == "guide":
            plugin_id = GUIDE_KEY_TO_PLUGIN.get(item["key"], item["key"])
            plugin = DEFAULT_REGISTRY.get(plugin_id)
            assert plugin is not None, f"Plugin {plugin_id} not found in registry"
            covered_guides.add(plugin_id)
            py_escpos = plugin.render_guide_raster(576)
        elif p_name == "chrome":
            from app.renderer.canvas import (
                render_master_header_raster,
                render_puzzle_header_raster,
                render_divider_raster,
                render_master_footer_raster,
            )
            kind = item["kind"]
            if kind == "master_header":
                py_escpos = render_master_header_raster("PEN + PAPER PUZZLES", "Enjoy Your Puzzles", "DAILY 5-PUZZLE MIX")
            elif kind == "puzzle_header":
                py_escpos = render_puzzle_header_raster("SUDOKU", "MEDIUM", "Fill every row, column, and 3x3 box with digits 1-9 without repeating.")
            elif kind == "divider":
                py_escpos = render_divider_raster()
            elif kind == "master_footer":
                py_escpos = render_master_footer_raster("Enjoy your day!", False, True)
            else:
                raise RuntimeError(f"Unknown chrome kind {kind}")
        else:
            if p_name == "stars":
                plugin_id = "queens"
            elif p_name.startswith("wordsearch"):
                plugin_id = "wordsearch"
            else:
                plugin_id = p_name
            plugin = DEFAULT_REGISTRY.get(plugin_id)
            assert plugin is not None, f"Plugin {plugin_id} not found in registry"
            covered_boards.add(plugin_id)

            if p_name == "jumble":
                py_data = {
                    "words": item["words"],
                    "scrambled": item["scrambled"],
                    "circles": item["circles"],
                    "riddle": item["riddle"],
                    "answer": item["answer"]
                }
            elif p_name == "wheel":
                py_data = {
                    "center_letter": item["center_letter"],
                    "outer_letters": item["outer_letters"],
                    "good": item["good"],
                    "great": item["great"],
                    "genius": item["genius"],
                    "count4": item.get("count4", 0),
                    "count5": item.get("count5", 0),
                    "count6": item.get("count6", 0),
                    "count7plus": item.get("count7plus", 0),
                }
            elif p_name == "mines":
                py_data = {
                    "rows": item["rows"],
                    "cols": item["cols"],
                    "total_mines": item["total_mines"],
                    "puzzle": item["grid"]
                }
            elif p_name == "tents":
                py_data = {
                    "size": item["size"],
                    "row_clues": item["row_clues"],
                    "col_clues": item["col_clues"],
                    "puzzle": item["grid"]
                }
            elif p_name == "stars":
                py_data = {
                    "size": item["size"],
                    "grid_size": item["size"],
                    "stars_per_unit": item.get("stars_per_unit", 1),
                    "regions": item["regions"]
                }
            elif p_name in ("wordsearch", "wordsearch_easy"):
                py_data = {
                    "grid": item["grid"],
                    "words": item["words"],
                    "theme": item["theme"]
                }
            elif p_name in ("sudoku", "sudokito"):
                py_data = {"puzzle": item["grid"]}
            elif p_name == "loop":
                py_data = {
                    "size": item["size"],
                    "clues": item["clues"],
                    "difficulty": item.get("difficulty", "medium")
                }
            elif p_name == "nonogram":
                py_data = {
                    "size": item["size"],
                    "row_clues": item["row_clues"],
                    "col_clues": item["col_clues"],
                }
            elif p_name == "lights":
                py_data = {
                    "size": item["size"],
                    "puzzle": item["grid"],
                }
            elif p_name == "killer":
                py_data = {
                    "size": item["size"],
                    "box_rows": item["box_rows"],
                    "box_cols": item["box_cols"],
                    "cages": item["cages"],
                }
            elif p_name == "cryptogram":
                py_data = {
                    "phrase": item["phrase"],
                    "author": item["author"],
                    "ciphertext": item["ciphertext"],
                    "clues": item.get("clues", []),
                    "clue_str": item.get("clue_str", ""),
                    "difficulty": item.get("difficulty", "easy"),
                }
            elif p_name == "ladder":
                py_data = {
                    "start_word": item["start_word"],
                    "target_word": item["target_word"],
                    "word_len": item["word_len"],
                    "total_words": item["total_words"],
                    "solution": item["solution"],
                    "difficulty": item.get("difficulty", "easy"),
                }
            elif p_name == "binary":
                py_data = {"size": item["size"], "puzzle": item["grid"]}
            elif p_name == "bridges":
                py_data = {"size": item["size"], "islands": item["islands"]}
            elif p_name == "tango":
                py_data = {
                    "size": item["size"],
                    "puzzle": item["grid"],
                    "edges_h": item["edges_h"],
                    "edges_v": item["edges_v"],
                }
            elif p_name == "towers":
                py_data = {
                    "size": item["size"],
                    "clues": item["clues"],
                    "solution": item["solution"],
                    "difficulty": item.get("difficulty", "medium"),
                }
            elif p_name == "inequality":
                py_data = {
                    "size": item["size"],
                    "givens": item["givens"],
                    "edges_h": item["edges_h"],
                    "edges_v": item["edges_v"],
                    "solution": item["solution"],
                    "difficulty": item.get("difficulty", "medium"),
                }
            elif p_name == "maze":
                py_data = {
                    "size": item["size"],
                    "walls_h": item["walls_h"],
                    "walls_v": item["walls_v"],
                    "difficulty": item.get("difficulty", "medium"),
                }
            else:
                raise RuntimeError(f"Unknown puzzle {p_name}")

            py_escpos = plugin.render_raster(py_data)

        assert py_escpos[:3] == b"\x1d\x76\x30", f"Invalid ESC/POS header for {label}"
        py_w_bytes = py_escpos[4] | (py_escpos[5] << 8)
        py_h = py_escpos[6] | (py_escpos[7] << 8)
        py_raw = py_escpos[8:]

        if not compare_bitmaps(label, width, height, cpp_raw, py_raw, py_w_bytes * 8, py_h, "Python"):
            overall_pass = False

        js_entry = js_results[idx]
        assert not js_entry["vectorCalls"], f"Prohibited vector calls in JS for {label}: {js_entry['vectorCalls']}"
        js_raw = bytes.fromhex(js_entry["hex"])
        if not compare_bitmaps(label, width, height, cpp_raw, js_raw, js_entry["width"], js_entry["height"], "JS"):
            overall_pass = False
        print()

    expected_ids = {p.puzzle_id for p in DEFAULT_REGISTRY.get_all()}
    missing_boards = sorted(expected_ids - covered_boards)
    missing_guides = sorted(expected_ids - covered_guides)
    assert not missing_boards, f"Rule 25 Violation: Games missing 3-way visual board coverage: {missing_boards}"
    assert not missing_guides, f"Rule 25 Violation: Games missing 3-way visual guide coverage: {missing_guides}"
    print(f"[OK] 3-way visual parity coverage complete: {len(covered_boards)}/{len(expected_ids)} puzzle boards and {len(covered_guides)}/{len(expected_ids)} game guides verified (Rule 25).")

    print("=" * 70)
    if overall_pass:
        print(f"ALL 3-WAY VISUAL CONSISTENCY TESTS PASSED (100% ACROSS {len(items)} CASES)!")
    else:
        print("SOME VISUAL CONSISTENCY CHECKS FELL BELOW THRESHOLD.")
    print("=" * 70)
    return overall_pass


if __name__ == "__main__":
    success = test_visual_consistency()
    sys.exit(0 if success else 1)
