#include "QueensGen.h"
#include "StarsDataset.h"
#include "GeneratorUtils.h"
#include "../printer/EscPosPrinter.h"
#include "../printer/ThermalCanvas.h"

QueensGen::QueensGen() : _size(8), _starsPerUnit(1)
#ifdef HOST_TEST
    , _numStars(0)
#endif
{
    memset(_regions, -1, sizeof(_regions));
}

void QueensGen::applyTransform(uint8_t transform) {
    if (transform == 0) return;

    int8_t temp[MAX_SIZE][MAX_SIZE];
    for (uint8_t r = 0; r < _size; r++) {
        for (uint8_t c = 0; c < _size; c++) {
            uint8_t nr, nc;
            mp_transform_coord_d4(r, c, _size, transform, nr, nc, false);
            temp[nr][nc] = _regions[r][c];
        }
    }
    memcpy(_regions, temp, sizeof(_regions));

#ifdef HOST_TEST
    for (uint8_t s = 0; s < _numStars; s++) {
        uint8_t nr, nc;
        mp_transform_coord_d4(_stars[s].row, _stars[s].col, _size, transform, nr, nc, false);
        _stars[s].row = nr;
        _stars[s].col = nc;
    }
#endif
}

void QueensGen::generate(QueensDifficulty difficulty, uint32_t seed) {
    if (seed == 0) {
        seed = (uint32_t)random(800);
    }
    uint16_t puzzleIdx = (seed / 8) % 100;
    uint8_t transform = seed % 8;

    const uint8_t* regionsData = nullptr;
#ifdef HOST_TEST
    const uint8_t* solutionsData = nullptr;
#endif

    if (difficulty == QUEENS_EASY) {
        _size = 5;
        _starsPerUnit = 1;
        regionsData = &STARS_EASY_REGIONS[puzzleIdx][0];
#ifdef HOST_TEST
        solutionsData = &STARS_EASY_SOLUTIONS[puzzleIdx][0];
#endif
    } else if (difficulty == QUEENS_HARD) {
        _size = 9;
        _starsPerUnit = 2;
        regionsData = &STARS_HARD_REGIONS[puzzleIdx][0];
#ifdef HOST_TEST
        solutionsData = &STARS_HARD_SOLUTIONS[puzzleIdx][0];
#endif
    } else if (difficulty == QUEENS_MASTER) {
        _size = 10;
        _starsPerUnit = 2;
        regionsData = &STARS_EXTREME_REGIONS[puzzleIdx][0];
#ifdef HOST_TEST
        solutionsData = &STARS_EXTREME_SOLUTIONS[puzzleIdx][0];
#endif
    } else { // QUEENS_MEDIUM
        _size = 8;
        _starsPerUnit = 1;
        regionsData = &STARS_MEDIUM_REGIONS[puzzleIdx][0];
#ifdef HOST_TEST
        solutionsData = &STARS_MEDIUM_SOLUTIONS[puzzleIdx][0];
#endif
    }

    // Unpack 4-bit nibble regions (2 cells per byte)
    for (uint8_t r = 0; r < _size; r++) {
        for (uint8_t c = 0; c < _size; c++) {
            _regions[r][c] = mp_unpack_nibble_pgm(regionsData, r * _size + c);
        }
    }

#ifdef HOST_TEST
    _numStars = _size * _starsPerUnit;
    // Unpack packed star coordinates: (row << 4) | col
    for (uint8_t i = 0; i < _numStars; i++) {
        uint8_t packed = pgm_read_byte(solutionsData + i);
        _stars[i].row = packed >> 4;
        _stars[i].col = packed & 0x0F;
    }
#endif

    applyTransform(transform);
}

void QueensGen::printToReceipt(EscPosPrinter& printer) {
    // Column numbers header
    String header = "     ";
    for (uint8_t c = 0; c < _size; c++) {
        header += String(c + 1) + " ";
    }
    printer.println(header);

    String divLine = "    +";
    for (uint8_t c = 0; c < _size; c++) divLine += "--";
    printer.println(divLine);

    // Grid rows with region letters
    const char letters[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    for (uint8_t r = 0; r < _size; r++) {
        String line = "  " + String(r + 1) + " |";
        for (uint8_t c = 0; c < _size; c++) {
            int8_t reg = _regions[r][c];
            char label = letters[reg % 26];
            line += " ";
            line += label;
        }
        printer.println(line);
    }
    printer.println("");
}

bool QueensGen::printRasterToReceipt(EscPosPrinter& printer) {
    const int16_t padding = 24;
    const int16_t boardSize = THERMAL_CANVAS_WIDTH - padding * 2;
    const int16_t cellSize = boardSize / _size;
    const int16_t totalH = ((padding + cellSize * _size + padding + 7) / 8) * 8;

    ThermalCanvas canvas;
    return canvas.renderBanded(printer, totalH, [&](ThermalCanvas& canvas) {
        for (uint8_t r = 0; r < _size; r++) {
            for (uint8_t c = 0; c < _size; c++) {
                int8_t reg = _regions[r][c];
                if (reg >= 0) {
                    int16_t x0 = padding + c * cellSize;
                    int16_t y0 = padding + r * cellSize;
                    canvas.fillHatch(x0, y0, cellSize, cellSize, reg);
                }
            }
        }

        for (uint8_t r = 0; r < _size; r++) {
            for (uint8_t c = 0; c < _size; c++) {
                int8_t reg = _regions[r][c];
                int16_t x0 = padding + c * cellSize;
                int16_t y0 = padding + r * cellSize;
                bool isBottom = (r == _size - 1) || (r + 1 < _size && _regions[r + 1][c] != reg);
                canvas.drawHLine(x0, y0 + cellSize, cellSize, isBottom ? 4 : 1);

                bool isRight = (c == _size - 1) || (c + 1 < _size && _regions[r][c + 1] != reg);
                canvas.drawVLine(x0 + cellSize, y0, cellSize, isRight ? 4 : 1);
            }
        }

        canvas.drawRect(padding, padding, cellSize * _size, cellSize * _size, 5);
    });
}
