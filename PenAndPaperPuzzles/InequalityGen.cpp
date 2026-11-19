#include "InequalityGen.h"
#include "InequalityDataset.h"
#include "GeneratorUtils.h"
#include "EscPosPrinter.h"
#include "ThermalCanvas.h"

InequalityGen::InequalityGen() : _size(5), _cellSize(88), _height(488) {
#ifdef HOST_TEST
    memset(_solution, 0, sizeof(_solution));
#endif
    memset(_givens, 0, sizeof(_givens));
    memset(_edges_h, 0, sizeof(_edges_h));
    memset(_edges_v, 0, sizeof(_edges_v));
}

void InequalityGen::applyTransform(uint8_t transform) {
    if (transform == 0) return;

#ifdef HOST_TEST
    uint8_t newSol[MAX_SIZE][MAX_SIZE];
    memset(newSol, 0, sizeof(newSol));
#endif
    uint8_t newGivens[MAX_SIZE][MAX_SIZE];
    memset(newGivens, 0, sizeof(newGivens));

    for (uint8_t r = 0; r < _size; r++) {
        for (uint8_t c = 0; c < _size; c++) {
            uint8_t nr, nc;
            mp_transform_coord_d4_ineq(r, c, _size, transform, nr, nc);
#ifdef HOST_TEST
            newSol[nr][nc] = _solution[r][c];
#endif
            newGivens[nr][nc] = _givens[r][c];
        }
    }

    uint8_t newEdgesH[MAX_SIZE][MAX_SIZE - 1];
    uint8_t newEdgesV[MAX_SIZE - 1][MAX_SIZE];
    memset(newEdgesH, 0, sizeof(newEdgesH));
    memset(newEdgesV, 0, sizeof(newEdgesV));

    auto mapEdge = [&](uint8_t r1, uint8_t c1, uint8_t r2, uint8_t c2, uint8_t edgeVal) {
        if (edgeVal == 0) return;
        uint8_t nr1, nc1, nr2, nc2;
        mp_transform_coord_d4_ineq(r1, c1, _size, transform, nr1, nc1);
        mp_transform_coord_d4_ineq(r2, c2, _size, transform, nr2, nc2);
        uint8_t v1 = (edgeVal == 1) ? 1 : 2;
        uint8_t v2 = (edgeVal == 1) ? 2 : 1;
        if (nr1 == nr2) {
            uint8_t cLeft = min(nc1, nc2);
            uint8_t valLeft = (nc1 < nc2) ? v1 : v2;
            uint8_t valRight = (nc1 < nc2) ? v2 : v1;
            newEdgesH[nr1][cLeft] = (valLeft < valRight) ? 1 : 2;
        } else {
            uint8_t rTop = min(nr1, nr2);
            uint8_t valTop = (nr1 < nr2) ? v1 : v2;
            uint8_t valBot = (nr1 < nr2) ? v2 : v1;
            newEdgesV[rTop][nc1] = (valTop < valBot) ? 1 : 2;
        }
    };

    for (uint8_t r = 0; r < _size; r++) {
        for (uint8_t c = 0; c < _size - 1; c++) {
            mapEdge(r, c, r, c + 1, _edges_h[r][c]);
        }
    }

    for (uint8_t r = 0; r < _size - 1; r++) {
        for (uint8_t c = 0; c < _size; c++) {
            mapEdge(r, c, r + 1, c, _edges_v[r][c]);
        }
    }

#ifdef HOST_TEST
    memcpy(_solution, newSol, sizeof(_solution));
#endif
    memcpy(_givens, newGivens, sizeof(_givens));
    memcpy(_edges_h, newEdgesH, sizeof(_edges_h));
    memcpy(_edges_v, newEdgesV, sizeof(_edges_v));
}

void InequalityGen::generate(InequalityDifficulty difficulty, uint32_t seed) {
    if (seed == 0) {
        seed = (uint32_t)random(800);
    }
    uint16_t puzzleIdx = (seed / 8) % 100;
    uint8_t transform = seed % 8;

#ifdef HOST_TEST
    memset(_solution, 0, sizeof(_solution));
#endif
    memset(_givens, 0, sizeof(_givens));
    memset(_edges_h, 0, sizeof(_edges_h));
    memset(_edges_v, 0, sizeof(_edges_v));

    _cellSize = 88;

    if (difficulty == INEQUALITY_EASY || difficulty == INEQUALITY_MEDIUM) {
        _size = 4;
        _height = 400;
        const Inequality4x4Entry* p = (difficulty == INEQUALITY_EASY) ? &INEQUALITY_EASY_DATASET[puzzleIdx] : &INEQUALITY_MEDIUM_DATASET[puzzleIdx];
        for (uint8_t r = 0; r < 4; r++) {
            for (uint8_t c = 0; c < 4; c++) {
                uint8_t idx = r * 4 + c;
#ifdef HOST_TEST
                _solution[r][c] = mp_unpack_nibble_pgm(p->solution, idx);
#endif
                _givens[r][c] = mp_unpack_nibble_pgm(p->givens, idx);
            }
        }
        for (uint8_t r = 0; r < 4; r++) {
            for (uint8_t c = 0; c < 3; c++) {
                _edges_h[r][c] = mp_unpack_2bit_pgm(p->edges_h, r * 3 + c);
            }
        }
        for (uint8_t r = 0; r < 3; r++) {
            for (uint8_t c = 0; c < 4; c++) {
                _edges_v[r][c] = mp_unpack_2bit_pgm(p->edges_v, r * 4 + c);
            }
        }
    } else { // INEQUALITY_HARD or INEQUALITY_EXTREME (5x5)
        _size = 5;
        _height = 488;
        const Inequality5x5Entry* p = (difficulty == INEQUALITY_HARD) ? &INEQUALITY_HARD_DATASET[puzzleIdx] : &INEQUALITY_EXTREME_DATASET[puzzleIdx];
        for (uint8_t r = 0; r < 5; r++) {
            for (uint8_t c = 0; c < 5; c++) {
                uint8_t idx = r * 5 + c;
#ifdef HOST_TEST
                _solution[r][c] = mp_unpack_nibble_pgm(p->solution, idx);
#endif
                _givens[r][c] = mp_unpack_nibble_pgm(p->givens, idx);
            }
        }
        for (uint8_t r = 0; r < 5; r++) {
            for (uint8_t c = 0; c < 4; c++) {
                _edges_h[r][c] = mp_unpack_2bit_pgm(p->edges_h, r * 4 + c);
            }
        }
        for (uint8_t r = 0; r < 4; r++) {
            for (uint8_t c = 0; c < 5; c++) {
                _edges_v[r][c] = mp_unpack_2bit_pgm(p->edges_v, r * 5 + c);
            }
        }
    }

    applyTransform(transform);
}

void InequalityGen::printToReceipt(EscPosPrinter& printer) {
    for (uint8_t r = 0; r < _size; r++) {
        char rowBuf[48];
        memset(rowBuf, ' ', 6);
        int pos = 6;
        for (uint8_t c = 0; c < _size && pos < (int)sizeof(rowBuf) - 4; c++) {
            rowBuf[pos++] = (_givens[r][c] > 0 && _givens[r][c] <= 9)
                ? (char)('0' + _givens[r][c])
                : '.';
            if (c < _size - 1) {
                uint8_t eh = _edges_h[r][c];
                rowBuf[pos++] = ' ';
                rowBuf[pos++] = (eh == 1) ? '<' : ((eh == 2) ? '>' : ' ');
                rowBuf[pos++] = ' ';
            }
        }
        rowBuf[pos] = '\0';
        printer.println((const char*)rowBuf);

        if (r < _size - 1) {
            char vBuf[48];
            memset(vBuf, ' ', 6);
            int vpos = 6;
            for (uint8_t c = 0; c < _size && vpos < (int)sizeof(vBuf) - 4; c++) {
                uint8_t ev = _edges_v[r][c];
                vBuf[vpos++] = (ev == 1) ? '^' : ((ev == 2) ? 'v' : ' ');
                if (c < _size - 1) {
                    vBuf[vpos++] = ' ';
                    vBuf[vpos++] = ' ';
                    vBuf[vpos++] = ' ';
                }
            }
            vBuf[vpos] = '\0';
            printer.println((const char*)vBuf);
        }
    }
}

bool InequalityGen::printRasterToReceipt(EscPosPrinter& printer) {
    uint16_t grid_w = _size * _cellSize;
    uint16_t grid_x = (576 - grid_w) / 2;
    uint16_t grid_y = (_height - grid_w) / 2;

    ThermalCanvas canvas;
    return canvas.renderBanded(printer, _height, [&](ThermalCanvas& canvas) {
        canvas.drawGrid(grid_x, grid_y, _size, _size, _cellSize, _cellSize, 4, 1);

        for (uint8_t r = 0; r < _size; r++) {
            for (uint8_t c = 0; c < _size - 1; c++) {
                uint8_t eh = _edges_h[r][c];
                if (eh == 1 || eh == 2) {
                    uint16_t cx = grid_x + (c + 1) * _cellSize;
                    uint16_t cy = grid_y + r * _cellSize + _cellSize / 2;
                    canvas.fillRect(cx - 12, cy - 12, 25, 25, 0);
                    if (eh == 1) { // <
                        for (int8_t d = 0; d < 8; d++) {
                            canvas.setPixel(cx - 4 + d, cy - d, 1);
                            canvas.setPixel(cx - 4 + d, cy - d + 1, 1);
                            canvas.setPixel(cx - 4 + d, cy + d, 1);
                            canvas.setPixel(cx - 4 + d, cy + d - 1, 1);
                        }
                    } else { // >
                        for (int8_t d = 0; d < 8; d++) {
                            canvas.setPixel(cx + 3 - d, cy - d, 1);
                            canvas.setPixel(cx + 3 - d, cy - d + 1, 1);
                            canvas.setPixel(cx + 3 - d, cy + d, 1);
                            canvas.setPixel(cx + 3 - d, cy + d - 1, 1);
                        }
                    }
                }
            }
        }

        for (uint8_t r = 0; r < _size - 1; r++) {
            for (uint8_t c = 0; c < _size; c++) {
                uint8_t ev = _edges_v[r][c];
                if (ev == 1 || ev == 2) {
                    uint16_t cx = grid_x + c * _cellSize + _cellSize / 2;
                    uint16_t cy = grid_y + (r + 1) * _cellSize;
                    canvas.fillRect(cx - 12, cy - 12, 25, 25, 0);
                    if (ev == 1) { // ^
                        for (int8_t d = 0; d < 8; d++) {
                            canvas.setPixel(cx - d, cy - 4 + d, 1);
                            canvas.setPixel(cx - d + 1, cy - 4 + d, 1);
                            canvas.setPixel(cx + d, cy - 4 + d, 1);
                            canvas.setPixel(cx + d - 1, cy - 4 + d, 1);
                        }
                    } else { // v
                        for (int8_t d = 0; d < 8; d++) {
                            canvas.setPixel(cx - d, cy + 3 - d, 1);
                            canvas.setPixel(cx - d + 1, cy + 3 - d, 1);
                            canvas.setPixel(cx + d, cy + 3 - d, 1);
                            canvas.setPixel(cx + d - 1, cy + 3 - d, 1);
                        }
                    }
                }
            }
        }

        for (uint8_t r = 0; r < _size; r++) {
            for (uint8_t c = 0; c < _size; c++) {
                if (_givens[r][c] > 0) {
                    uint16_t tx = grid_x + c * _cellSize + (_cellSize - 18) / 2;
                    uint16_t ty = grid_y + r * _cellSize + (_cellSize - 21) / 2;
                    char str[2] = { (char)('0' + _givens[r][c]), '\0' };
                    canvas.drawText(tx, ty, str, 3);
                }
            }
        }
    });
}
