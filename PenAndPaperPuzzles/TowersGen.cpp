#include "TowersGen.h"
#include "TowersDataset.h"
#include "GeneratorUtils.h"
#include "EscPosPrinter.h"
#include "ThermalCanvas.h"

TowersGen::TowersGen() : _size(5), _cellSize(72), _height(440) {
#ifdef HOST_TEST
    memset(_solution, 0, sizeof(_solution));
#endif
    memset(_top, 0, sizeof(_top));
    memset(_bottom, 0, sizeof(_bottom));
    memset(_left, 0, sizeof(_left));
    memset(_right, 0, sizeof(_right));
}

void TowersGen::applyTransform(uint8_t transform) {
    if (transform == 0) return;
    uint8_t rot = transform % 4;
    bool flip = (transform >= 4);

#ifdef HOST_TEST
    uint8_t tempSol[MAX_SIZE][MAX_SIZE];
    for (uint8_t r = 0; r < _size; r++) {
        for (uint8_t c = 0; c < _size; c++) {
            uint8_t nr, nc;
            mp_transform_coord_d4(r, c, _size, transform, nr, nc, true);
            tempSol[nr][nc] = _solution[r][c];
        }
    }
    memcpy(_solution, tempSol, sizeof(_solution));
#endif

    if (flip) {
        uint8_t tempTop[MAX_SIZE], tempBot[MAX_SIZE], tempLeft[MAX_SIZE], tempRight[MAX_SIZE];
        for (uint8_t i = 0; i < _size; i++) {
            tempTop[_size - 1 - i] = _top[i];
            tempBot[_size - 1 - i] = _bottom[i];
            tempLeft[i] = _right[i];
            tempRight[i] = _left[i];
        }
        memcpy(_top, tempTop, sizeof(_top));
        memcpy(_bottom, tempBot, sizeof(_bottom));
        memcpy(_left, tempLeft, sizeof(_left));
        memcpy(_right, tempRight, sizeof(_right));
    }

    for (uint8_t k = 0; k < rot; k++) {
        uint8_t newTop[MAX_SIZE], newRight[MAX_SIZE], newBottom[MAX_SIZE], newLeft[MAX_SIZE];
        for (uint8_t i = 0; i < _size; i++) {
            newTop[i] = _left[_size - 1 - i];
            newRight[i] = _top[i];
            newBottom[i] = _right[_size - 1 - i];
            newLeft[i] = _bottom[i];
        }
        memcpy(_top, newTop, sizeof(_top));
        memcpy(_right, newRight, sizeof(_right));
        memcpy(_bottom, newBottom, sizeof(_bottom));
        memcpy(_left, newLeft, sizeof(_left));
    }
}

void TowersGen::generate(TowersDifficulty difficulty, uint32_t seed) {
    if (seed == 0) {
        seed = (uint32_t)random(800);
    }
    uint16_t puzzleIdx = (seed / 8) % 100;
    uint8_t transform = seed % 8;

#ifdef HOST_TEST
    memset(_solution, 0, sizeof(_solution));
#endif
    memset(_top, 0, sizeof(_top));
    memset(_bottom, 0, sizeof(_bottom));
    memset(_left, 0, sizeof(_left));
    memset(_right, 0, sizeof(_right));

    if (difficulty == TOWERS_EASY || difficulty == TOWERS_MEDIUM) {
        _size = 4;
        _cellSize = 80;
        _height = 400;
        const Towers4x4Entry* p = (difficulty == TOWERS_EASY) ? &TOWERS_EASY_DATASET[puzzleIdx] : &TOWERS_MEDIUM_DATASET[puzzleIdx];
#ifdef HOST_TEST
        for (uint8_t r = 0; r < 4; r++) {
            for (uint8_t c = 0; c < 4; c++) {
                _solution[r][c] = mp_unpack_nibble_pgm(p->solution, r * 4 + c);
            }
        }
#endif
        for (uint8_t i = 0; i < 4; i++) {
            _top[i] = mp_unpack_nibble_pgm(p->clues, i);
            _bottom[i] = mp_unpack_nibble_pgm(p->clues, 4 + i);
            _left[i] = mp_unpack_nibble_pgm(p->clues, 8 + i);
            _right[i] = mp_unpack_nibble_pgm(p->clues, 12 + i);
        }
    } else { // TOWERS_HARD or TOWERS_EXTREME (5x5)
        _size = 5;
        _cellSize = 72;
        _height = 440;
        const Towers5x5Entry* p = (difficulty == TOWERS_HARD) ? &TOWERS_HARD_DATASET[puzzleIdx] : &TOWERS_EXTREME_DATASET[puzzleIdx];
#ifdef HOST_TEST
        for (uint8_t r = 0; r < 5; r++) {
            for (uint8_t c = 0; c < 5; c++) {
                _solution[r][c] = mp_unpack_nibble_pgm(p->solution, r * 5 + c);
            }
        }
#endif
        for (uint8_t i = 0; i < 5; i++) {
            _top[i] = mp_unpack_nibble_pgm(p->clues, i);
            _bottom[i] = mp_unpack_nibble_pgm(p->clues, 5 + i);
            _left[i] = mp_unpack_nibble_pgm(p->clues, 10 + i);
            _right[i] = mp_unpack_nibble_pgm(p->clues, 15 + i);
        }
    }

    applyTransform(transform);
}

void TowersGen::printToReceipt(EscPosPrinter& printer) {
    String topStr = "       ";
    for (uint8_t c = 0; c < _size; c++) {
        if (_top[c] > 0) topStr += String(_top[c]) + " ";
        else topStr += "  ";
    }
    printer.println(topStr);

    String sep = "     +";
    for (uint8_t c = 0; c < _size; c++) sep += "---+";
    printer.println(sep);

    for (uint8_t r = 0; r < _size; r++) {
        char lChar = (_left[r] > 0) ? (char)('0' + _left[r]) : ' ';
        char rChar = (_right[r] > 0) ? (char)('0' + _right[r]) : ' ';
        String line = String("   ") + lChar + " |";
        for (uint8_t c = 0; c < _size; c++) {
            line += "   |";
        }
        line += String(" ") + rChar;
        printer.println(line);
        printer.println(sep);
    }

    String botStr = "       ";
    for (uint8_t c = 0; c < _size; c++) {
        if (_bottom[c] > 0) botStr += String(_bottom[c]) + " ";
        else botStr += "  ";
    }
    printer.println(botStr);
}

bool TowersGen::printRasterToReceipt(EscPosPrinter& printer) {
    uint16_t grid_w = _size * _cellSize;
    uint16_t grid_x = (576 - grid_w) / 2;
    uint16_t grid_y = (_height - grid_w) / 2;

    ThermalCanvas canvas;
    return canvas.renderBanded(printer, _height, [&](ThermalCanvas& canvas) {
        canvas.drawGrid(grid_x, grid_y, _size, _size, _cellSize, _cellSize, 4, 1);

        for (uint8_t c = 0; c < _size; c++) {
            if (_top[c] > 0) {
                uint16_t cx = grid_x + c * _cellSize + (_cellSize - 12) / 2;
                uint16_t cy = grid_y - 20;
                char str[2] = { (char)('0' + _top[c]), '\0' };
                canvas.drawText(cx, cy, str, 2);
            }
            if (_bottom[c] > 0) {
                uint16_t cx = grid_x + c * _cellSize + (_cellSize - 12) / 2;
                uint16_t cy = grid_y + grid_w + 6;
                char str[2] = { (char)('0' + _bottom[c]), '\0' };
                canvas.drawText(cx, cy, str, 2);
            }
        }

        for (uint8_t r = 0; r < _size; r++) {
            if (_left[r] > 0) {
                uint16_t cx = grid_x - 18;
                uint16_t cy = grid_y + r * _cellSize + (_cellSize - 14) / 2;
                char str[2] = { (char)('0' + _left[r]), '\0' };
                canvas.drawText(cx, cy, str, 2);
            }
            if (_right[r] > 0) {
                uint16_t cx = grid_x + grid_w + 6;
                uint16_t cy = grid_y + r * _cellSize + (_cellSize - 14) / 2;
                char str[2] = { (char)('0' + _right[r]), '\0' };
                canvas.drawText(cx, cy, str, 2);
            }
        }
    });
}
