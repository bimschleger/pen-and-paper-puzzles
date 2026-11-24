#include "ThermalCanvas.h"
#include "EscPosPrinter.h"
#include "qrcode.h"
#include <cstdlib>

#ifndef min
#define min(a,b) (((a)<(b))?(a):(b))
#endif
#ifndef max
#define max(a,b) (((a)>(b))?(a):(b))
#endif

// 5x7 Font representation: 7 rows of 6 bits per character
struct FontGlyph {
    char c;
    uint8_t rows[7];
};

static const FontGlyph GLYPH_TABLE[] = {
    { '0', {0x1E, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E} },
    { '1', {0x08, 0x18, 0x28, 0x08, 0x08, 0x08, 0x3E} },
    { '2', {0x1E, 0x21, 0x01, 0x0E, 0x18, 0x20, 0x3F} },
    { '3', {0x1E, 0x21, 0x01, 0x0E, 0x01, 0x21, 0x1E} },
    { '4', {0x02, 0x06, 0x0A, 0x12, 0x3F, 0x02, 0x02} },
    { '5', {0x3F, 0x20, 0x3E, 0x01, 0x01, 0x21, 0x1E} },
    { '6', {0x1E, 0x21, 0x20, 0x3E, 0x21, 0x21, 0x1E} },
    { '7', {0x3F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10} },
    { '8', {0x1E, 0x21, 0x21, 0x1E, 0x21, 0x21, 0x1E} },
    { '9', {0x1E, 0x21, 0x21, 0x1F, 0x01, 0x21, 0x1E} },
    { 'A', {0x0C, 0x12, 0x21, 0x3F, 0x21, 0x21, 0x21} },
    { 'B', {0x3E, 0x21, 0x21, 0x3E, 0x21, 0x21, 0x3E} },
    { 'C', {0x1E, 0x21, 0x20, 0x20, 0x20, 0x21, 0x1E} },
    { 'D', {0x3C, 0x22, 0x21, 0x21, 0x21, 0x22, 0x3C} },
    { 'E', {0x3F, 0x20, 0x20, 0x3E, 0x20, 0x20, 0x3F} },
    { 'F', {0x3F, 0x20, 0x20, 0x3E, 0x20, 0x20, 0x20} },
    { 'G', {0x1E, 0x21, 0x20, 0x27, 0x21, 0x21, 0x1E} },
    { 'H', {0x21, 0x21, 0x21, 0x3F, 0x21, 0x21, 0x21} },
    { 'I', {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F} },
    { 'J', {0x07, 0x02, 0x02, 0x02, 0x22, 0x22, 0x1C} },
    { 'K', {0x21, 0x22, 0x24, 0x38, 0x24, 0x22, 0x21} },
    { 'L', {0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x3F} },
    { 'M', {0x21, 0x33, 0x2D, 0x21, 0x21, 0x21, 0x21} },
    { 'N', {0x21, 0x31, 0x29, 0x25, 0x23, 0x21, 0x21} },
    { 'O', {0x1E, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E} },
    { 'P', {0x3E, 0x21, 0x21, 0x3E, 0x20, 0x20, 0x20} },
    { 'Q', {0x1E, 0x21, 0x21, 0x21, 0x25, 0x22, 0x1D} },
    { 'R', {0x3E, 0x21, 0x21, 0x3E, 0x24, 0x22, 0x21} },
    { 'S', {0x1E, 0x21, 0x20, 0x1E, 0x01, 0x21, 0x1E} },
    { 'T', {0x3F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04} },
    { 'U', {0x21, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E} },
    { 'V', {0x21, 0x21, 0x21, 0x12, 0x12, 0x0C, 0x0C} },
    { 'W', {0x21, 0x21, 0x21, 0x21, 0x2D, 0x33, 0x21} },
    { 'X', {0x21, 0x12, 0x0C, 0x0C, 0x12, 0x21, 0x21} },
    { 'Y', {0x21, 0x12, 0x0C, 0x04, 0x04, 0x04, 0x04} },
    { 'Z', {0x3F, 0x02, 0x04, 0x08, 0x10, 0x20, 0x3F} },
    { ' ', {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00} },
    { '.', {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C} },
    { ':', {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00} },
    { '-', {0x00, 0x00, 0x00, 0x3E, 0x00, 0x00, 0x00} },
    { '+', {0x00, 0x08, 0x08, 0x3E, 0x08, 0x08, 0x00} },
    { '=', {0x00, 0x3E, 0x00, 0x3E, 0x00, 0x00, 0x00} },
    { '*', {0x00, 0x2A, 0x1C, 0x3E, 0x1C, 0x2A, 0x00} },
    { '/', {0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x00} },
    { '(', {0x04, 0x08, 0x10, 0x10, 0x10, 0x08, 0x04} },
    { ')', {0x10, 0x08, 0x04, 0x04, 0x04, 0x08, 0x10} },
    { '?', {0x1E, 0x21, 0x02, 0x04, 0x04, 0x00, 0x04} },
    { '!', {0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04} },
    { '[', {0x1E, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1E} },
    { ']', {0x1E, 0x02, 0x02, 0x02, 0x02, 0x02, 0x1E} },
    { '_', {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3F} },
    { ',', {0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08} },
    { '"', {0x14, 0x14, 0x14, 0x00, 0x00, 0x00, 0x00} },
    { '\'', {0x08, 0x08, 0x10, 0x00, 0x00, 0x00, 0x00} },
    { '^', {0x0C, 0x12, 0x21, 0x00, 0x00, 0x00, 0x00} },
    { '|', {0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08} },
    { '<', {0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02} },
    { '>', {0x10, 0x08, 0x04, 0x02, 0x04, 0x08, 0x10} },
    { ';', {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x04, 0x08} }
};
static const size_t GLYPH_COUNT = sizeof(GLYPH_TABLE) / sizeof(GLYPH_TABLE[0]);

static const uint8_t* getGlyphRows(char c) {
    char upperC = toupper((unsigned char)c);
    for (size_t i = 0; i < GLYPH_COUNT; i++) {
        if (GLYPH_TABLE[i].c == upperC) {
            return GLYPH_TABLE[i].rows;
        }
    }
    // Return space for unknown glyphs
    return GLYPH_TABLE[36].rows;
}

namespace {
inline void fillRowSpan(uint8_t* rowPtr, int16_t startX, int16_t endX, uint8_t color) {
    if (startX >= endX) return;
    uint16_t bStart = (uint16_t)startX >> 3;
    uint16_t bEnd = (uint16_t)(endX - 1) >> 3;
    uint8_t leftMask = (uint8_t)(0xFFu >> (startX & 7));
    uint8_t rightBits = (uint8_t)(endX & 7);
    uint8_t rightMask = (rightBits == 0) ? 0xFFu : (uint8_t)(0xFFu << (8 - rightBits));

    if (color) {
        if (bStart == bEnd) {
            rowPtr[bStart] |= (uint8_t)(leftMask & rightMask);
        } else {
            rowPtr[bStart] |= leftMask;
            if (bEnd > bStart + 1) {
                memset(rowPtr + bStart + 1, 0xFF, bEnd - bStart - 1);
            }
            rowPtr[bEnd] |= rightMask;
        }
    } else {
        if (bStart == bEnd) {
            rowPtr[bStart] &= (uint8_t)~(leftMask & rightMask);
        } else {
            rowPtr[bStart] &= (uint8_t)~leftMask;
            if (bEnd > bStart + 1) {
                memset(rowPtr + bStart + 1, 0x00, bEnd - bStart - 1);
            }
            rowPtr[bEnd] &= (uint8_t)~rightMask;
        }
    }
}

inline void orRowSpan(uint8_t* rowPtr, int16_t startX, int16_t endX, uint8_t patternByte) {
    if (startX >= endX || patternByte == 0) return;
    uint16_t bStart = (uint16_t)startX >> 3;
    uint16_t bEnd = (uint16_t)(endX - 1) >> 3;
    uint8_t leftMask = (uint8_t)(0xFFu >> (startX & 7));
    uint8_t rightBits = (uint8_t)(endX & 7);
    uint8_t rightMask = (rightBits == 0) ? 0xFFu : (uint8_t)(0xFFu << (8 - rightBits));

    if (bStart == bEnd) {
        rowPtr[bStart] |= (uint8_t)(patternByte & leftMask & rightMask);
    } else {
        rowPtr[bStart] |= (uint8_t)(patternByte & leftMask);
        for (uint16_t b = bStart + 1; b < bEnd; b++) {
            rowPtr[b] |= patternByte;
        }
        rowPtr[bEnd] |= (uint8_t)(patternByte & rightMask);
    }
}
} // namespace

ThermalCanvas::ThermalCanvas() : _height(0), _yOffset(0), _totalHeight(0), _buffer(nullptr) {
}

ThermalCanvas::~ThermalCanvas() {
    end();
}

bool ThermalCanvas::begin(uint16_t heightDots) {
    end();
    _height = heightDots;
    _yOffset = 0;
    _totalHeight = heightDots;
    size_t totalBytes = (size_t)THERMAL_CANVAS_WIDTH_BYTES * _height;
    _buffer = (uint8_t*)malloc(totalBytes);
    if (_buffer) {
        memset(_buffer, 0, totalBytes);
        return true;
    }
    _height = 0;
    _totalHeight = 0;
    return false;
}

void ThermalCanvas::end() {
    if (_buffer) {
        free(_buffer);
        _buffer = nullptr;
    }
    _height = 0;
    _yOffset = 0;
    _totalHeight = 0;
}

void ThermalCanvas::clear(uint8_t color) {
    if (_buffer && _height > 0) {
        size_t totalBytes = (size_t)THERMAL_CANVAS_WIDTH_BYTES * _height;
        memset(_buffer, color ? 0xFF : 0x00, totalBytes);
    }
}

void ThermalCanvas::setPixel(int16_t x, int16_t y, uint8_t color) {
    int16_t ly = y - _yOffset;
    if (!_buffer || x < 0 || x >= THERMAL_CANVAS_WIDTH || ly < 0 || ly >= (int16_t)_height) {
        return;
    }
    size_t byteIdx = (size_t)ly * THERMAL_CANVAS_WIDTH_BYTES + (x >> 3);
    uint8_t bitMask = 1 << (7 - (x & 7));
    if (color) {
        _buffer[byteIdx] |= bitMask;
    } else {
        _buffer[byteIdx] &= ~bitMask;
    }
}

void ThermalCanvas::drawHLine(int16_t x, int16_t y, int16_t w, uint8_t thickness, uint8_t color) {
    if (!_buffer || w <= 0 || thickness <= 0) return;
    int16_t startX = max((int16_t)0, x);
    int16_t endX = min((int16_t)THERMAL_CANVAS_WIDTH, (int16_t)(x + w));
    if (startX >= endX) return;

    int16_t startY = max(_yOffset, y);
    int16_t endY = min((int16_t)(_yOffset + (int16_t)_height), (int16_t)(y + thickness));
    for (int16_t py = startY; py < endY; py++) {
        uint8_t* rowPtr = _buffer + (size_t)(py - _yOffset) * THERMAL_CANVAS_WIDTH_BYTES;
        fillRowSpan(rowPtr, startX, endX, color);
    }
}

void ThermalCanvas::drawVLine(int16_t x, int16_t y, int16_t h, uint8_t thickness, uint8_t color) {
    if (!_buffer || h <= 0 || thickness <= 0) return;
    int16_t startY = max(_yOffset, y);
    int16_t endY = min((int16_t)(_yOffset + (int16_t)_height), (int16_t)(y + h));
    if (startY >= endY) return;

    int16_t startX = max((int16_t)0, x);
    int16_t endX = min((int16_t)THERMAL_CANVAS_WIDTH, (int16_t)(x + thickness));
    for (int16_t px = startX; px < endX; px++) {
        uint16_t xByte = (uint16_t)(px >> 3);
        uint8_t bitMask = (uint8_t)(0x80u >> (px & 7));
        size_t offset = (size_t)(startY - _yOffset) * THERMAL_CANVAS_WIDTH_BYTES + xByte;
        if (color) {
            for (int16_t py = startY; py < endY; py++) {
                _buffer[offset] |= bitMask;
                offset += THERMAL_CANVAS_WIDTH_BYTES;
            }
        } else {
            uint8_t invMask = (uint8_t)~bitMask;
            for (int16_t py = startY; py < endY; py++) {
                _buffer[offset] &= invMask;
                offset += THERMAL_CANVAS_WIDTH_BYTES;
            }
        }
    }
}

void ThermalCanvas::drawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t thickness, uint8_t color) {
    if (w <= 0 || h <= 0) return;
    drawHLine(x, y, w, thickness, color);
    drawHLine(x, y + h - thickness, w, thickness, color);
    drawVLine(x, y, h, thickness, color);
    drawVLine(x + w - thickness, y, h, thickness, color);
}

void ThermalCanvas::fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t color) {
    if (!_buffer || w <= 0 || h <= 0) return;
    int16_t startY = max(_yOffset, y);
    int16_t endY = min((int16_t)(_yOffset + (int16_t)_height), (int16_t)(y + h));
    int16_t startX = max((int16_t)0, x);
    int16_t endX = min((int16_t)THERMAL_CANVAS_WIDTH, (int16_t)(x + w));
    if (startY >= endY || startX >= endX) return;

    for (int16_t py = startY; py < endY; py++) {
        uint8_t* rowPtr = _buffer + (size_t)(py - _yOffset) * THERMAL_CANVAS_WIDTH_BYTES;
        fillRowSpan(rowPtr, startX, endX, color);
    }
}

void ThermalCanvas::fillHatch(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t patternId) {
    if (!_buffer || w <= 0 || h <= 0) return;
    uint8_t pat = patternId % 10;
    if (pat == 0) return;
    int16_t startY = max((int16_t)0, max(_yOffset, y));
    int16_t endY = min((int16_t)(_yOffset + (int16_t)_height), (int16_t)(y + h));
    int16_t startX = max((int16_t)0, x);
    int16_t endX = min((int16_t)THERMAL_CANVAS_WIDTH, (int16_t)(x + w));
    if (startY >= endY || startX >= endX) return;

    for (int16_t py = startY; py < endY; py++) {
        uint8_t* rowPtr = _buffer + (size_t)(py - _yOffset) * THERMAL_CANVAS_WIDTH_BYTES;
        if (pat != 3 && pat != 9) {
            uint8_t rowMask = 0;
            for (uint8_t bx = 0; bx < 8; bx++) {
                bool isBurn = false;
                switch (pat) {
                    case 1: isBurn = (((bx + py) & 7) == 0); break;
                    case 2: isBurn = (((bx - py + 1000) % 8) == 0); break;
                    case 4: isBurn = (bx == 0); break;
                    case 5: isBurn = ((bx & 3) == 0 && (py % 4 == 0)); break;
                    case 6: isBurn = (((bx + py) & 7) == 0 && ((bx & 3) < 2)); break;
                    case 7: isBurn = (((bx - py + 1000) % 8) == 0 && ((bx & 3) < 2)); break;
                    case 8: {
                        int16_t ry = py % 8;
                        isBurn = ((bx == 4 && abs(ry - 4) <= 1) || (ry == 4 && abs((int16_t)bx - 4) <= 1));
                        break;
                    }
                }
                if (isBurn) rowMask |= (uint8_t)(0x80u >> bx);
            }
            if (rowMask) {
                orRowSpan(rowPtr, startX, endX, rowMask);
            }
        } else if (pat == 3) {
            for (int16_t px = startX; px < endX; px++) {
                if ((px + py) % 10 == 0 || (px - py + 1000) % 10 == 0) {
                    rowPtr[px >> 3] |= (uint8_t)(0x80u >> (px & 7));
                }
            }
        } else {
            for (int16_t px = startX; px < endX; px++) {
                if ((px + py) % 6 == 0 && (px - py + 1000) % 6 == 0) {
                    rowPtr[px >> 3] |= (uint8_t)(0x80u >> (px & 7));
                }
            }
        }
    }
}

void ThermalCanvas::drawGrid(int16_t x0, int16_t y0, uint8_t rows, uint8_t cols, int16_t cellW, int16_t cellH,
                             uint8_t outerThick, uint8_t innerThick,
                             uint8_t majorRowStep, uint8_t majorColStep, uint8_t majorThick) {
    if (rows == 0 || cols == 0 || cellW <= 0 || cellH <= 0) return;
    int16_t w = (int16_t)cols * cellW;
    int16_t h = (int16_t)rows * cellH;
    drawRect(x0, y0, w, h, outerThick, 1);
    for (uint8_t r = 1; r < rows; r++) {
        uint8_t th = (majorRowStep > 0 && (r % majorRowStep) == 0 && majorThick > 0) ? majorThick : innerThick;
        drawHLine(x0, y0 + (int16_t)r * cellH, w, th, 1);
    }
    for (uint8_t c = 1; c < cols; c++) {
        uint8_t th = (majorColStep > 0 && (c % majorColStep) == 0 && majorThick > 0) ? majorThick : innerThick;
        drawVLine(x0 + (int16_t)c * cellW, y0, h, th, 1);
    }
}

void ThermalCanvas::drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint8_t thickness, uint8_t color) {
    int16_t minY = min(y0, y1) - (int16_t)thickness;
    int16_t maxY = max(y0, y1) + (int16_t)thickness;
    if (maxY < _yOffset || minY >= _yOffset + (int16_t)_height) return;

    int16_t dx = abs(x1 - x0);
    int16_t sx = (x0 < x1) ? 1 : -1;
    int16_t dy = -abs(y1 - y0);
    int16_t sy = (y0 < y1) ? 1 : -1;
    int16_t err = dx + dy;

    while (true) {
        if (thickness <= 1) {
            setPixel(x0, y0, color);
        } else {
            int16_t halfT = thickness / 2;
            for (int16_t ty = -halfT; ty < halfT + (thickness % 2); ty++) {
                for (int16_t tx = -halfT; tx < halfT + (thickness % 2); tx++) {
                    setPixel(x0 + tx, y0 + ty, color);
                }
            }
        }
        if (x0 == x1 && y0 == y1) break;
        int16_t e2 = 2 * err;
        if (e2 >= dy) {
            err += dy;
            x0 += sx;
        }
        if (e2 <= dx) {
            err += dx;
            y0 += sy;
        }
    }
}

void ThermalCanvas::drawDashedHLine(int16_t x, int16_t y, int16_t w, uint8_t dashLen, uint8_t gapLen, uint8_t thickness, uint8_t color) {
    if (w <= 0 || dashLen == 0) return;
    int16_t curX = x;
    int16_t endX = x + w;
    while (curX < endX) {
        int16_t segW = min((int16_t)dashLen, (int16_t)(endX - curX));
        drawHLine(curX, y, segW, thickness, color);
        curX += dashLen + gapLen;
    }
}

void ThermalCanvas::drawPolygon(const int16_t* px, const int16_t* py, uint8_t numPoints, uint8_t thickness, uint8_t color) {
    if (numPoints < 2) return;
    for (uint8_t i = 0; i < numPoints; i++) {
        uint8_t next = (i + 1) % numPoints;
        drawLine(px[i], py[i], px[next], py[next], thickness, color);
    }
}

void ThermalCanvas::drawCircle(int16_t cx, int16_t cy, int16_t radius, uint8_t thickness, uint8_t color) {
    if (!_buffer || radius <= 0) return;
    int32_t rInnerSq = (radius >= thickness) ? (int32_t)(radius - thickness) * (radius - thickness) : 0;
    int32_t rOuterSq = (int32_t)radius * radius;
    int16_t yStart = max(_yOffset, (int16_t)(cy - radius));
    int16_t yEnd = min((int16_t)(_yOffset + (int16_t)_height), (int16_t)(cy + radius + 1));
    int16_t xStart = max((int16_t)0, (int16_t)(cx - radius));
    int16_t xEnd = min((int16_t)THERMAL_CANVAS_WIDTH, (int16_t)(cx + radius + 1));

    for (int16_t py = yStart; py < yEnd; py++) {
        int32_t dy = py - cy;
        int32_t dySq = dy * dy;
        uint8_t* rowPtr = _buffer + (size_t)(py - _yOffset) * THERMAL_CANVAS_WIDTH_BYTES;
        for (int16_t px = xStart; px < xEnd; px++) {
            int32_t dx = px - cx;
            int32_t distSq = dx * dx + dySq;
            if (distSq >= rInnerSq && distSq <= rOuterSq) {
                if (color) rowPtr[px >> 3] |= (uint8_t)(0x80u >> (px & 7));
                else rowPtr[px >> 3] &= (uint8_t)~(0x80u >> (px & 7));
            }
        }
    }
}

void ThermalCanvas::fillCircle(int16_t cx, int16_t cy, int16_t radius, uint8_t color) {
    if (!_buffer || radius <= 0) return;
    int32_t rSq = (int32_t)radius * radius;
    int16_t yStart = max(_yOffset, (int16_t)(cy - radius));
    int16_t yEnd = min((int16_t)(_yOffset + (int16_t)_height), (int16_t)(cy + radius + 1));
    int16_t xStart = max((int16_t)0, (int16_t)(cx - radius));
    int16_t xEnd = min((int16_t)THERMAL_CANVAS_WIDTH, (int16_t)(cx + radius + 1));

    for (int16_t py = yStart; py < yEnd; py++) {
        int32_t dy = py - cy;
        int32_t dySq = dy * dy;
        uint8_t* rowPtr = _buffer + (size_t)(py - _yOffset) * THERMAL_CANVAS_WIDTH_BYTES;
        for (int16_t px = xStart; px < xEnd; px++) {
            int32_t dx = px - cx;
            if (dx * dx + dySq <= rSq) {
                if (color) rowPtr[px >> 3] |= (uint8_t)(0x80u >> (px & 7));
                else rowPtr[px >> 3] &= (uint8_t)~(0x80u >> (px & 7));
            }
        }
    }
}

void ThermalCanvas::drawChar(int16_t x, int16_t y, char c, uint8_t scale, uint8_t color) {
    if (!_buffer || scale == 0) return;
    if (scale == 2 || scale == 3) {
        uint8_t uc = (uint8_t)toupper((unsigned char)c);
        if (uc >= 32 && uc < 127) {
            uint8_t gIdx = pgm_read_byte(&THERMAL_GRID_ASCII_MAP[uc - 32]);
            if (gIdx != 255) {
                ThermalFontId fid = (scale == 2) ? FONT_GRID_12x14 : FONT_GRID_18x21;
                ThermalFontDef def;
                memcpy_P(&def, &THERMAL_FONT_DEFS[fid], sizeof(ThermalFontDef));
                if (gIdx < def.glyphCount) {
                    ThermalGlyph g;
                    memcpy_P(&g, &def.glyphs[gIdx], sizeof(ThermalGlyph));
                    if (g.w > 0 && g.h > 0) {
                        int16_t gx = x + g.xOff;
                        int16_t gy = y + g.yOff;
                        if (gy + g.h > _yOffset && gy < _yOffset + (int16_t)_height) {
                            uint16_t bitIdx = 0;
                            for (uint8_t dy = 0; dy < g.h; dy++) {
                                int16_t py = gy + dy;
                                bool inBand = (py >= _yOffset && py < _yOffset + (int16_t)_height);
                                for (uint8_t dx = 0; dx < g.w; dx++) {
                                    uint8_t byteVal = pgm_read_byte(def.bitmap + g.bitOffset + (bitIdx >> 3));
                                    if (inBand && ((byteVal >> (7 - (bitIdx & 7))) & 1)) {
                                        setPixel(gx + dx, py, color);
                                    }
                                    bitIdx++;
                                }
                            }
                        }
                    }
                    return;
                }
            }
            return;
        }
    }
    if (y + 7 * (int16_t)scale <= _yOffset || y >= _yOffset + (int16_t)_height) return;
    const uint8_t* rows = getGlyphRows(c);
    for (uint8_t rowIdx = 0; rowIdx < 7; rowIdx++) {
        uint8_t rowByte = rows[rowIdx];
        for (uint8_t colIdx = 0; colIdx < 6; colIdx++) {
            if ((rowByte >> (5 - colIdx)) & 1) {
                fillRect(x + colIdx * scale, y + rowIdx * scale, scale, scale, color);
            }
        }
    }
}

namespace {
inline bool loadPropGlyph(const ThermalFontDef& def, char ch, ThermalGlyph& out) {
    uint8_t uc = (uint8_t)ch;
    uint8_t idx = (uc >= 32 && uc < 127) ? (uint8_t)(uc - 32) : 0;
    if (idx >= def.glyphCount) idx = 0;
    memcpy_P(&out, &def.glyphs[idx], sizeof(ThermalGlyph));
    return true;
}

inline int16_t measureSpanWidth(const ThermalFontDef& def, const char* start, const char* end) {
    int16_t total = 0;
    ThermalGlyph g;
    for (const char* p = start; p < end; p++) {
        loadPropGlyph(def, *p, g);
        total += g.xAdv;
    }
    return total;
}
} // namespace

uint8_t ThermalCanvas::getFontLineHeight(ThermalFontId fontId) const {
    if ((uint8_t)fontId >= THERMAL_FONT_COUNT) return 0;
    ThermalFontDef def;
    memcpy_P(&def, &THERMAL_FONT_DEFS[fontId], sizeof(ThermalFontDef));
    return def.lineHeight;
}

int16_t ThermalCanvas::measureTextFont(const char* text, ThermalFontId fontId) const {
    if (!text || (uint8_t)fontId >= THERMAL_FONT_COUNT) return 0;
    ThermalFontDef def;
    memcpy_P(&def, &THERMAL_FONT_DEFS[fontId], sizeof(ThermalFontDef));
    int16_t total = 0;
    ThermalGlyph g;
    while (*text) {
        loadPropGlyph(def, *text, g);
        total += g.xAdv;
        text++;
    }
    return total;
}

void ThermalCanvas::drawTextFont(int16_t x, int16_t y, const char* text, ThermalFontId fontId, uint8_t color) {
    if (!_buffer || !text || (uint8_t)fontId >= THERMAL_FONT_COUNT) return;
    ThermalFontDef def;
    memcpy_P(&def, &THERMAL_FONT_DEFS[fontId], sizeof(ThermalFontDef));
    int16_t curX = x;
    ThermalGlyph g;
    while (*text) {
        loadPropGlyph(def, *text, g);
        if (g.w > 0 && g.h > 0) {
            int16_t gx = curX + g.xOff;
            int16_t gy = y + g.yOff;
            if (gy + g.h > _yOffset && gy < _yOffset + (int16_t)_height) {
                uint16_t bitIdx = 0;
                for (uint8_t dy = 0; dy < g.h; dy++) {
                    int16_t py = gy + dy;
                    bool inBand = (py >= _yOffset && py < _yOffset + (int16_t)_height);
                    for (uint8_t dx = 0; dx < g.w; dx++) {
                        uint8_t byteVal = pgm_read_byte(def.bitmap + g.bitOffset + (bitIdx >> 3));
                        if (inBand && ((byteVal >> (7 - (bitIdx & 7))) & 1)) {
                            setPixel(gx + dx, py, color);
                        }
                        bitIdx++;
                    }
                }
            }
        }
        curX += g.xAdv;
        text++;
    }
}

void ThermalCanvas::drawCenteredTextFont(int16_t y, const char* text, ThermalFontId fontId, uint8_t color) {
    if (!text) return;
    int16_t w = measureTextFont(text, fontId);
    int16_t x = (THERMAL_CANVAS_WIDTH - w) / 2;
    drawTextFont(x, y, text, fontId, color);
}

void ThermalCanvas::drawRightTextFont(int16_t rightX, int16_t y, const char* text, ThermalFontId fontId, uint8_t color) {
    if (!text) return;
    int16_t w = measureTextFont(text, fontId);
    drawTextFont(rightX - w, y, text, fontId, color);
}

int16_t ThermalCanvas::measureWrappedHeightFont(const char* text, int16_t maxWidth, ThermalFontId fontId, uint8_t lineGap) const {
    if (!text || text[0] == '\0' || (uint8_t)fontId >= THERMAL_FONT_COUNT) return 0;
    ThermalFontDef def;
    memcpy_P(&def, &THERMAL_FONT_DEFS[fontId], sizeof(ThermalFontDef));
    ThermalGlyph spaceG;
    loadPropGlyph(def, ' ', spaceG);
    int16_t spaceAdv = spaceG.xAdv;

    int16_t lineCount = 0;
    int16_t curW = 0;
    bool hasWordsOnLine = false;
    const char* p = text;
    while (*p != '\0') {
        while (*p == ' ') p++;
        if (*p == '\0') break;
        const char* wStart = p;
        while (*p != '\0' && *p != ' ') p++;
        int16_t wW = measureSpanWidth(def, wStart, p);
        if (!hasWordsOnLine) {
            lineCount++;
            curW = wW;
            hasWordsOnLine = true;
        } else if (curW + spaceAdv + wW <= maxWidth) {
            curW += spaceAdv + wW;
        } else {
            lineCount++;
            curW = wW;
        }
    }
    if (lineCount == 0) return 0;
    return lineCount * (int16_t)def.lineHeight + (lineCount - 1) * (int16_t)lineGap;
}

int16_t ThermalCanvas::drawWrappedTextFont(int16_t x, int16_t y, int16_t maxWidth, const char* text,
                                           ThermalFontId fontId, uint8_t align,
                                           uint8_t lineGap, uint8_t color) {
    if (!text || text[0] == '\0' || (uint8_t)fontId >= THERMAL_FONT_COUNT) return 0;
    ThermalFontDef def;
    memcpy_P(&def, &THERMAL_FONT_DEFS[fontId], sizeof(ThermalFontDef));
    ThermalGlyph spaceG;
    loadPropGlyph(def, ' ', spaceG);
    int16_t spaceAdv = spaceG.xAdv;

    auto flushLine = [&](const char* lStart, const char* lEnd, int16_t lineW, int16_t ly) {
        if (!_buffer || !lStart || lEnd <= lStart) return;
        int16_t lx = x;
        if (align == 1) {
            lx = x + (maxWidth - lineW) / 2;
        } else if (align == 2) {
            lx = x + maxWidth - lineW;
        }
        int16_t curX = lx;
        ThermalGlyph g;
        for (const char* q = lStart; q < lEnd; q++) {
            if (*q == ' ' && q > lStart && *(q - 1) == ' ') continue;
            char ch = (*q == ' ') ? ' ' : *q;
            loadPropGlyph(def, ch, g);
            if (g.w > 0 && g.h > 0) {
                int16_t gx = curX + g.xOff;
                int16_t gy = ly + g.yOff;
                if (gy + g.h > _yOffset && gy < _yOffset + (int16_t)_height) {
                    uint16_t bitIdx = 0;
                    for (uint8_t dy = 0; dy < g.h; dy++) {
                        int16_t py = gy + dy;
                        bool inBand = (py >= _yOffset && py < _yOffset + (int16_t)_height);
                        for (uint8_t dx = 0; dx < g.w; dx++) {
                            uint8_t byteVal = pgm_read_byte(def.bitmap + g.bitOffset + (bitIdx >> 3));
                            if (inBand && ((byteVal >> (7 - (bitIdx & 7))) & 1)) {
                                setPixel(gx + dx, py, color);
                            }
                            bitIdx++;
                        }
                    }
                }
            }
            curX += g.xAdv;
        }
    };

    const char* lineStart = nullptr;
    const char* lineEnd = nullptr;
    int16_t curW = 0;
    int16_t lineCount = 0;
    int16_t curY = y;
    const char* p = text;
    while (*p != '\0') {
        while (*p == ' ') p++;
        if (*p == '\0') break;
        const char* wStart = p;
        while (*p != '\0' && *p != ' ') p++;
        int16_t wW = measureSpanWidth(def, wStart, p);
        if (lineStart == nullptr) {
            lineStart = wStart;
            lineEnd = p;
            curW = wW;
        } else if (curW + spaceAdv + wW <= maxWidth) {
            lineEnd = p;
            curW += spaceAdv + wW;
        } else {
            flushLine(lineStart, lineEnd, curW, curY);
            lineCount++;
            curY += (int16_t)def.lineHeight + (int16_t)lineGap;
            lineStart = wStart;
            lineEnd = p;
            curW = wW;
        }
    }
    if (lineStart != nullptr) {
        flushLine(lineStart, lineEnd, curW, curY);
        lineCount++;
    }
    if (lineCount == 0) return 0;
    return lineCount * (int16_t)def.lineHeight + (lineCount - 1) * (int16_t)lineGap;
}

uint16_t ThermalCanvas::measureMasterHeaderHeight(const ThermalCanvas& ref, const char* title,
                                                  const char* subtitle, const char* mixSubtitle) {
    int16_t curY = 20 + (int16_t)ref.getFontLineHeight(FONT_DISPLAY_32) + 4;
    if (subtitle && subtitle[0] != '\0') {
        curY += (int16_t)ref.getFontLineHeight(FONT_BODY_20) + 6;
    }
    curY += 13;
    if (mixSubtitle && mixSubtitle[0] != '\0') {
        curY += (int16_t)ref.getFontLineHeight(FONT_CAPTION_16) + 8;
    }
    return (uint16_t)((curY + 7) & ~7);
}

void ThermalCanvas::drawMasterHeader(const char* title, const char* subtitle, const char* mixSubtitle) {
    drawHLine(20, 4, 536, 2, 1);
    drawHLine(20, 8, 536, 1, 1);
    int16_t curY = 20;
    if (title && title[0] != '\0') {
        drawCenteredTextFont(curY, title, FONT_DISPLAY_32, 1);
    }
    curY += (int16_t)getFontLineHeight(FONT_DISPLAY_32) + 4;
    if (subtitle && subtitle[0] != '\0') {
        drawCenteredTextFont(curY, subtitle, FONT_BODY_20, 1);
        curY += (int16_t)getFontLineHeight(FONT_BODY_20) + 6;
    }
    drawHLine(20, curY, 536, 1, 1);
    drawHLine(20, curY + 3, 536, 2, 1);
    curY += 13;
    if (mixSubtitle && mixSubtitle[0] != '\0') {
        drawCenteredTextFont(curY, mixSubtitle, FONT_CAPTION_16, 1);
    }
}

uint16_t ThermalCanvas::measurePuzzleHeaderHeight(const ThermalCanvas& ref, const char* title,
                                                  const char* diffStr, const char* instruction) {
    (void)title;
    int16_t curY = 36;
    if (diffStr && diffStr[0] != '\0') {
        curY += (int16_t)ref.getFontLineHeight(FONT_CAPTION_16) + 4;
    }
    if (instruction && instruction[0] != '\0') {
        curY += 2;
        curY += ref.measureWrappedHeightFont(instruction, 536, FONT_BODY_20, 4) + 10;
    }
    return (uint16_t)((curY + 7) & ~7);
}

void ThermalCanvas::drawPuzzleHeader(const char* title, const char* diffStr, const char* instruction) {
    int16_t curY = 4;
    if (title && title[0] != '\0') {
        int16_t tw = measureTextFont(title, FONT_SUBHEAD_22);
        int16_t tx = (THERMAL_CANVAS_WIDTH - tw) / 2;
        int16_t ruleY = curY + (int16_t)getFontLineHeight(FONT_SUBHEAD_22) / 2;
        if (tx - 14 > 20) {
            drawHLine(20, ruleY, tx - 14 - 20, 1, 1);
        }
        if (tx + tw + 14 < 556) {
            drawHLine(tx + tw + 14, ruleY, 556 - (tx + tw + 14), 1, 1);
        }
        drawTextFont(tx, curY, title, FONT_SUBHEAD_22, 1);
    }
    curY = 36;
    if (diffStr && diffStr[0] != '\0') {
        char diffBuf[64];
        snprintf(diffBuf, sizeof(diffBuf), "DIFFICULTY: %s", diffStr);
        drawCenteredTextFont(curY, diffBuf, FONT_CAPTION_16, 1);
        curY += (int16_t)getFontLineHeight(FONT_CAPTION_16) + 4;
    }
    if (instruction && instruction[0] != '\0') {
        curY += 2;
        int16_t ih = drawWrappedTextFont(20, curY, 536, instruction, FONT_BODY_20, 1, 4, 1);
        curY += ih + 10;
    }
}

void ThermalCanvas::drawDivider() {
    drawHLine(20, 11, 536, 1, 1);
}

uint16_t ThermalCanvas::measureMasterFooterHeight(const ThermalCanvas& ref, const char* closingTagline,
                                                  bool includeScheduleHint, bool leadingRule) {
    int16_t curY = 4;
    if (leadingRule) curY += 18;
    if (closingTagline && closingTagline[0] != '\0') {
        curY += (int16_t)ref.getFontLineHeight(FONT_SUBHEAD_22) + 8;
    }
    curY += ref.measureWrappedHeightFont("For more puzzles, toggle the power on the front of the printer.", 536, FONT_BODY_20, 4) + 10;
    curY += ref.measureWrappedHeightFont("To change settings, toggle the power on the cable behind the printer.", 536, FONT_BODY_20, 4) + 10;
    if (includeScheduleHint) {
        curY += (int16_t)ref.getFontLineHeight(FONT_BODY_20) + 6;
    }
    curY += 12;
    return (uint16_t)((curY + 7) & ~7);
}

void ThermalCanvas::drawMasterFooter(const char* closingTagline, bool includeScheduleHint, bool leadingRule) {
    int16_t curY = 4;
    if (leadingRule) {
        drawHLine(20, curY + 6, 536, 1, 1);
        curY += 18;
    }
    if (closingTagline && closingTagline[0] != '\0') {
        drawCenteredTextFont(curY, closingTagline, FONT_SUBHEAD_22, 1);
        curY += (int16_t)getFontLineHeight(FONT_SUBHEAD_22) + 8;
    }
    curY += drawWrappedTextFont(20, curY, 536,
                                "For more puzzles, toggle the power on the front of the printer.",
                                FONT_BODY_20, 1, 4, 1) + 10;
    curY += drawWrappedTextFont(20, curY, 536,
                                "To change settings, toggle the power on the cable behind the printer.",
                                FONT_BODY_20, 1, 4, 1) + 10;
    if (includeScheduleHint) {
        drawCenteredTextFont(curY, "To schedule daily puzzles, go to settings.", FONT_BODY_20, 1);
        curY += (int16_t)getFontLineHeight(FONT_BODY_20) + 6;
    }
    drawHLine(20, curY + 2, 536, 1, 1);
}

void ThermalCanvas::drawText(int16_t x, int16_t y, const char* text, uint8_t scale, uint8_t color) {
    if (!text || scale == 0) return;
    int16_t curX = x;
    int16_t charW = 6 * scale + max(1, scale / 2);
    while (*text) {
        drawChar(curX, y, *text, scale, color);
        curX += charW;
        text++;
    }
}

void ThermalCanvas::drawCenteredText(int16_t y, const char* text, uint8_t scale, uint8_t color) {
    if (!text) return;
    int16_t w = getTextWidth(text, scale);
    int16_t x = (THERMAL_CANVAS_WIDTH - w) / 2;
    drawText(x, y, text, scale, color);
}

int16_t ThermalCanvas::getTextWidth(const char* text, uint8_t scale) const {
    if (!text || scale == 0) return 0;
    int len = strlen(text);
    if (len == 0) return 0;
    int16_t charW = 6 * scale + max(1, scale / 2);
    return len * charW;
}

bool ThermalCanvas::drawQrCode(int16_t cx, int16_t cy, const char* text, uint8_t moduleScale) {
    if (!text || moduleScale == 0 || !_buffer) return false;

    QRCode qrcode;
    uint8_t qrcodeData[106]; // Version 3 buffer
    int8_t status = qrcode_initText(&qrcode, qrcodeData, 3, ECC_LOW, text);
    if (status != 0) return false;

    int16_t qrPx = (int16_t)qrcode.size * moduleScale;
    int16_t startX = cx - (qrPx / 2);
    int16_t startY = cy - (qrPx / 2);

    // Quiet zone: 4 modules white background
    int16_t quietPx = 4 * moduleScale;
    fillRect(startX - quietPx, startY - quietPx, qrPx + 2 * quietPx, qrPx + 2 * quietPx, 0);

    // Draw dark modules
    for (uint8_t y = 0; y < qrcode.size; y++) {
        for (uint8_t x = 0; x < qrcode.size; x++) {
            if (qrcode_getModule(&qrcode, x, y)) {
                fillRect(startX + x * moduleScale, startY + y * moduleScale, moduleScale, moduleScale, 1);
            }
        }
    }
    return true;
}

bool ThermalCanvas::printTo(EscPosPrinter& printer) {
    if (!_buffer || _height == 0) return false;
    printer.printRasterBitmap(_buffer, THERMAL_CANVAS_WIDTH, _height);
    return true;
}
