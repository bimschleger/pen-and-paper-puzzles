#include "OfflinePuzzleComposer.h"
#include "config.h"
#include "GeneratorUtils.h"
#include "EscPosPrinter.h"
#include "ThermalCanvas.h"
#include "GameRulesDataset.h"

OfflinePuzzleComposer::OfflinePuzzleComposer() : 
    _currentGrade(GRADE_MEDIUM), 
    _rotationIndex(0) {
}

void OfflinePuzzleComposer::cycleGrade() {
    _rotationIndex = (_rotationIndex + 1) % 3;
    _currentGrade = (PuzzleGrade)_rotationIndex;
}

void OfflinePuzzleComposer::setGrade(PuzzleGrade grade) {
    _currentGrade = grade;
}

PuzzleGrade OfflinePuzzleComposer::getCurrentGrade() const {
    return _currentGrade;
}

const char* OfflinePuzzleComposer::getGradeName(PuzzleGrade grade) const {
    return OfflineConfigManager::getGradeName(grade);
}

PuzzleGrade OfflinePuzzleComposer::getGradeForSlot(uint8_t index, uint8_t totalCount) const {
    if (totalCount <= 1) return GRADE_MEDIUM;
    float p = (float)index / (float)(totalCount - 1);
    if (p < 0.25f) return GRADE_EASY;
    if (p < 0.65f) return GRADE_MEDIUM;
    if (p < 0.85f) return GRADE_HARD;
    return GRADE_EXTREME;
}

bool OfflinePuzzleComposer::supportsExtreme(OfflinePuzzleType type) const {
    return (type == PUZZLE_LIGHTS || type == PUZZLE_QUEENS || type == PUZZLE_KILLER ||
            type == PUZZLE_TOWERS || type == PUZZLE_INEQUALITY || type == PUZZLE_MAZE);
}

void OfflinePuzzleComposer::printSinglePuzzle(EscPosPrinter& printer, OfflinePuzzleType type, bool useRaster, PuzzleGrade grade) {
    PuzzleGrade effectiveGrade = (grade == GRADE_EXTREME && !supportsExtreme(type)) ? GRADE_HARD : grade;
    if (effectiveGrade != GRADE_EASY && effectiveGrade != GRADE_HARD && effectiveGrade != GRADE_EXTREME) {
        effectiveGrade = GRADE_MEDIUM;
    }
    const char* diffStr = OfflineConfigManager::getGradeName(effectiveGrade);
    uint8_t tier3 = (effectiveGrade == GRADE_EASY) ? 0 : ((effectiveGrade == GRADE_HARD) ? 2 : 1);
    uint8_t tier4 = (effectiveGrade == GRADE_EXTREME) ? 3 : tier3;

    switch (type) {
        case PUZZLE_SUDOKU: {
            SudokuDifficulty diff = (SudokuDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Sudoku...");
            SudokuGen sudoku;
            sudoku.generate(diff);
            printPuzzleHeader(printer, "SUDOKU", diffStr, 
                              "Fill every row, column, and 3x3 box with digits 1-9 without repeating.");
            if (!useRaster || !sudoku.printRasterToReceipt(printer, diff)) {
                sudoku.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_WORDSEARCH: {
            WordSearchDifficulty diff = (WordSearchDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Word Search...");
            WordSearchGen wordSearch;
            wordSearch.generate(diff);
            char wsInstr[64];
            snprintf(wsInstr, sizeof(wsInstr), "Find all %d hidden words listed below.", (int)wordSearch.getWordCount());
            printPuzzleHeader(printer, "SEARCH", diffStr, wsInstr);
            if (!useRaster || !wordSearch.printRasterToReceipt(printer)) {
                wordSearch.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_NONOGRAM: {
            NonogramDifficulty diff = (NonogramDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Nonogram...");
            NonogramGen nonogram;
            nonogram.generate(diff);
            printPuzzleHeader(printer, "NONOGRAM", diffStr, 
                              "Shade blocks of cells matching each clue in order, separated by at least one empty cell.");
            if (!useRaster || !nonogram.printRasterToReceipt(printer)) {
                nonogram.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_QUEENS: {
            QueensDifficulty diff = (QueensDifficulty)tier4;
            Serial.println("[COMPOSER] Generating Queens puzzle...");
            QueensGen queens;
            queens.generate(diff);
            const char* instr1 = (diff == QUEENS_HARD || diff == QUEENS_MASTER) 
                ? "Place 2 stars in each row, column, and region" 
                : "Place 1 star in each row, column, and region";
            printPuzzleHeader(printer, "STARS", diffStr, instr1, "with no stars touching, even diagonally.");
            if (!useRaster || !queens.printRasterToReceipt(printer)) {
                queens.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_JUMBLE: {
            JumbleDifficulty diff = (JumbleDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Daily Jumble...");
            JumbleGen jumble;
            jumble.generate(diff);
            printPuzzleHeader(printer, "JUMBLE", diffStr,
                              "Unscramble each word, then use the circled letters to solve the riddle.");
            if (!useRaster || !jumble.printRasterToReceipt(printer)) {
                jumble.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_BINARY: {
            BinaryDifficulty diff = (BinaryDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Binary...");
            BinaryGen binary;
            binary.generate(diff);
            const char* binInstr1 = (diff == BINARY_EASY)
                ? "Fill each row and column with three 0s and"
                : "Fill each row and column with four 0s and";
            const char* binInstr2 = (diff == BINARY_EASY)
                ? "three 1s, with no more than two consecutive of each type."
                : "four 1s, with no more than two consecutive of each type.";
            printPuzzleHeader(printer, "BINARY", diffStr, binInstr1, binInstr2);
            if (!useRaster || !binary.printRasterToReceipt(printer, diff)) {
                binary.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_MINES: {
            MinesDifficulty diff = (MinesDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Mines...");
            MinesGen mines;
            mines.generate(diff);
            char instr[64];
            snprintf(instr, sizeof(instr), "Deduce all %d hidden mines using the adjacent numbered clues.", (int)mines.getTotalMines());
            printPuzzleHeader(printer, "MINES", diffStr, instr);
            if (!useRaster || !mines.printRasterToReceipt(printer, diff)) {
                mines.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_TENTS: {
            TentsDifficulty diff = (TentsDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Tents...");
            TentsGen tents;
            tents.generate(diff);
            char tentsInstr[128];
            snprintf(tentsInstr, sizeof(tentsInstr), "Pitch %d tents beside trees; no tents may touch even diagonally, matching row/column counts.", (int)tents.getTreeCount());
            printPuzzleHeader(printer, "TENTS", diffStr, tentsInstr);
            if (!useRaster || !tents.printRasterToReceipt(printer, diff)) {
                tents.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_BRIDGES: {
            BridgesDifficulty diff = (BridgesDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Bridges...");
            BridgesGen bridges;
            bridges.generate(diff);
            printPuzzleHeader(printer, "BRIDGES", diffStr, 
                              "Connect all islands into one network using 1 or 2 lines matching each island's number.");
            if (!useRaster || !bridges.printRasterToReceipt(printer, diff)) {
                bridges.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_TANGO: {
            TangoDifficulty diff = (TangoDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Tango...");
            TangoGen tango;
            tango.generate(diff);
            const char* tangoInstr = (diff == TANGO_HARD)
                ? "Fill each line with four 0s and four 1s without trios; = means same, x means opposite."
                : "Fill each line with three 0s and three 1s without trios; = means same, x means opposite.";
            printPuzzleHeader(printer, "TANGO", diffStr, tangoInstr);
            if (!useRaster || !tango.printRasterToReceipt(printer, diff)) {
                tango.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_WHEEL: {
            WheelDifficulty diff = (WheelDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Wheel...");
            WheelGen wheel;
            wheel.generate(diff);
            char instr[110];
            snprintf(instr, sizeof(instr), "Find %d+ words using center letter %c (letters may repeat), including a 7-letter pangram.", 
                     (int)wheel.getWordCount(), wheel.getCenterLetter());
            printPuzzleHeader(printer, "WHEEL", diffStr, instr);
            if (!useRaster || !wheel.printRasterToReceipt(printer)) {
                wheel.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_LIGHTS: {
            LightsDifficulty diff = (LightsDifficulty)tier4;
            Serial.println("[COMPOSER] Generating Lights...");
            LightsGen lights;
            lights.generate(diff);
            char lightsInstr[128];
            snprintf(lightsInstr, sizeof(lightsInstr), "Place %d bulbs to light corridors; none can face each other; numbers show bulbs sharing an edge.", (int)lights.getTotalBulbs());
            printPuzzleHeader(printer, "LIGHTS", diffStr, lightsInstr);
            if (!useRaster || !lights.printRasterToReceipt(printer, diff)) {
                lights.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_LOOP: {
            LoopDifficulty diff = (LoopDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Loop...");
            LoopGen loop;
            loop.generate(diff);
            printPuzzleHeader(printer, "LOOP", diffStr, 
                              "Draw a single continuous closed loop connecting dots so each number matches its edge count.");
            if (!useRaster || !loop.printRasterToReceipt(printer, diff)) {
                loop.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_KILLER: {
            KillerDifficulty diff = (KillerDifficulty)tier4;
            Serial.println("[COMPOSER] Generating Killer Sudoku...");
            KillerGen killer;
            killer.generate(diff);
            const char* rangeStr = (diff == KILLER_EXTREME || diff == KILLER_HARD) ? "1-6" : "1-4";
            char killerInstr[100];
            snprintf(killerInstr, sizeof(killerInstr), "Fill every row, column, and box with digits %s, matching cage sums without repeats.", rangeStr);
            printPuzzleHeader(printer, "KILLER", diffStr, killerInstr);
            if (!useRaster || !killer.printRasterToReceipt(printer)) {
                killer.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_CRYPTOGRAM: {
            CryptogramDifficulty diff = (CryptogramDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Cryptogram...");
            CryptogramGen cryptogram;
            cryptogram.generate(diff);
            uint8_t clueCnt = cryptogram.getClueCount();
            char cryptoInstr[100];
            snprintf(cryptoInstr, sizeof(cryptoInstr), "Deduce the hidden phrase using the %s and substitution logic.",
                     (clueCnt == 1) ? "1 letter clue" : (clueCnt == 3 ? "3 letter clues" : "2 letter clues"));
            printPuzzleHeader(printer, "CRYPTOGRAM", diffStr, cryptoInstr);
            if (!useRaster || !cryptogram.printRasterToReceipt(printer)) {
                cryptogram.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_LADDER: {
            LadderDifficulty diff = (LadderDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Ladder...");
            LadderGen ladder;
            ladder.generate(diff);
            uint8_t count = ladder.getIntermediateCount();
            char instr[100];
            char countPhrase[32];
            if (count == 1) {
                snprintf(countPhrase, sizeof(countPhrase), "1 English word");
            } else {
                snprintf(countPhrase, sizeof(countPhrase), "%d English words", (int)count);
            }
            snprintf(instr, sizeof(instr), "Deduce %s to link %s to %s, changing 1 letter each step.",
                     countPhrase, ladder.getStartWord(), ladder.getTargetWord());
            printPuzzleHeader(printer, "LADDER", diffStr, instr);
            if (!useRaster || !ladder.printRasterToReceipt(printer)) {
                ladder.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_TOWERS: {
            TowersDifficulty diff = (TowersDifficulty)tier4;
            Serial.println("[COMPOSER] Generating Towers...");
            TowersGen towers;
            towers.generate(diff);
            char towersInstr[100];
            snprintf(towersInstr, sizeof(towersInstr), "Place heights 1-%d per line so exterior numbers match the count of visible taller buildings.", (int)towers.getSize());
            printPuzzleHeader(printer, "TOWERS", diffStr, towersInstr);
            if (!useRaster || !towers.printRasterToReceipt(printer)) {
                towers.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_INEQUALITY: {
            InequalityDifficulty diff = (InequalityDifficulty)tier4;
            Serial.println("[COMPOSER] Generating Inequality...");
            InequalityGen inequality;
            inequality.generate(diff);
            char inequalityInstr[100];
            snprintf(inequalityInstr, sizeof(inequalityInstr), "Fill digits 1-%d in every line while satisfying all inequality signs between adjacent cells.", (int)inequality.getSize());
            printPuzzleHeader(printer, "INEQUALITY", diffStr, inequalityInstr);
            if (!useRaster || !inequality.printRasterToReceipt(printer)) {
                inequality.printToReceipt(printer);
            }
            break;
        }
        case PUZZLE_MAZE: {
            MazeDifficulty diff = (MazeDifficulty)tier4;
            Serial.println("[COMPOSER] Generating Maze...");
            MazeGen maze;
            maze.generate(diff);
            printPuzzleHeader(printer, "MAZE", diffStr, "Draw a path from the entrance to the exit without crossing any walls.");
            if (!useRaster || !maze.printRasterToReceipt(printer, diff)) {
                maze.printToReceipt(printer, diff);
            }
            break;
        }
        case PUZZLE_SUDOKITO: {
            SudokitoDifficulty diff = (SudokitoDifficulty)tier3;
            Serial.println("[COMPOSER] Generating Sudokito...");
            SudokitoGen sudokito;
            sudokito.generate(diff);
            printPuzzleHeader(printer, "SUDOKITO", diffStr, 
                              "Fill every row, column, and 2x3 box with digits 1-6 without repeating.");
            if (!useRaster || !sudokito.printRasterToReceipt(printer, diff)) {
                sudokito.printToReceipt(printer, diff);
            }
            break;
        }
        default:
            break;
    }
}

bool OfflinePuzzleComposer::generateAndPrintReceipt(EscPosPrinter& printer, const String& subtitle, PuzzleGrade grade, const OfflineConfigManager* config) {
    // 1. Reseed PRNG with ESP32 hardware True Random Number Generator + microsecond timer
    randomSeed(esp_random() ^ (uint32_t)micros());

    // 2. Maintain grade state for status reporting
    PuzzleGrade effectiveGrade;
    if (grade != (PuzzleGrade)-1) {
        effectiveGrade = grade;
    } else if (config) {
        effectiveGrade = config->getPuzzleGrade();
    } else {
        effectiveGrade = GRADE_ESCALATING;
    }

    if (effectiveGrade == GRADE_ROTATING) {
        effectiveGrade = (PuzzleGrade)(_rotationIndex % 3);
        _rotationIndex = (_rotationIndex + 1) % 3;
    }
    _currentGrade = effectiveGrade;

    unsigned long startMs = millis();
    Serial.println("\n[COMPOSER] Starting 100% offline generation for DAILY PUZZLE MIX...");

    if (!printer.connect()) {
        Serial.println("[COMPOSER] ERROR: Failed to connect to printer.");
        return false;
    }

    printer.init();

    // 3. Determine enabled puzzle list and puzzle count
    OfflinePuzzleType activePuzzles[OFFLINE_PUZZLE_TOTAL];
    uint8_t totalAvailable = 0;

    if (config) {
        totalAvailable = config->getEnabledPuzzles(activePuzzles, OFFLINE_PUZZLE_TOTAL);
    }
    if (totalAvailable == 0) {
        totalAvailable = (uint8_t)OFFLINE_PUZZLE_TOTAL;
        for (uint8_t i = 0; i < totalAvailable; i++) {
            activePuzzles[i] = (OfflinePuzzleType)i;
        }
    }

    uint8_t count = config ? config->getPuzzleCount() : OFFLINE_PUZZLE_COUNT;
    if (count > totalAvailable) count = totalAvailable;
    if (count < 1) count = 1;

    // 4. Receipt Header
    String headerSubtitle = (subtitle.length() > 0) ? subtitle : "Enjoy Your Puzzles";
    char mixHeader[32];
    snprintf(mixHeader, sizeof(mixHeader), "DAILY %d-PUZZLE MIX", (int)count);

#if (OFFLINE_PRINT_STYLE == STYLE_HYBRID)
    bool useRaster = true;
#else
    bool useRaster = false;
#endif

    if (useRaster) {
        printer.printRasterHeader("PEN + PAPER PUZZLES", headerSubtitle.c_str(), mixHeader);
    } else {
        printer.printHeader("PEN + PAPER PUZZLES", headerSubtitle);
        printer.setAlign(ALIGN_CENTER);
        printer.println(mixHeader);
        printer.println("");
    }

    // Fisher-Yates shuffle on available enabled puzzles
    mp_shuffle(activePuzzles, totalAvailable);

    for (uint8_t i = 0; i < count; i++) {
        PuzzleGrade slotGrade = effectiveGrade;
        if (effectiveGrade == GRADE_ESCALATING) {
            slotGrade = getGradeForSlot(i, count);
        }
        printSinglePuzzle(printer, activePuzzles[i], useRaster, slotGrade);
        if (useRaster) {
            printer.printRasterDivider();
        } else {
            printer.printHorizontalLine('-');
        }
    }

    // Footer
    if (useRaster) {
        printer.printRasterMasterFooter("Enjoy your day!", false, false);
    } else {
        printer.printMasterFooter("Enjoy your day!", false, false);
    }

    printer.feed(4);
    printer.cut(false);
    printer.disconnect();

    unsigned long elapsed = millis() - startMs;
    Serial.printf("[COMPOSER] Generation & printing of %d puzzles completed in %lu ms!\n\n", 
                  count, elapsed);
    return true;
}

void OfflinePuzzleComposer::renderGameGuideRaster(ThermalCanvas& canvas, uint8_t gameId) {
    canvas.clear(0);
    int16_t w = canvas.getWidth();
    int16_t h = canvas.getHeight();
    int16_t midX = w / 2;

    // Outer border (thickness 2)
    canvas.drawRect(10, 8, w - 20, h - 16, 2);

    // Center dashed divider
    for (int16_t y = 10; y < h - 10; y += 8) {
        canvas.drawVLine(midX, y, 4, 1);
    }

    // Headers
    canvas.drawText(84, 16, "VALID MOVE", 2);
    canvas.drawText(360, 16, "INVALID MOVE", 2);

    // Callout labels below
    canvas.drawText(108, h - 28, "[ OK ]", 2);
    canvas.drawText(384, h - 28, "[ ERROR ]", 2);

    const GameRuleDef* def = getGameRuleDefById(gameId);
    if (!def) return;
    GameRuleDef ruleCopy;
    memcpy_P(&ruleCopy, def, sizeof(GameRuleDef));

    for (uint8_t i = 0; i < ruleCopy.opsCount; i++) {
        GuideOp op;
        memcpy_P(&op, &GUIDE_OPS_TABLE[ruleCopy.opsOffset + i], sizeof(GuideOp));
        int16_t cx = (op.panel == 0) ? 144 : 432;
        switch (op.op) {
            case GOP_GRID: {
                int16_t gx = cx + op.a, gy = op.b;
                int16_t cols = op.c, rows = op.d, sz = op.e;
                canvas.drawRect(gx, gy, cols * sz, rows * sz, 2);
                for (int16_t c = 1; c < cols; c++) canvas.drawVLine(gx + c * sz, gy, rows * sz, 1);
                for (int16_t r = 1; r < rows; r++) canvas.drawHLine(gx, gy + r * sz, cols * sz, 1);
                break;
            }
            case GOP_RECT:   canvas.drawRect(cx + op.a, op.b, op.c, op.d, (uint8_t)op.e); break;
            case GOP_FRECT:  canvas.fillRect(cx + op.a, op.b, op.c, op.d, (uint8_t)op.e); break;
            case GOP_HATCH:  canvas.fillHatch(cx + op.a, op.b, op.c, op.d, (uint8_t)op.e); break;
            case GOP_HLINE:  canvas.drawHLine(cx + op.a, op.b, op.c, (uint8_t)op.d); break;
            case GOP_VLINE:  canvas.drawVLine(cx + op.a, op.b, op.c, (uint8_t)op.d); break;
            case GOP_DHLINE: canvas.drawDashedHLine(cx + op.a, op.b, op.c, 4, 3, (uint8_t)op.d); break;
            case GOP_LINE:   canvas.drawLine(cx + op.a, op.b, cx + op.c, op.d, (uint8_t)op.e); break;
            case GOP_CIRC:   canvas.drawCircle(cx + op.a, op.b, op.c, (uint8_t)op.d); break;
            case GOP_TEXT:   canvas.drawText(cx + op.a, op.b, op.text, (uint8_t)op.c); break;
        }
    }
}

bool OfflinePuzzleComposer::printGameGuide(EscPosPrinter& printer, uint8_t gameId) {
    const GameRuleDef* def = getGameRuleDefById(gameId);
    if (!def) {
        Serial.printf("[COMPOSER] Game rule for ID %d not found!\n", gameId);
        return false;
    }

    if (!printer.connect()) {
        Serial.println("[COMPOSER] Printer connection failed for game guide!");
        return false;
    }

    printer.init();

    // Master Header
    printer.printRasterHeader("PEN + PAPER PUZZLES", "GAME GUIDE & QUICK REFERENCE");

    // Game Title + Instruction
    printer.printRasterPuzzleHeader(def->title, nullptr, def->instruction);

    // Objective & Rules of Play (typeset 203 DPI)
    {
        ThermalCanvas tc;
        uint16_t h = 4 + tc.getFontLineHeight(FONT_CAPTION_16) + 4 +
                     tc.measureWrappedHeightFont(def->objective, 536, FONT_BODY_20, 4) + 14 +
                     tc.getFontLineHeight(FONT_CAPTION_16) + 6;
        for (uint8_t i = 0; i < def->ruleCount; i++) {
            h += tc.measureWrappedHeightFont(def->rules[i], 516, FONT_BODY_20, 4) + 6;
        }
        h = (uint16_t)((h + 7) & ~7);
        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            int16_t curY = 4;
            c.drawTextFont(20, curY, "OBJECTIVE", FONT_CAPTION_16);
            curY += c.getFontLineHeight(FONT_CAPTION_16) + 4;
            curY += c.drawWrappedTextFont(20, curY, 536, def->objective, FONT_BODY_20, 0, 4) + 14;
            c.drawTextFont(20, curY, "RULES OF PLAY", FONT_CAPTION_16);
            curY += c.getFontLineHeight(FONT_CAPTION_16) + 6;
            for (uint8_t i = 0; i < def->ruleCount; i++) {
                c.fillCircle(26, curY + 12, 3, 1);
                curY += c.drawWrappedTextFont(40, curY, 516, def->rules[i], FONT_BODY_20, 0, 4) + 6;
            }
        });
    }

    // Visual Move Diagram (Thermal Canvas - Banded Streaming)
    ThermalCanvas canvas;
    canvas.renderBanded(printer, 216, [&](ThermalCanvas& c) {
        renderGameGuideRaster(c, gameId);
    });

    // Move captions, Where to Start, and Common Questions (typeset 203 DPI)
    {
        ThermalCanvas tc;
        uint16_t h = 4;
        h += tc.getFontLineHeight(FONT_CAPTION_16) + 4 + tc.measureWrappedHeightFont(def->validCaption, 536, FONT_BODY_20, 4) + 10;
        h += tc.getFontLineHeight(FONT_CAPTION_16) + 4 + tc.measureWrappedHeightFont(def->invalidCaption, 536, FONT_BODY_20, 4) + 14;
        h += tc.getFontLineHeight(FONT_CAPTION_16) + 6;
        for (uint8_t i = 0; i < def->anchorCount; i++) {
            h += tc.measureWrappedHeightFont(def->openingAnchors[i], 516, FONT_BODY_20, 4) + 6;
        }
        h += 8 + tc.getFontLineHeight(FONT_CAPTION_16) + 6;
        for (uint8_t i = 0; i < def->faqCount; i++) {
            h += tc.measureWrappedHeightFont(def->faq[i].question, 510, FONT_SUBHEAD_22, 2) + 4;
            h += tc.measureWrappedHeightFont(def->faq[i].answer, 510, FONT_BODY_20, 4) + 10;
        }
        h = (uint16_t)((h + 7) & ~7);
        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            int16_t curY = 4;
            c.drawTextFont(20, curY, "VALID MOVE", FONT_CAPTION_16);
            curY += c.getFontLineHeight(FONT_CAPTION_16) + 4;
            curY += c.drawWrappedTextFont(20, curY, 536, def->validCaption, FONT_BODY_20, 0, 4) + 10;
            c.drawTextFont(20, curY, "INVALID MOVE", FONT_CAPTION_16);
            curY += c.getFontLineHeight(FONT_CAPTION_16) + 4;
            curY += c.drawWrappedTextFont(20, curY, 536, def->invalidCaption, FONT_BODY_20, 0, 4) + 14;
            c.drawTextFont(20, curY, "WHERE TO START", FONT_CAPTION_16);
            curY += c.getFontLineHeight(FONT_CAPTION_16) + 6;
            for (uint8_t i = 0; i < def->anchorCount; i++) {
                c.fillCircle(26, curY + 12, 3, 1);
                curY += c.drawWrappedTextFont(40, curY, 516, def->openingAnchors[i], FONT_BODY_20, 0, 4) + 6;
            }
            curY += 8;
            c.drawTextFont(20, curY, "COMMON QUESTIONS", FONT_CAPTION_16);
            curY += c.getFontLineHeight(FONT_CAPTION_16) + 6;
            for (uint8_t i = 0; i < def->faqCount; i++) {
                c.drawTextFont(20, curY + 2, "Q:", FONT_CAPTION_16);
                curY += c.drawWrappedTextFont(46, curY, 510, def->faq[i].question, FONT_SUBHEAD_22, 0, 2) + 4;
                c.drawTextFont(20, curY + 2, "A:", FONT_CAPTION_16);
                curY += c.drawWrappedTextFont(46, curY, 510, def->faq[i].answer, FONT_BODY_20, 0, 4) + 10;
            }
        });
    }

    // Master Footer
    printer.printRasterMasterFooter("Enjoy your day!", false, true);

    printer.feed(4);
    printer.cut(false);
    printer.disconnect();

    Serial.printf("[COMPOSER] Printed Game Guide for %s (ID %d)!\n", def->title, gameId);
    return true;
}

bool OfflinePuzzleComposer::printGameSampler(EscPosPrinter& printer, uint8_t gameId) {
    randomSeed(esp_random() ^ (uint32_t)micros());
    if (gameId >= OFFLINE_PUZZLE_TOTAL) {
        Serial.printf("[COMPOSER] Game ID %d out of range for sampler!\n", gameId);
        return false;
    }

    const GameRuleDef* def = getGameRuleDefById(gameId);
    if (!def) {
        Serial.printf("[COMPOSER] Game rule for ID %d not found!\n", gameId);
        return false;
    }

    if (!printer.connect()) {
        Serial.println("[COMPOSER] Printer connection failed for game sampler!");
        return false;
    }

    printer.init();

#if (OFFLINE_PRINT_STYLE == STYLE_HYBRID)
    bool useRaster = true;
#else
    bool useRaster = false;
#endif

    // Minimal header: --- [TITLE] TEST PRINT ---
    if (useRaster) {
        char testTitle[48];
        snprintf(testTitle, sizeof(testTitle), "%s TEST PRINT", def->title);
        printer.printRasterPuzzleHeader(testTitle, nullptr, nullptr);
    } else {
        printer.setAlign(ALIGN_CENTER);
        printer.setBold(true);
        printer.print("--- ");
        printer.print(def->title);
        printer.println(" TEST PRINT ---");
        printer.setBold(false);
        printer.println("");
    }

    OfflinePuzzleType type = (OfflinePuzzleType)gameId;

    // Difficulty tiers: Easy, Medium, Hard, and Extreme (if supported)
    PuzzleGrade tiers[4] = { GRADE_EASY, GRADE_MEDIUM, GRADE_HARD, GRADE_EXTREME };
    uint8_t tierCount = supportsExtreme(type) ? 4 : 3;

    for (uint8_t i = 0; i < tierCount; i++) {
        printSinglePuzzle(printer, type, useRaster, tiers[i]);
        if (useRaster) {
            printer.printRasterDivider();
        } else {
            printer.printHorizontalLine('-');
        }
    }

    // Standard Daily Footer
    if (useRaster) {
        printer.printRasterMasterFooter("Enjoy your day!", false, false);
    } else {
        printer.printMasterFooter("Enjoy your day!", false, false);
    }

    printer.feed(4);
    printer.cut(false);
    printer.disconnect();

    Serial.printf("[COMPOSER] Printed Game Sampler for %s (ID %d)!\n", def->title, gameId);
    return true;
}


