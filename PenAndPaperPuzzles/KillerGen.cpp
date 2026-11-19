#include "KillerGen.h"
#include "KillerDataset.h"
#include "GeneratorUtils.h"
#include "EscPosPrinter.h"
#include "ThermalCanvas.h"

KillerGen::KillerGen() : _size(4), _boxRows(2), _boxCols(2), _numCages(0) {
    memset(_cageMap, 0, sizeof(_cageMap));
#ifdef HOST_TEST
    memset(_solution, 0, sizeof(_solution));
#endif
    memset(_cageSums, 0, sizeof(_cageSums));
}

void KillerGen::applyTransform(uint8_t transform) {
    if (transform == 0) return;
    uint8_t tempMap[MAX_SIZE][MAX_SIZE];
#ifdef HOST_TEST
    uint8_t tempSol[MAX_SIZE][MAX_SIZE];
#endif
    for (uint8_t r = 0; r < _size; r++) {
        for (uint8_t c = 0; c < _size; c++) {
            uint8_t nr, nc;
            mp_transform_coord_d4(r, c, _size, transform, nr, nc, false);
            tempMap[nr][nc] = _cageMap[r][c];
#ifdef HOST_TEST
            tempSol[nr][nc] = _solution[r][c];
#endif
        }
    }
    memcpy(_cageMap, tempMap, sizeof(_cageMap));
#ifdef HOST_TEST
    memcpy(_solution, tempSol, sizeof(_solution));
#endif
}

void KillerGen::generate(KillerDifficulty difficulty, uint32_t seed) {
    if (seed == 0) {
        seed = (uint32_t)random(800);
    }
    uint16_t puzzleIdx = (seed / 8) % 100;

    if (difficulty == KILLER_EASY || difficulty == KILLER_MEDIUM) {
        _size = 4;
        _boxRows = 2;
        _boxCols = 2;
        uint8_t transform = seed % 8;

        const Killer4x4Entry* entry = (difficulty == KILLER_EASY)
            ? &KILLER_EASY_DATASET[puzzleIdx]
            : &KILLER_MEDIUM_DATASET[puzzleIdx];
        _numCages = pgm_read_byte(&entry->num_cages);
        for (uint8_t i = 0; i < 16; i++) {
            _cageMap[i / 4][i % 4] = mp_unpack_nibble_pgm(entry->cage_map, i);
#ifdef HOST_TEST
            _solution[i / 4][i % 4] = mp_unpack_nibble_pgm(entry->solution, i);
#endif
        }
        for (uint8_t c = 0; c < _numCages && c < MAX_CAGES; c++) {
            _cageSums[c] = pgm_read_byte(&entry->cage_sums[c]);
        }
        applyTransform(transform);
    } else {
        _size = 6;
        _boxRows = 2;
        _boxCols = 3;
        // Box-preserving symmetries: 0 (identity), 2 (180 rot), 4 (h-flip), 6 (v-flip)
        uint8_t transform = (seed % 4) * 2;

        const Killer6x6Entry* entry = (difficulty == KILLER_HARD)
            ? &KILLER_HARD_DATASET[puzzleIdx]
            : &KILLER_EXTREME_DATASET[puzzleIdx];
        _numCages = pgm_read_byte(&entry->num_cages);
        for (uint8_t i = 0; i < 36; i++) {
            _cageMap[i / 6][i % 6] = mp_unpack_nibble_pgm(entry->cage_map, i);
#ifdef HOST_TEST
            _solution[i / 6][i % 6] = mp_unpack_nibble_pgm(entry->solution, i);
#endif
        }
        for (uint8_t c = 0; c < _numCages && c < MAX_CAGES; c++) {
            _cageSums[c] = pgm_read_byte(&entry->cage_sums[c]);
        }
        applyTransform(transform);
    }
}

void KillerGen::printToReceipt(EscPosPrinter& printer) {
    const char letters[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

    char sepBorder[48];
    size_t spos = snprintf(sepBorder, sizeof(sepBorder), "      +");
    for (uint8_t c = 0; c < _size && spos + 4 < sizeof(sepBorder); c++) {
        spos += snprintf(sepBorder + spos, sizeof(sepBorder) - spos, "---+");
    }
    printer.println(sepBorder);

    char rowBuf[48];
    for (uint8_t r = 0; r < _size; r++) {
        size_t rpos = snprintf(rowBuf, sizeof(rowBuf), "      |");
        for (uint8_t c = 0; c < _size && rpos + 4 < sizeof(rowBuf); c++) {
            char label = letters[_cageMap[r][c] % 26];
            rpos += snprintf(rowBuf + rpos, sizeof(rowBuf) - rpos, " %c |", label);
        }
        printer.println(rowBuf);
        printer.println(sepBorder);
    }
    printer.println("");

    // Cage sums legend wrapped to <= 44 columns
    char curLine[64];
    size_t clen = snprintf(curLine, sizeof(curLine), "CAGES: ");
    for (uint8_t c = 0; c < _numCages; c++) {
        char item[16];
        size_t ilen = snprintf(item, sizeof(item), "%c=%d%s", letters[c % 26], (int)_cageSums[c],
                               (c + 1 < _numCages) ? ", " : "");
        if (clen + ilen > 44) {
            printer.println(curLine);
            clen = snprintf(curLine, sizeof(curLine), "       %s", item);
        } else {
            memcpy(curLine + clen, item, ilen + 1);
            clen += ilen;
        }
    }
    if (clen > 7) {
        printer.println(curLine);
    }
    printer.println("");
}

bool KillerGen::printRasterToReceipt(EscPosPrinter& printer) {
    const int16_t padding = 24;
    const int16_t boardSize = THERMAL_CANVAS_WIDTH - padding * 2;
    const int16_t cellSize = boardSize / _size;
    const int16_t actualBoard = cellSize * _size;
    const int16_t totalH = padding + actualBoard + padding;
    const int16_t inset = (_size == 4) ? 10 : 8;
    const int16_t dashLen = 8;
    const int16_t gapLen = 6;
    const int16_t step = dashLen + gapLen;

    ThermalCanvas canvas;
    return canvas.renderBanded(printer, totalH, [&](ThermalCanvas& canvas) {
        canvas.drawGrid(padding, padding, _size, _size, cellSize, cellSize, 4, 2, _boxRows, _boxCols, 4);

        for (uint8_t r = 0; r < _size; r++) {
            for (uint8_t c = 0; c < _size; c++) {
                uint8_t cid = _cageMap[r][c];
                int16_t x0 = padding + c * cellSize + inset;
                int16_t y0 = padding + r * cellSize + inset;
                int16_t x1 = padding + (c + 1) * cellSize - inset;
                int16_t y1 = padding + (r + 1) * cellSize - inset;

                if (r == 0 || _cageMap[r - 1][c] != cid) {
                    canvas.drawDashedHLine(x0, y0, x1 - x0, dashLen, gapLen, 2);
                }
                if (r == _size - 1 || _cageMap[r + 1][c] != cid) {
                    canvas.drawDashedHLine(x0, y1, x1 - x0, dashLen, gapLen, 2);
                }
                if (c == 0 || _cageMap[r][c - 1] != cid) {
                    for (int16_t y = y0; y < y1; y += step) {
                        int16_t seg = ((y + dashLen) > y1) ? (y1 - y) : dashLen;
                        canvas.drawVLine(x0, y, seg, 2);
                    }
                }
                if (c == _size - 1 || _cageMap[r][c + 1] != cid) {
                    for (int16_t y = y0; y < y1; y += step) {
                        int16_t seg = ((y + dashLen) > y1) ? (y1 - y) : dashLen;
                        canvas.drawVLine(x1, y, seg, 2);
                    }
                }
            }
        }

        for (uint8_t cid = 0; cid < _numCages; cid++) {
            int8_t minR = -1;
            int8_t minC = -1;
            for (uint8_t r = 0; r < _size && minR == -1; r++) {
                for (uint8_t c = 0; c < _size; c++) {
                    if (_cageMap[r][c] == cid) {
                        minR = r;
                        minC = c;
                        break;
                    }
                }
            }
            if (minR != -1) {
                int16_t tx = padding + minC * cellSize + inset + 8;
                int16_t ty = padding + minR * cellSize + inset + 8;
                char sumStr[8];
                snprintf(sumStr, sizeof(sumStr), "%d", (int)_cageSums[cid]);
                canvas.drawText(tx, ty, sumStr, 2);
            }
        }
    });
}
