#ifndef THERMAL_CANVAS_H
#define THERMAL_CANVAS_H

#include <Arduino.h>
#include "ThermalFonts.h"

class EscPosPrinter;

#define THERMAL_CANVAS_WIDTH       576
#define THERMAL_CANVAS_WIDTH_BYTES 72   // 576 / 8

class ThermalCanvas {
public:
    ThermalCanvas();
    ~ThermalCanvas();
    ThermalCanvas(const ThermalCanvas&) = delete;
    ThermalCanvas& operator=(const ThermalCanvas&) = delete;

    static constexpr uint16_t BAND_HEIGHT = 256;

    // Buffer lifecycle
    bool begin(uint16_t heightDots);
    void end();
    void clear(uint8_t color = 0);

    bool isValid() const { return _buffer != nullptr && _height > 0; }
    uint16_t getWidth() const { return THERMAL_CANVAS_WIDTH; }
    uint16_t getHeight() const { return _height; }
    uint8_t* getBuffer() const { return _buffer; }
    size_t getBufferSize() const { return (size_t)THERMAL_CANVAS_WIDTH_BYTES * _height; }

    // Drawing Primitives
    void setPixel(int16_t x, int16_t y, uint8_t color = 1);
    void drawHLine(int16_t x, int16_t y, int16_t w, uint8_t thickness = 1, uint8_t color = 1);
    void drawVLine(int16_t x, int16_t y, int16_t h, uint8_t thickness = 1, uint8_t color = 1);
    void drawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t thickness = 1, uint8_t color = 1);
    void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t color = 1);
    void fillHatch(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t patternId);
    void drawGrid(int16_t x0, int16_t y0, uint8_t rows, uint8_t cols, int16_t cellW, int16_t cellH,
                  uint8_t outerThick = 4, uint8_t innerThick = 1,
                  uint8_t majorRowStep = 0, uint8_t majorColStep = 0, uint8_t majorThick = 0);
    // Lines & Shapes
    void drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint8_t thickness = 1, uint8_t color = 1);
    void drawDashedHLine(int16_t x, int16_t y, int16_t w, uint8_t dashLen = 4, uint8_t gapLen = 4, uint8_t thickness = 1, uint8_t color = 1);
    void drawPolygon(const int16_t* px, const int16_t* py, uint8_t numPoints, uint8_t thickness = 1, uint8_t color = 1);

    // Circles
    void drawCircle(int16_t cx, int16_t cy, int16_t radius, uint8_t thickness = 2, uint8_t color = 1);
    void fillCircle(int16_t cx, int16_t cy, int16_t radius, uint8_t color = 1);

    // Text & Fonts (5x7 standard bitmap font + native 203 DPI 1-bit fonts)
    void drawChar(int16_t x, int16_t y, char c, uint8_t scale = 2, uint8_t color = 1);
    void drawText(int16_t x, int16_t y, const char* text, uint8_t scale = 2, uint8_t color = 1);
    void drawCenteredText(int16_t y, const char* text, uint8_t scale = 2, uint8_t color = 1);
    int16_t getTextWidth(const char* text, uint8_t scale = 2) const;

    uint8_t getFontLineHeight(ThermalFontId fontId) const;
    int16_t measureTextFont(const char* text, ThermalFontId fontId) const;
    void drawTextFont(int16_t x, int16_t y, const char* text, ThermalFontId fontId, uint8_t color = 1);
    void drawCenteredTextFont(int16_t y, const char* text, ThermalFontId fontId, uint8_t color = 1);
    void drawRightTextFont(int16_t rightX, int16_t y, const char* text, ThermalFontId fontId, uint8_t color = 1);
    int16_t measureWrappedHeightFont(const char* text, int16_t maxWidth, ThermalFontId fontId, uint8_t lineGap = 4) const;
    int16_t drawWrappedTextFont(int16_t x, int16_t y, int16_t maxWidth, const char* text,
                                ThermalFontId fontId, uint8_t align = 0,
                                uint8_t lineGap = 4, uint8_t color = 1);

    // Standardized 203 DPI Receipt Chrome Renderers (matching Python & Web Simulator)
    static uint16_t measureMasterHeaderHeight(const ThermalCanvas& ref, const char* title,
                                              const char* subtitle = nullptr, const char* mixSubtitle = nullptr);
    void drawMasterHeader(const char* title, const char* subtitle = nullptr, const char* mixSubtitle = nullptr);

    static uint16_t measurePuzzleHeaderHeight(const ThermalCanvas& ref, const char* title,
                                              const char* diffStr = nullptr, const char* instruction = nullptr);
    void drawPuzzleHeader(const char* title, const char* diffStr = nullptr, const char* instruction = nullptr);

    static uint16_t getDividerHeight() { return 24; }
    void drawDivider();

    static uint16_t measureMasterFooterHeight(const ThermalCanvas& ref, const char* closingTagline,
                                              bool includeScheduleHint = false, bool leadingRule = true);
    void drawMasterFooter(const char* closingTagline, bool includeScheduleHint = false, bool leadingRule = true);

    // QR Code rendering
    bool drawQrCode(int16_t cx, int16_t cy, const char* text, uint8_t moduleScale = 6);

    // Direct stream to thermal printer
    bool printTo(EscPosPrinter& printer);

    template <typename DrawFn>
    bool renderBanded(EscPosPrinter& printer, uint16_t totalHeight, DrawFn&& drawFn) {
        totalHeight = (uint16_t)((totalHeight + 7) & ~7);
        if (totalHeight == 0) return false;

        uint16_t bandH = (totalHeight < BAND_HEIGHT) ? totalHeight : BAND_HEIGHT;
        if (!begin(bandH)) return false;

        _totalHeight = totalHeight;
        if (!printer.beginRasterBitmap(THERMAL_CANVAS_WIDTH, totalHeight)) {
            end();
            return false;
        }

        bool ok = true;
        for (uint16_t bandY = 0; bandY < totalHeight; bandY += BAND_HEIGHT) {
            uint16_t curH = totalHeight - bandY;
            if (curH > BAND_HEIGHT) curH = BAND_HEIGHT;
            _yOffset = (int16_t)bandY;
            _height = curH;
            clear(0);
            drawFn(*this);
            if (!printer.writeRasterRows(_buffer, (size_t)curH * THERMAL_CANVAS_WIDTH_BYTES)) {
                ok = false;
                break;
            }
        }

        printer.endRasterBitmap();
        end();
        return ok;
    }

private:
    uint16_t _height;
    int16_t  _yOffset;
    uint16_t _totalHeight;
    uint8_t* _buffer;
};

#endif // THERMAL_CANVAS_H
