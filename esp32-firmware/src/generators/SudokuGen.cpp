#include "SudokuGen.h"
#include "GeneratorUtils.h"
#include "../printer/EscPosPrinter.h"
#include "../printer/ThermalCanvas.h"

SudokuGen::SudokuGen() : _cluesCount(81) {
    memset(_puzzle, 0, sizeof(_puzzle));
}

bool SudokuGen::isValid(uint8_t board[9][9], uint8_t row, uint8_t col, uint8_t num) {
    for (uint8_t i = 0; i < 9; i++) {
        if (board[row][i] == num || board[i][col] == num) {
            return false;
        }
    }
    uint8_t boxR = (row / 3) * 3;
    uint8_t boxC = (col / 3) * 3;
    for (uint8_t r = boxR; r < boxR + 3; r++) {
        for (uint8_t c = boxC; c < boxC + 3; c++) {
            if (board[r][c] == num) {
                return false;
            }
        }
    }
    return true;
}

static uint8_t findSudokuMrv(uint8_t board[9][9], uint8_t& bestR, uint8_t& bestC, uint16_t& bestMask) {
    uint8_t bestCandCount = 10;
    bestR = 0xFF;
    bestC = 0xFF;
    bestMask = 0;

    for (uint8_t r = 0; r < 9; r++) {
        for (uint8_t c = 0; c < 9; c++) {
            if (board[r][c] == 0) {
                uint16_t mask = 0;
                uint8_t cnt = 0;
                for (uint8_t num = 1; num <= 9; num++) {
                    bool ok = true;
                    for (uint8_t i = 0; i < 9; i++) {
                        if (board[r][i] == num || board[i][c] == num) { ok = false; break; }
                    }
                    if (ok) {
                        uint8_t br = (r / 3) * 3, bc = (c / 3) * 3;
                        for (uint8_t dr = 0; dr < 3 && ok; dr++) {
                            for (uint8_t dc = 0; dc < 3; dc++) {
                                if (board[br + dr][bc + dc] == num) { ok = false; break; }
                            }
                        }
                    }
                    if (ok) {
                        mask |= (uint16_t)(1u << num);
                        cnt++;
                    }
                }
                if (cnt == 0) return 0; // dead end
                if (cnt < bestCandCount) {
                    bestCandCount = cnt;
                    bestR = r;
                    bestC = c;
                    bestMask = mask;
                    if (cnt == 1) return 2; // found next cell
                }
            }
        }
    }
    return (bestR == 0xFF) ? 1 : 2; // 1 = solved, 2 = next cell found
}

bool SudokuGen::fillBoard(uint8_t board[9][9]) {
    uint8_t stackR[81];
    uint8_t stackC[81];
    uint8_t stackCount[81];
    uint8_t stackIdx[81];
    uint8_t stackVals[81][9];

    auto pushCell = [&](int8_t depth) -> uint8_t {
        uint8_t r, c;
        uint16_t mask;
        uint8_t st = findSudokuMrv(board, r, c, mask);
        if (st != 2) return st;

        uint8_t n = 0;
        for (uint8_t v = 1; v <= 9; v++) {
            if (mask & (1u << v)) stackVals[depth][n++] = v;
        }
        mp_shuffle(stackVals[depth], n);
        stackR[depth] = r;
        stackC[depth] = c;
        stackCount[depth] = n;
        stackIdx[depth] = 0;
        return 2;
    };

    int8_t sp = 0;
    uint8_t initSt = pushCell(0);
    if (initSt == 1) return true;
    if (initSt == 0) return false;

    uint32_t nodes = 0;
    const uint32_t MAX_NODES = 25000;

    while (sp >= 0) {
        if ((++nodes & 0xFF) == 0) yield();
        if (nodes >= MAX_NODES) {
            for (int8_t k = 0; k <= sp; k++) board[stackR[k]][stackC[k]] = 0;
            return false;
        }

        uint8_t r = stackR[sp];
        uint8_t c = stackC[sp];
        board[r][c] = 0;

        if (stackIdx[sp] >= stackCount[sp]) {
            sp--;
            continue;
        }

        board[r][c] = stackVals[sp][stackIdx[sp]++];
        if (sp + 1 >= 81) return true;

        uint8_t nextSt = pushCell(sp + 1);
        if (nextSt == 1) return true;
        if (nextSt == 2) sp++;
    }
    return false;
}

uint8_t SudokuGen::countSolutions(uint8_t board[9][9], uint8_t maxCount) {
    struct CountFrame {
        uint16_t mask;
        uint8_t r;
        uint8_t c;
        uint8_t nextVal;
    };
    CountFrame stack[81];

    uint8_t r0, c0;
    uint16_t m0;
    uint8_t st0 = findSudokuMrv(board, r0, c0, m0);
    if (st0 == 0) return 0;
    if (st0 == 1) return 1;

    int8_t sp = 0;
    stack[0] = { m0, r0, c0, 1 };

    uint8_t count = 0;
    uint32_t nodes = 0;
    const uint32_t MAX_NODES = 25000;

    while (sp >= 0) {
        if ((++nodes & 0xFF) == 0) yield();
        if (nodes >= MAX_NODES) {
            for (int8_t k = 0; k <= sp; k++) board[stack[k].r][stack[k].c] = 0;
            return maxCount;
        }

        CountFrame& f = stack[sp];
        board[f.r][f.c] = 0;

        uint8_t v = f.nextVal;
        while (v <= 9 && !(f.mask & (1u << v))) v++;
        if (v > 9) {
            sp--;
            continue;
        }
        f.nextVal = v + 1;
        board[f.r][f.c] = v;

        uint8_t nr, nc;
        uint16_t nm;
        uint8_t nst = findSudokuMrv(board, nr, nc, nm);
        if (nst == 1) {
            count++;
            if (count >= maxCount) {
                for (int8_t k = 0; k <= sp; k++) board[stack[k].r][stack[k].c] = 0;
                return count;
            }
        } else if (nst == 2 && sp + 1 < 81) {
            sp++;
            stack[sp] = { nm, nr, nc, 1 };
        }
    }
    return count;
}

void SudokuGen::generate(SudokuDifficulty difficulty) {
    uint8_t targetClues = 30;
    if (difficulty == SUDOKU_EASY) targetClues = 38;
    else if (difficulty == SUDOKU_HARD) targetClues = 25;

    // 1. Fill random solved board
    uint8_t solution[9][9] = {0};
    for (uint8_t attempt = 0; attempt < 5; attempt++) {
        memset(solution, 0, sizeof(solution));
        if (fillBoard(solution)) break;
        yield();
    }

    // 2. Clone to puzzle
    memcpy(_puzzle, solution, sizeof(_puzzle));

    // 3. Prepare list of 81 coordinates
    uint8_t cells[81];
    for (uint8_t i = 0; i < 81; i++) cells[i] = i;
    mp_shuffle(cells, 81);

    _cluesCount = 81;
    for (uint8_t i = 0; i < 81; i++) {
        if (_cluesCount <= targetClues) break;

        uint8_t pos = cells[i];
        uint8_t r = pos / 9;
        uint8_t c = pos % 9;

        uint8_t backup = _puzzle[r][c];
        _puzzle[r][c] = 0;

        // Check if solution remains unique
        if (countSolutions(_puzzle, 2) != 1) {
            _puzzle[r][c] = backup; // Restore
        } else {
            _cluesCount--;
        }
    }
}

void SudokuGen::printToReceipt(EscPosPrinter& printer, SudokuDifficulty /*diff*/) {
    printer.println("   +-------+-------+-------+");
    for (uint8_t r = 0; r < 9; r++) {
        String line = "   | ";
        for (uint8_t c = 0; c < 9; c++) {
            uint8_t val = _puzzle[r][c];
            if (val == 0) line += ". ";
            else line += String(val) + " ";
            if (c == 2 || c == 5) line += "| ";
        }
        line += "|";
        printer.println(line);

        if (r == 2 || r == 5) {
            printer.println("   +-------+-------+-------+");
        }
    }
    printer.println("   +-------+-------+-------+");
    printer.println("");
}

bool SudokuGen::printRasterToReceipt(EscPosPrinter& printer, SudokuDifficulty /*diff*/) {
    const int16_t padding = 24;
    const int16_t boardSize = THERMAL_CANVAS_WIDTH - padding * 2; // 528
    const int16_t cellSize = boardSize / 9; // 58
    const int16_t totalH = ((padding + cellSize * 9 + padding + 7) / 8) * 8; // 576

    ThermalCanvas canvas;
    return canvas.renderBanded(printer, totalH, [&](ThermalCanvas& canvas) {
        for (int i = 0; i <= 9; i++) {
            int16_t pos = padding + i * cellSize;
            bool isMajor = (i % 3 == 0);
            canvas.drawHLine(padding, pos, cellSize * 9, isMajor ? 4 : 1);
            canvas.drawVLine(pos, padding, cellSize * 9, isMajor ? 4 : 1);
        }

        for (uint8_t r = 0; r < 9; r++) {
            for (uint8_t c = 0; c < 9; c++) {
                uint8_t val = _puzzle[r][c];
                if (val != 0) {
                    int16_t cx = padding + c * cellSize + (cellSize - 18) / 2;
                    int16_t cy = padding + r * cellSize + (cellSize - 21) / 2;
                    canvas.drawChar(cx, cy, '0' + val, 3);
                }
            }
        }
    });
}

