---
name: pr
description: Inspects active code changes, runs pre-flight tests & Arduino sketch synchronization, creates/manages a feature branch, commits changes, pushes to GitHub origin, and opens a Pull Request targeting main. Use whenever the user types /pr or asks to create a pull request.
---

# PR: Automated Review, Test, Commit, Push & Pull Request Creation

This skill automates the complete pull request workflow for **Pen and Paper Puzzles**:
1. Inspecting active code modifications and diffs.
2. Managing branch isolation (automatically branching if on `main`).
3. Running local pre-flight tests (`test_puzzle_standards.py`) and Arduino sketch mirroring (`sync_arduino_sketch.sh`).
4. Generating conventional commit titles and structured descriptions.
5. Pushing the feature branch to `origin`.
6. Creating a Pull Request against `main` using GitHub CLI (`gh pr create`) with a web URL fallback.

---

## Workflow Steps

When the user runs `/pr` (or asks to create a pull request), execute this exact sequence:

### 1. Inspect Active Changes & Code Diff
1. Run `git status -s` to identify all modified, added, deleted, and untracked files.
2. Run `git diff` to view unstaged diffs and `git diff --cached` to inspect any already staged changes.
3. Review untracked files to ensure they are intended project files and not temporary scratchpads, IDE artifacts (`.DS_Store`), or credentials.
4. **Early Exit on Clean State**:
   - If `git status` reports working tree clean (no staged, unstaged, or untracked changes) and no unpushed commits:
     - Inform the user: *"Working tree is clean. There are no changes to commit."*
     - Stop execution.

---

## 2. Branch & Worktree Management
1. Check current branch:
   ```bash
   git branch --show-current
   ```
2. **If currently on `main`**:
   - Formulate a concise, kebab-case branch name reflecting the changes (e.g., `feature/add-daily-pr-workflow`, `fix/jumble-circle-alignment`, `refactor/tango-raster`).
   - Create and switch to the new feature branch:
     ```bash
     git checkout -b <branch-name>
     ```
   - Inform the user: *"Created and switched to feature branch `<branch-name>` to keep `main` clean."*
3. **If already on a feature branch or worktree**:
   - Stay on the current branch.

---

### 3. Pre-Flight Verification & Hygiene (Rule Enforcement)
Before committing, ensure repository integrity across all 5 tiers (Standards, Logic/Watchdogs, Raster/Simulator/Visual Parity, Firmware/Stack/Budget Safety, and Randomized Stress):
1. **Compiled Datasets & Portal Sync (Rules 15, 18, 21, 22)**:
   If any file under `server/data/`, `portal.html`, or `tools/datasets/` changed, recompile and stage all generated headers, simulator datasets, portal header, and guide docs:
   ```bash
   python3 tools/datasets/build_all_datasets.py
   ```
2. **Arduino Sketch Synchronization (Rule 7)**:
   ```bash
   chmod +x ./scripts/sync_arduino_sketch.sh
   ./scripts/sync_arduino_sketch.sh
   ```
   If `PenAndPaperPuzzles/` files were updated by the sync script, ensure they are staged.
3. **Full Unified PR Verification Gate (`run_tests.py` + Stress)**:
   ```bash
   python3 run_tests.py
   python3 run_tests.py --tier stress --iterations 3
   ```
   These gates execute and enforce:
   - **Puzzle Presentation, Onboarding & Rules (Rules 1–4, 6, 18)**: `server/test_puzzle_standards.py`, `server/test_game_onboarding.py`, `server/test_game_rules.py`
   - **Code Health, DRY, Budgets & Safety Guardrails (Rules 6, 15, 17, 19–24)**: `server/test_code_health_and_dry.py` ($\le 150\text{ms}$ per-puzzle watchdog, bounded iterative solvers with return checks, 7-bit ASCII datasets, zero-CDN/size budgets, Python 3.9+ AST compatibility, $\le 150\text{ms}$ 20-game Python raster batch)
   - **Deductive Solvability & Opening Anchors (Rule 10)**: `server/test_stars_deduction.py`, `server/test_towers_deduction.py`, `server/test_inequality_deduction.py`, `server/test_killer_deduction.py`
   - **Thermal Raster Safety, Golden Snapshots & 100.00% Bit-for-Bit Visual Parity (Rules 8, 11–13, 21, 25)**: `server/test_thermal_format.py`, `server/test_thermal_snapshots.py`, `server/test_visual_consistency.py` (all registered boards & guides)
   - **Web Simulator Headless Runtime & Hardware Emulation (Rules 16, 23)**: `server/test_simulator_runtime.py` (all 20 `*Simulator` classes, `renderOffline<Game>` 1-bit canvases, `drawSimGuideCanvas` diagrams, real `change` event dispatch, and Portal API error handling)
   - **ESP32 Firmware Parity, RAM/`.rodata` Budgets & Tri-Profile Compilation (Rules 7, 14, 17, 19)**: `server/test_firmware_parity.py` (`<= 18,432 B` band RAM, `<= 38,000 B` prod `.rodata`, Production + `-DHOST_TEST` + ESP32-S3 syntax profiles)

   If any check fails, halt and fix the issue before proceeding.

---

### 4. Generate Commit & PR Title and Description
Analyze the diffs and conversation context to produce high-quality metadata:

#### A. Title
- Concise: **$\le 72$ characters** (ideally $\le 50$ characters).
- Conventional Commit prefix: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- Imperative mood (e.g., `feat: implement github actions ci and pr workflow`).

#### B. Description / PR Body
- Separated from the title by a blank line.
- Provide a clear, bulleted summary:
  - **Summary**: What was added, changed, or fixed.
  - **Motivation**: Why the change was made.
  - **Testing**: What local tests passed (`python3 run_tests.py`, `--tier stress --iterations 3`, `test_visual_consistency.py`, `build_all_datasets.py`, `sync_arduino_sketch.sh --check`).
  - **Coverage Checklist (Rules 18–25)** (when adding/modifying features or games):
    - [ ] 3-way visual parity (`C++ == Python == JS`) verified for board + `guide:<id>`
    - [ ] Golden snapshots (`golden_registry.json`) updated & verified
    - [ ] Simulator runtime (`cachedBundle`/events) & Portal 1-bit/HTTP error checks pass
    - [ ] Curated datasets & `PenAndPaperPuzzles/` synchronized with zero drift
    - [ ] Firmware compiles across Production, `-DHOST_TEST`, and ESP32-S3 profiles within RAM/`.rodata` budgets

---

### 5. Stage & Commit
1. Stage the relevant modified and untracked files:
   ```bash
   git add <files>
   ```
2. Execute the commit:
   ```bash
   git commit -m "<Commit Title>" -m "<Commit Description>"
   ```

---

### 6. Push to Remote Feature Branch
Push the branch to `origin`:
```bash
git push -u origin <branch-name>
```

---

### 7. Open Pull Request on GitHub
1. Check GitHub CLI authentication status:
   ```bash
   gh auth status
   ```
2. **If authenticated**:
   - Create the PR targeting `main`:
     ```bash
     gh pr create --base main --head <branch-name> --title "<Commit Title>" --body "<Commit Description>"
     ```
   - Capture and display the resulting PR URL to the user.
3. **If `gh` is unauthenticated or encounters an error**:
   - Display a direct GitHub web URL for one-click creation:
     ```text
     https://github.com/bimschleger/pen-and-paper-puzzles/compare/main...<branch-name>?expand=1
     ```
   - Remind the user:
     ```text
     Tip: Run `gh auth login` once in your terminal to enable zero-click automatic PR creation in future runs.
     ```

---

### 8. Final Report
Present a clean summary to the user:
- Branch: `<branch-name>`
- Commit: `<hash>` (`<title>`)
- PR URL: Link to the GitHub Pull Request
- Status: GitHub Actions CI checks are now running on the PR.
