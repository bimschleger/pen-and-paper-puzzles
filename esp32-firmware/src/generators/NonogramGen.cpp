#include "NonogramGen.h"
#include "../printer/EscPosPrinter.h"
#include "../printer/ThermalCanvas.h"

NonogramGen::NonogramGen() : _size(5) {
    memset(_grid, 0, sizeof(_grid));
}

void NonogramGen::calculateClues() {
    for (uint8_t i = 0; i < _size; i++) {
        _rowClues[i].clear();
        _colClues[i].clear();
    }

    // Row clues
    for (uint8_t r = 0; r < _size; r++) {
        uint8_t count = 0;
        for (uint8_t c = 0; c < _size; c++) {
            if (_grid[r][c] == 1) {
                count++;
            } else if (count > 0) {
                _rowClues[r].push_back(count);
                count = 0;
            }
        }
        if (count > 0) _rowClues[r].push_back(count);
        if (_rowClues[r].empty()) _rowClues[r].push_back(0);
    }

    // Column clues
    for (uint8_t c = 0; c < _size; c++) {
        uint8_t count = 0;
        for (uint8_t r = 0; r < _size; r++) {
            if (_grid[r][c] == 1) {
                count++;
            } else if (count > 0) {
                _colClues[c].push_back(count);
                count = 0;
            }
        }
        if (count > 0) _colClues[c].push_back(count);
        if (_colClues[c].empty()) _colClues[c].push_back(0);
    }
}

void NonogramGen::generate(NonogramDifficulty difficulty) {
    if (difficulty == NONO_EASY) _size = 5;
    else if (difficulty == NONO_HARD) _size = 10;
    else _size = 8;

    // Generate balanced random pattern (~50-60% fill)
    for (uint8_t r = 0; r < _size; r++) {
        for (uint8_t c = 0; c < _size; c++) {
            _grid[r][c] = (random(100) < 55) ? 1 : 0;
        }
    }

    calculateClues();
}

#if (OFFLINE_PRINT_STYLE == STYLE_ASCII) || defined(HOST_TEST)
void NonogramGen::printToReceipt(EscPosPrinter& printer) {
    // Find maximum depth of column clues and max row clue text width
    size_t maxColClues = 1;
    for (uint8_t c = 0; c < _size; c++) {
        if (_colClues[c].size() > maxColClues) {
            maxColClues = _colClues[c].size();
        }
    }
    size_t maxRowClueLen = 6;
    char rowClueTexts[MAX_SIZE][24];
    for (uint8_t r = 0; r < _size; r++) {
        size_t pos = 0;
        for (size_t i = 0; i < _rowClues[r].size() && pos + 4 < sizeof(rowClueTexts[r]); i++) {
            if (i > 0) rowClueTexts[r][pos++] = ' ';
            pos += snprintf(rowClueTexts[r] + pos, sizeof(rowClueTexts[r]) - pos, "%u", (unsigned)_rowClues[r][i]);
        }
        rowClueTexts[r][pos] = '\0';
        if (pos > maxRowClueLen) maxRowClueLen = pos;
    }

    char line[64];
    // Print column clues header
    for (size_t clueIdx = 0; clueIdx < maxColClues; clueIdx++) {
        size_t pos = 0;
        size_t indent = maxRowClueLen + 3;
        while (pos < indent && pos < sizeof(line) - 1) line[pos++] = ' ';
        for (uint8_t c = 0; c < _size && pos + 4 < sizeof(line); c++) {
            size_t numClues = _colClues[c].size();
            size_t pad = maxColClues - numClues;
            if (clueIdx >= pad) {
                uint8_t val = _colClues[c][clueIdx - pad];
                pos += snprintf(line + pos, sizeof(line) - pos, "%2u ", (unsigned)val);
            } else {
                memcpy(line + pos, "   ", 3);
                pos += 3;
            }
        }
        line[pos] = '\0';
        printer.println(line);
    }

    // Divider line
    {
        size_t pos = 0;
        while (pos < maxRowClueLen + 1 && pos < sizeof(line) - 1) line[pos++] = ' ';
        if (pos + 2 < sizeof(line)) { line[pos++] = '+'; line[pos++] = '-'; }
        for (uint8_t c = 0; c < _size && pos + 4 < sizeof(line); c++) {
            memcpy(line + pos, "---", 3);
            pos += 3;
        }
        line[pos] = '\0';
        printer.println(line);
    }

    // Print each row with its clues and empty dot slots
    for (uint8_t r = 0; r < _size; r++) {
        size_t pos = 0;
        size_t clueLen = strlen(rowClueTexts[r]);
        while (pos + clueLen < maxRowClueLen && pos < sizeof(line) - 1) line[pos++] = ' ';
        if (pos + clueLen + 4 < sizeof(line)) {
            memcpy(line + pos, rowClueTexts[r], clueLen);
            pos += clueLen;
            memcpy(line + pos, " | ", 3);
            pos += 3;
        }
        for (uint8_t c = 0; c < _size && pos + 4 < sizeof(line); c++) {
            memcpy(line + pos, " . ", 3);
            pos += 3;
        }
        line[pos] = '\0';
        printer.println(line);
    }
    printer.println("");
}
#endif

bool NonogramGen::printRasterToReceipt(EscPosPrinter& printer) {
    const int16_t padding = 24;
    const int16_t innerWidth = THERMAL_CANVAS_WIDTH - padding * 2;
    const int16_t cellSize = (_size <= 5) ? 76 : ((_size <= 8) ? 50 : ((_size <= 10) ? 40 : 26));
    const uint8_t majorInterval = (_size == 8) ? 4 : 5;
    const int16_t gridSize = cellSize * _size;
    const int16_t rowClueWidth = innerWidth - gridSize;

    size_t maxColClues = 1;
    for (uint8_t c = 0; c < _size; c++) {
        if (_colClues[c].size() > maxColClues) maxColClues = _colClues[c].size();
    }
    const int16_t colClueItemH = max((int16_t)24, (int16_t)(cellSize * 0.55));
    const int16_t colClueHeight = max((int16_t)50, (int16_t)(maxColClues * colClueItemH + 16));
    const int16_t totalH = ((12 + colClueHeight + gridSize + 12 + 7) / 8) * 8;
    const int16_t gridX = padding + rowClueWidth;
    const int16_t gridY = 12 + colClueHeight;

    ThermalCanvas canvas;
    return canvas.renderBanded(printer, totalH, [&](ThermalCanvas& canvas) {
        canvas.drawRect(padding, 12, rowClueWidth, colClueHeight, 3);
        canvas.drawRect(gridX, 12, gridSize, colClueHeight, 3);
        canvas.drawRect(padding, gridY, rowClueWidth, gridSize, 3);
        canvas.drawGrid(gridX, gridY, _size, _size, cellSize, cellSize, 4, 1, majorInterval, majorInterval, 4);

        for (uint8_t c = 0; c < _size; c++) {
            size_t numClues = _colClues[c].size();
            for (size_t k = 0; k < numClues; k++) {
                int16_t dist = (numClues - 1 - k) * colClueItemH;
                char buf[4];
                snprintf(buf, sizeof(buf), "%d", _colClues[c][k]);
                int16_t clueW = (strlen(buf) > 1) ? 28 : 16;
                int16_t colCx = gridX + c * cellSize + (cellSize - clueW) / 2;
                canvas.drawText(colCx, gridY - 26 - dist, buf, 2);
            }
            if (c > 0) {
                bool isMajor = (c % majorInterval == 0);
                canvas.drawVLine(gridX + c * cellSize, 12, colClueHeight, isMajor ? 3 : 1);
            }
        }

        for (uint8_t r = 0; r < _size; r++) {
            int16_t rowCy = gridY + r * cellSize + cellSize / 2 - 8;
            size_t numClues = _rowClues[r].size();
            for (size_t k = 0; k < numClues; k++) {
                int16_t dist = (numClues - 1 - k) * 20;
                char buf[4];
                snprintf(buf, sizeof(buf), "%d", _rowClues[r][k]);
                int16_t charOffset = (strlen(buf) > 1) ? 14 : 0;
                canvas.drawText(gridX - 24 - dist - charOffset, rowCy, buf, 2);
            }
            if (r > 0) {
                bool isMajor = (r % majorInterval == 0);
                canvas.drawHLine(padding, gridY + r * cellSize, rowClueWidth, isMajor ? 3 : 1);
            }
        }
    });
}

