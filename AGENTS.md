# Pen and Paper Puzzles: Agent Behavioral & Formatting Standards

Authoritative behavioral, formatting, and architecture rules are maintained in:
👉 `.agents/rules/puzzle_standards.md`

All agents must strictly comply with Rules 1 through 18 defined therein:
- Rules 1–4: Game Titles, Difficulty, Descriptions, Solution Keys
- Rule 5: Automated Verification
- Rule 6: Puzzle Plugin Architecture (`server/app/puzzles/base.py`)
- Rule 7: Arduino IDE Dual-Target Synchronization Standard
- Rule 8: Tri-Target Visual Parity Standard (Python, ESP32 C++, Web Simulator)
- Rule 9: Master Receipt Header & Footer Offline Standards
- Rule 10: Logical Opening Anchors & Curated Deductive Datasets
- Rule 11: Thermal Shading, Badges & Hatching Discipline
- Rule 12: Grid Geometry Harmonization & Single-Frame Line Discipline
- Rule 13: Clue Margins & Clean Playable Cell Standards
- Rule 14: Standalone Offline Appliance Standard
- Rule 15: Single Source of Truth for Curated Datasets
- Rule 16: Web Simulator Hardware Emulation Standard
- Rule 17: Shared Utilities, DRY Primitives & Dynamic Count Standard
- Rule 18: Game Onboarding, Setup Portal, Documentation & Parity Standard

Engineering performance, hardware budgets, solver safety, and CI coverage gates are maintained in:
👉 `.agents/rules/engineering_performance_and_ci.md`

All agents must also strictly comply with Rules 19 through 25 defined therein:
- Rule 19: ESP32 Banded Raster Memory (`<= 18,432 B`) & `.rodata` Flash Discipline
- Rule 20: Bounded Iterative Solvers, Mandatory Retry Handling & WDT `yield()`
- Rule 21: Declarative Multi-Target Game Guides (`diagram_ops` SSoT)
- Rule 22: Strictly Printable 7-Bit ASCII & Fail-Loud Dataset Pipeline
- Rule 23: Zero-CDN Offline Web Targets, Payload Budgets & Real-Event Coverage
- Rule 24: Python Pure-Bitmap Performance, Shared Utilities & Python 3.9+ Compatibility
- Rule 25: New-Feature Full-Coverage Contract & PR/CI Gate Parity
