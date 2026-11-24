---
description: Hardware memory/flash budgets, solver safety, declarative guide SSoT, offline web budgets, Python performance, and PR/CI coverage gates (Rules 19-25)
trigger: always_on
---

# Pen and Paper Puzzles: Engineering Performance, Safety & CI Coverage Standards

These non-negotiable engineering guardrails extend `.agents/rules/puzzle_standards.md` (Rules 1–18) and are enforced automatically by `run_tests.py`, `server/test_*.py`, `/pr`, and `.github/workflows/ci.yml`.

## 19. ESP32 Banded Raster Memory & `.rodata` Flash Discipline
- **Mandatory Banded Streaming (`<= 18,432 B` Peak RAM)**: All C++ puzzle and game guide raster renderers must stream through `ThermalCanvas::renderBanded()` (`BAND_HEIGHT = 256`, 18,432 B buffer) and `EscPosPrinter::beginRasterBitmap`/`writeRasterRows`/`endRasterBitmap`. Full-height `ThermalCanvas::begin()` allocations, `printRasterBitmap()` calls inside generators, and `ThermalCanvas` copies are prohibited.
- **Production `.rodata` Stripping (`#ifdef HOST_TEST`)**: Curated solution tables (`STARS_*_SOLUTIONS`, `MP_*_SOL_FIELD`/`MP_*_SOL`), host-only verification solvers (`MazeGen::solvePath`), and test-only `getSolution()` accessors must be guarded behind `#ifdef HOST_TEST`.
- **Tight Bit-Packing & Struct Sizing**: Pack low-cardinality `PROGMEM` datasets tightly (`mp_unpack_2bit_pgm` for 2-bit values, `mp_unpack_nibble_pgm` for 4-bit nibbles) and size fixed struct arrays (e.g. `cage_sums`) to verified dataset ceilings. Production curated `.rodata` (`Stars` + `Killer` + `Towers` + `Inequality`) must remain `<= 38,000 B`, and the 203 DPI `ThermalFonts.h` font pack (compiled from `server/data/thermal_fonts.json`) must remain `<= 16,000 B`.
- **Zero Heap Churn in ASCII Loops**: Format `printToReceipt()` rows into bounded stack `char buf[...]` buffers (`<= 1,024 B/array`, `<= 1,536 B/func`) instead of dynamic Arduino `String` concatenation.
- **Tri-Profile Firmware Compilation**: Every firmware change must compile and pass in **Production (no `-DHOST_TEST`)**, **Host Test (`-DHOST_TEST`)**, and **ESP32-S3 syntax (`-fsyntax-only -DCONFIG_IDF_TARGET_ESP32S3`)** profiles.

## 20. Bounded Iterative Solvers, Mandatory Retry Handling & WDT `yield()`
- **No Unbounded Recursion on ESP32**: Backtracking solvers (`fillBoard`, `countSolutions`, `solve*`) in `esp32-firmware/src/generators/` must use explicit iterative stacks with MRV selection, explicit `MAX_NODES` / `MAX_ITERS` bounds, and periodic `yield()`.
- **Mandatory Return-Code Check & Buffer Reset**: Every caller of a bounded generator (`generateFullBoard()`, `fillBoard()`) must check its `bool` return value, reset output buffers (`memset`) on entry/retry, and run a bounded retry loop with `yield()`. Ignoring a `bool` generator result is strictly prohibited.
- **Unified Difficulty Dispatch**: Route grade clamping (`tier3`/`tier4`) and display names (`OfflineConfigManager::getGradeName()`) once at the top of `OfflinePuzzleComposer::printSinglePuzzle()` rather than duplicating per-game ternary ladders.

## 21. Declarative Multi-Target Game Guides (`diagram_ops` SSoT)
- **Single Declarative Definition**: Every game's valid/invalid guide diagram must be expressed as `diagram_ops` in `server/data/game_rules.json` and compiled via `tools/datasets/build_game_rules.py` into `GameRulesDataset.h`, `portal.html`, and `receipt_simulator.html`.
- **No Hand-Coded Per-Game Guide Switches**: Per-game `switch (gameId)` or `if (gameId == ...)` guide drawing branches are prohibited across C++, Python, Web Simulator, and Portal.
- **1-Bit Parity Across All 4 Targets**: All 20 guides must pass 100.00% bit-for-bit 3-way parity (`C++ == Python == JS` in `test_visual_consistency.py`) and render via 1-bit `putImageData` (`ThermalCanvasMini`) in `portal.html`.

## 22. Strictly Printable 7-Bit ASCII & Fail-Loud Dataset Pipeline
- **7-Bit Printable ASCII Datasets**: Every string compiled into C++ `PROGMEM` datasets (`jumbles`, `cryptograms`, `wordsearch_dataset`, `ladder_words`, `wheel_dictionary`) must contain strictly printable 7-bit ASCII (`32 <= ord(ch) < 127`) and fit its C struct field capacity. Typographic Unicode punctuation (em-dashes, smart quotes) is forbidden in thermal datasets.
- **Buffered, Fail-Loud Compilers**: `tools/datasets/build_all_datasets.py` must buffer multi-marker HTML replacements in memory, anchor regexes to enclosing classes, raise `RuntimeError` immediately on any unmatched marker, and sync `PenAndPaperPuzzles/` once.
- **Zero Compiled Drift**: Any change to `server/data/*.json`, `portal.html`, or dataset compilers must produce zero uncommitted diff after running `python3 tools/datasets/build_all_datasets.py`.

## 23. Zero-CDN Offline Web Targets, Payload Budgets & Real-Event Coverage
- **Zero External Asset URLs**: `simulator/receipt_simulator.html` and `portal.html` must be 100% offline self-contained files with zero external `http://`/`https://` `<script>`, `<link>`, or `@import` URLs.
- **Payload Budgets**: Keep `simulator/receipt_simulator.html <= 650 KB` (via compact JS dataset encodings and minimal inline CSS) and `PortalHtml.h` compressed payload `<= 22 KB`.
- **Responsive UI & Error Discipline**: Presentation-only toggles (`#toggle-solutions`, `#toggle-burn`) must reuse `cachedBundle` without regenerating puzzles; DOM receipt rendering must batch via `DocumentFragment`; Portal `fetch()` calls must check `res.ok` and handle non-2xx responses cleanly without unhandled rejections.

## 24. Python Pure-Bitmap Performance, Shared Utilities & Runtime Compatibility
- **Minimal Dependencies**: Keep `server/requirements.txt` minimal—`Pillow` and `ortools` are prohibited, and `server/app/` must contain zero `PIL`/`HAS_PILLOW`/`pil_to_escpos` references.
- **Fast 1-Bit Raster Engine**: Maintain byte-aligned span writes (`_fill_row_span`), precomputed hatch tables (`_HATCH_TABLE`), and `math.isqrt` circle spans in `server/app/renderer/canvas.py`. Full 20-game medium Python `render_raster` bundle latency must remain `<= 150 ms`.
- **DRY Primitives & Solver Efficiency**: Use `server/app/puzzles/_grid_utils.py` (`ortho_neighbors`, `all_neighbors`, `is_orthogonally_connected`), `server/app/puzzles/base.py` ($D_4$ & dataset caching), lazy process-wide caches, and bitmask/worklist propagation in deductive solvers.
- **Python 3.9+ Compatibility**: Code in `server/` and `tools/` must remain compatible with Python 3.9+ (do not use Python 3.10+-only stdlib methods such as `int.bit_count()` or `match/case`).

## 25. New-Feature Full-Coverage Contract & PR/CI Gate Parity
Every new puzzle, difficulty tier, raster primitive, or UI/portal feature must ship with complete multi-tier automated coverage before PR merge:
1. **3-Way Visual Parity**: Registered in `server/visual_comparator_runner.cpp` and `server/test_visual_consistency.py` for BOTH the puzzle board (including hard/extreme tiers when geometry changes), `guide:<id>`, and `chrome:*` receipt chrome blocks, achieving **100.00% pixel similarity & 100.00% IoU** across C++, Python, and JS.
2. **Logic, Watchdog & Stress Coverage**: `verify_accuracy()` passing across all supported difficulties + invalid-difficulty fallback, `<= 150 ms` per-puzzle watchdog, `<= 35%` thermal duty cycle, and `python3 run_tests.py --tier stress --iterations 3` passing at 100%.
3. **Golden Snapshots**: Updated `server/tests/snapshots/golden_registry.json` verified by `test_thermal_snapshots.py`.
4. **Headless Web & Portal Tests**: Real event-dispatch coverage in `server/test_simulator_runtime.py` for new simulator controls/renderers and Portal API handlers (including HTTP 500 error paths).
5. **Zero-Drift Pipeline & Sketch Parity**: Clean pass of `python3 tools/datasets/build_all_datasets.py`, `./scripts/sync_arduino_sketch.sh --check`, and `python3 run_tests.py`.
