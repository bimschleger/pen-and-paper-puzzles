#include "SudokitoGen.h"
#include "GeneratorUtils.h"
#include "EscPosPrinter.h"
#include "ThermalCanvas.h"

SudokitoGen::SudokitoGen() : _cluesCount(36) {
    memset(_puzzle, 0, sizeof(_puzzle));
}

bool SudokitoGen::isValid(uint8_t board[6][6], uint8_t row, uint8_t col, uint8_t num) {
    for (uint8_t i = 0; i < 6; i++) {
        if (board[row][i] == num || board[i][col] == num) {
            return false;
        }
    }
    uint8_t boxR = (row / 2) * 2;
    uint8_t boxC = (col / 3) * 3;
    for (uint8_t r = boxR; r < boxR + 2; r++) {
        for (uint8_t c = boxC; c < boxC + 3; c++) {
            if (board[r][c] == num) {
                return false;
            }
        }
    }
    return true;
}

static uint8_t findSudokitoMrv(uint8_t board[6][6], uint8_t& bestR, uint8_t& bestC, uint8_t& bestMask) {
    uint8_t bestCandCount = 7;
    bestR = 0xFF;
    bestC = 0xFF;
    bestMask = 0;

    for (uint8_t r = 0; r < 6; r++) {
        for (uint8_t c = 0; c < 6; c++) {
            if (board[r][c] == 0) {
                uint8_t mask = 0;
                uint8_t cnt = 0;
                for (uint8_t num = 1; num <= 6; num++) {
                    bool ok = true;
                    for (uint8_t i = 0; i < 6; i++) {
                        if (board[r][i] == num || board[i][c] == num) { ok = false; break; }
                    }
                    if (ok) {
                        uint8_t br = (r / 2) * 2, bc = (c / 3) * 3;
                        for (uint8_t dr = 0; dr < 2 && ok; dr++) {
                            for (uint8_t dc = 0; dc < 3; dc++) {
                                if (board[br + dr][bc + dc] == num) { ok = false; break; }
                            }
                        }
                    }
                    if (ok) {
                        mask |= (uint8_t)(1u << num);
                        cnt++;
                    }
                }
                if (cnt == 0) return 0;
                if (cnt < bestCandCount) {
                    bestCandCount = cnt;
                    bestR = r;
                    bestC = c;
                    bestMask = mask;
                    if (cnt == 1) return 2;
                }
            }
        }
    }
    return (bestR == 0xFF) ? 1 : 2;
}

bool SudokitoGen::fillBoard(uint8_t board[6][6]) {
    uint8_t stackR[36];
    uint8_t stackC[36];
    uint8_t stackCount[36];
    uint8_t stackIdx[36];
    uint8_t stackVals[36][6];

    auto pushCell = [&](int8_t depth) -> uint8_t {
        uint8_t r, c, mask;
        uint8_t st = findSudokitoMrv(board, r, c, mask);
        if (st != 2) return st;

        uint8_t n = 0;
        for (uint8_t v = 1; v <= 6; v++) {
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
        if (sp + 1 >= 36) return true;

        uint8_t nextSt = pushCell(sp + 1);
        if (nextSt == 1) return true;
        if (nextSt == 2) sp++;
    }
    return false;
}

uint8_t SudokitoGen::countSolutions(uint8_t board[6][6], uint8_t maxCount) {
    struct CountFrame {
        uint8_t mask;
        uint8_t r;
        uint8_t c;
        uint8_t nextVal;
    };
    CountFrame stack[36];

    uint8_t r0, c0, m0;
    uint8_t st0 = findSudokitoMrv(board, r0, c0, m0);
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
        while (v <= 6 && !(f.mask & (1u << v))) v++;
        if (v > 6) {
            sp--;
            continue;
        }
        f.nextVal = v + 1;
        board[f.r][f.c] = v;

        uint8_t nr, nc, nm;
        uint8_t nst = findSudokitoMrv(board, nr, nc, nm);
        if (nst == 1) {
            count++;
            if (count >= maxCount) {
                for (int8_t k = 0; k <= sp; k++) board[stack[k].r][stack[k].c] = 0;
                return count;
            }
        } else if (nst == 2 && sp + 1 < 36) {
            sp++;
            stack[sp] = { nm, nr, nc, 1 };
        }
    }
    return count;
}

void SudokitoGen::generate(SudokitoDifficulty difficulty) {
    uint8_t targetClues = 14;
    if (difficulty == SUDOKITO_EASY) targetClues = 18;
    else if (difficulty == SUDOKITO_HARD) targetClues = 11;

    // 1. Fill random solved 6x6 board
    uint8_t solution[6][6] = {0};
    for (uint8_t attempt = 0; attempt < 5; attempt++) {
        memset(solution, 0, sizeof(solution));
        if (fillBoard(solution)) break;
        yield();
    }

    // 2. Clone to puzzle
    memcpy(_puzzle, solution, sizeof(_puzzle));

    // 3. Prepare 18 cell pairs with 180-degree rotational symmetry:
    // Pair i corresponds to (r, c) and (5 - r, 5 - c)
    uint8_t pairCoords[18][2];
    uint8_t pairCount = 0;
    bool visited[6][6] = {false};

    for (uint8_t r = 0; r < 6; r++) {
        for (uint8_t c = 0; c < 6; c++) {
            if (!visited[r][c]) {
                pairCoords[pairCount][0] = r * 6 + c;
                pairCoords[pairCount][1] = (5 - r) * 6 + (5 - c);
                visited[r][c] = true;
                visited[5 - r][5 - c] = true;
                pairCount++;
            }
        }
    }

    uint8_t pairOrder[18];
    for (uint8_t i = 0; i < 18; i++) pairOrder[i] = i;
    mp_shuffle(pairOrder, 18);

    _cluesCount = 36;
    for (uint8_t i = 0; i < 18; i++) {
        if (_cluesCount <= targetClues) break;

        uint8_t pIdx = pairOrder[i];
        uint8_t c1 = pairCoords[pIdx][0];
        uint8_t c2 = pairCoords[pIdx][1];

        uint8_t r1 = c1 / 6, col1 = c1 % 6;
        uint8_t r2 = c2 / 6, col2 = c2 % 6;

        uint8_t backup1 = _puzzle[r1][col1];
        uint8_t backup2 = _puzzle[r2][col2];

        _puzzle[r1][col1] = 0;
        _puzzle[r2][col2] = 0;

        if (countSolutions(_puzzle, 2) != 1) {
            _puzzle[r1][col1] = backup1;
            _puzzle[r2][col2] = backup2;
        } else {
            _cluesCount -= 2;
        }
    }

    // Secondary pass for odd targets (e.g. 11 clues)
    if (_cluesCount > targetClues) {
        uint8_t singles[36];
        uint8_t sCount = 0;
        for (uint8_t i = 0; i < 36; i++) {
            if (_puzzle[i / 6][i % 6] != 0) {
                singles[sCount++] = i;
            }
        }
        mp_shuffle(singles, sCount);
        for (uint8_t i = 0; i < sCount; i++) {
            if (_cluesCount <= targetClues) break;
            uint8_t pos = singles[i];
            uint8_t r = pos / 6, c = pos % 6;
            uint8_t backup = _puzzle[r][c];
            _puzzle[r][c] = 0;
            if (countSolutions(_puzzle, 2) != 1) {
                _puzzle[r][c] = backup;
            } else {
                _cluesCount--;
            }
        }
    }
}

void SudokitoGen::printToReceipt(EscPosPrinter& printer, SudokitoDifficulty /*diff*/) {
    printer.println("      +-------+-------+");
    for (uint8_t r = 0; r < 6; r++) {
        String line = "      | ";
        for (uint8_t c = 0; c < 6; c++) {
            uint8_t val = _puzzle[r][c];
            if (val == 0) line += ". ";
            else line += String(val) + " ";
            if (c == 2) line += "| ";
        }
        line += "|";
        printer.println(line);

        if (r == 1 || r == 3) {
            printer.println("      +-------+-------+");
        }
    }
    printer.println("      +-------+-------+");
    printer.println("");
}

bool SudokitoGen::printRasterToReceipt(EscPosPrinter& printer, SudokitoDifficulty /*diff*/) {
    const int16_t padding = 24;
    const int16_t boardSize = THERMAL_CANVAS_WIDTH - padding * 2; // 528
    const int16_t cellSize = boardSize / 6; // 88
    const int16_t totalH = padding + cellSize * 6 + padding; // 576

    ThermalCanvas canvas;
    return canvas.renderBanded(printer, totalH, [&](ThermalCanvas& canvas) {
        for (int i = 0; i <= 6; i++) {
            int16_t pos = padding + i * cellSize;
            canvas.drawHLine(padding, pos, cellSize * 6, (i % 2 == 0) ? 4 : 1);
            canvas.drawVLine(pos, padding, cellSize * 6, (i % 3 == 0) ? 4 : 1);
        }

        for (uint8_t r = 0; r < 6; r++) {
            for (uint8_t c = 0; c < 6; c++) {
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
