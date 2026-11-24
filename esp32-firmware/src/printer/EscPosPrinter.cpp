#include "EscPosPrinter.h"
#include "ThermalCanvas.h"

EscPosPrinter::EscPosPrinter() : 
    _mode(ACTIVE_PRINTER_MODE), 
    _serial(nullptr), 
    _outputStream(nullptr) {
}

EscPosPrinter::~EscPosPrinter() {
    disconnect();
}

bool EscPosPrinter::begin() {
    if (_mode == PRINTER_MODE_SERIAL) {
        _serial = &Serial2;
        _serial->begin(PRINTER_SERIAL_BAUD, SERIAL_8N1, PRINTER_RX_PIN, PRINTER_TX_PIN);
        _outputStream = _serial;
        Serial.printf("[PRINTER] Initialized Serial2 on RX=%d, TX=%d @ %d baud\n", 
                      PRINTER_RX_PIN, PRINTER_TX_PIN, PRINTER_SERIAL_BAUD);
        init();
        return true;
    }
#if (ACTIVE_PRINTER_MODE == PRINTER_MODE_W5500_ETH)
    if (_mode == PRINTER_MODE_W5500_ETH) {
        Serial.println("\n[ETH] Initializing W5500 SPI Ethernet (ESP32-S3-ETH)...");
        Serial.printf("[ETH] Hardware SPI: SCK=%d, MISO=%d, MOSI=%d, CS=%d, RST=%d\n",
                      W5500_SCK_PIN, W5500_MISO_PIN, W5500_MOSI_PIN, W5500_CS_PIN, W5500_RST_PIN);
        pinMode(W5500_RST_PIN, OUTPUT);
        digitalWrite(W5500_RST_PIN, LOW);
        delay(10);
        digitalWrite(W5500_RST_PIN, HIGH);
        delay(50);

        SPI.begin(W5500_SCK_PIN, W5500_MISO_PIN, W5500_MOSI_PIN, W5500_CS_PIN);
        Ethernet.init(W5500_CS_PIN);

        uint8_t mac[6] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };
        IPAddress ip, gw, mask, dns;
        ip.fromString(ESP32_STATIC_IP);
        gw.fromString(ESP32_STATIC_GATEWAY);
        mask.fromString(ESP32_STATIC_SUBNET);
        dns.fromString(ESP32_STATIC_DNS);

        Ethernet.begin(mac, ip, dns, gw, mask);
        delay(200);

        Serial.printf("[ETH] W5500 Configured! ESP32 IP: %s | Subnet: %s | Gateway: %s\n",
                      Ethernet.localIP().toString().c_str(), ESP32_STATIC_SUBNET, ESP32_STATIC_GATEWAY);
        Serial.printf("[ETH] Point-to-Point Direct Target Printer: %s:%d\n\n", PRINTER_IP_ADDR, PRINTER_TCP_PORT);
        return true;
    }
#endif
    
    Serial.printf("[PRINTER] Configured for Wi-Fi TCP: %s:%d\n", PRINTER_IP_ADDR, PRINTER_TCP_PORT);
    return true;
}

bool EscPosPrinter::connect() {
    if (_mode == PRINTER_MODE_SERIAL) {
        return true; // Always connected for UART
    }

#if (ACTIVE_PRINTER_MODE == PRINTER_MODE_W5500_ETH)
    if (_mode == PRINTER_MODE_W5500_ETH) {
        if (_ethClient.connected()) {
            return true;
        }

        Serial.printf("[PRINTER] Connecting via W5500 Ethernet to %s:%d...\n", PRINTER_IP_ADDR, PRINTER_TCP_PORT);
        IPAddress targetIP;
        targetIP.fromString(PRINTER_IP_ADDR);
        if (_ethClient.connect(targetIP, PRINTER_TCP_PORT)) {
            _outputStream = &_ethClient;
            Serial.println("[PRINTER] Connected successfully via W5500 direct Ethernet port 9100!");
            init();
            return true;
        }

        Serial.println("[PRINTER] ERROR: Failed to connect to printer via W5500 direct Ethernet.");
        _outputStream = nullptr;
        return false;
    }
#elif (ACTIVE_PRINTER_MODE == PRINTER_MODE_WIFI_TCP)
    if (_tcpClient.connected()) {
        return true;
    }

    Serial.printf("[PRINTER] Connecting to printer at %s:%d...\n", PRINTER_IP_ADDR, PRINTER_TCP_PORT);
    if (_tcpClient.connect(PRINTER_IP_ADDR, PRINTER_TCP_PORT, PRINTER_CONNECT_TIMEOUT)) {
        _outputStream = &_tcpClient;
        Serial.println("[PRINTER] Connected successfully via TCP port 9100!");
        init();
        return true;
    }

    Serial.println("[PRINTER] ERROR: Failed to connect to printer via TCP port 9100.");
    _outputStream = nullptr;
    return false;
#endif
    return false;
}

void EscPosPrinter::disconnect() {
#if (ACTIVE_PRINTER_MODE == PRINTER_MODE_W5500_ETH)
    if (_mode == PRINTER_MODE_W5500_ETH && _ethClient.connected()) {
        _ethClient.flush();
        delay(250);
        _ethClient.stop();
        _outputStream = nullptr;
        Serial.println("[PRINTER] Disconnected W5500 Ethernet socket.");
    }
#elif (ACTIVE_PRINTER_MODE == PRINTER_MODE_WIFI_TCP)
    if (_mode != PRINTER_MODE_SERIAL && _tcpClient.connected()) {
        _tcpClient.flush();
        delay(250);
        _tcpClient.stop();
        _outputStream = nullptr;
        Serial.println("[PRINTER] Disconnected TCP socket.");
    }
#endif
}

bool EscPosPrinter::isConnected() {
    if (_mode == PRINTER_MODE_SERIAL) {
        return (_serial != nullptr);
    }
#if (ACTIVE_PRINTER_MODE == PRINTER_MODE_W5500_ETH)
    return _ethClient.connected();
#elif (ACTIVE_PRINTER_MODE == PRINTER_MODE_WIFI_TCP)
    return _tcpClient.connected();
#else
    return false;
#endif
}

bool EscPosPrinter::isPrinterOnline(uint32_t timeoutMs, bool waitForLink) {
    if (_mode == PRINTER_MODE_SERIAL) {
        return (_serial != nullptr);
    }
#if (ACTIVE_PRINTER_MODE == PRINTER_MODE_W5500_ETH)
    static unsigned long lastSuccessMs = 0;
    static bool wasOnline = false;
    unsigned long now = millis();

    if (_ethClient.connected()) {
        wasOnline = true;
        lastSuccessMs = now;
        return true;
    }

    // Fast physical PHY link check (zero-latency SPI read, ~50 microseconds).
    // In loop() polling (waitForLink == false), return false immediately when LinkOFF.
    // At boot (waitForLink == true), wait up to timeoutMs for W5500 PHY auto-negotiation.
    unsigned long probeStartMs = now;
    if (Ethernet.linkStatus() == LinkOFF) {
        if (!waitForLink) {
            wasOnline = false;
            lastSuccessMs = 0;
            return false;
        }
        while (Ethernet.linkStatus() == LinkOFF && (millis() - probeStartMs < timeoutMs)) {
            delay(50);
            yield();
        }
        if (Ethernet.linkStatus() == LinkOFF) {
            wasOnline = false;
            lastSuccessMs = 0;
            return false;
        }
    }

    // Cache a recent successful probe for up to 1000ms so we do not flood the printer's
    // embedded TCP stack with 5 new TCP connections per second during idle loop polling.
    if (!waitForLink && wasOnline && (now - lastSuccessMs < 1000)) {
        return true;
    }

    // PHY link is ON. Probe TCP port 9100 with bounded retransmission
    // to prevent blocking the ESP32 CPU loop if the printer IP is temporarily unreachable.
    uint32_t elapsed = millis() - probeStartMs;
    uint32_t remaining = (timeoutMs > elapsed) ? (timeoutMs - elapsed) : 200;
    uint16_t rtr = (uint16_t)min(max(remaining, (uint32_t)200), (uint32_t)500);
    Ethernet.setRetransmissionTimeout(rtr);
    Ethernet.setRetransmissionCount(1);

    EthernetClient probe;
    IPAddress targetIP;
    targetIP.fromString(PRINTER_IP_ADDR);
    bool online = probe.connect(targetIP, PRINTER_TCP_PORT);
    if (!online && waitForLink && (millis() - probeStartMs + 150 < timeoutMs)) {
        // Brief retry if PHY link just came up and printer ARP/TCP stack is settling
        delay(100);
        yield();
        online = probe.connect(targetIP, PRINTER_TCP_PORT);
    }
    if (online) {
        probe.stop();
        wasOnline = true;
        lastSuccessMs = millis();
    } else {
        wasOnline = false;
    }

    // Restore standard retransmission parameters for print jobs
    Ethernet.setRetransmissionTimeout(2000);
    Ethernet.setRetransmissionCount(8);

    return online;
#elif (ACTIVE_PRINTER_MODE == PRINTER_MODE_WIFI_TCP)
    static unsigned long lastSuccessMs = 0;
    static bool wasOnline = false;
    unsigned long now = millis();

    if (_tcpClient.connected()) {
        wasOnline = true;
        lastSuccessMs = now;
        return true;
    }
    if (wasOnline && (now - lastSuccessMs < 1000)) {
        return true;
    }
    WiFiClient probe;
    if (probe.connect(PRINTER_IP_ADDR, PRINTER_TCP_PORT, timeoutMs)) {
        probe.stop();
        wasOnline = true;
        lastSuccessMs = now;
        return true;
    }
    wasOnline = false;
    return false;
#else
    return false;
#endif
}

bool EscPosPrinter::writeAll(const uint8_t* data, size_t len, uint32_t timeoutMs) {
    if (!_outputStream || !data || len == 0) return (_outputStream != nullptr && len == 0);
    size_t sent = 0;
    unsigned long startMs = millis();
    while (sent < len) {
        size_t chunk = len - sent;
        if (_mode == PRINTER_MODE_SERIAL && chunk > 512) chunk = 512;
        else if (_mode != PRINTER_MODE_SERIAL && chunk > 2048) chunk = 2048;

        size_t written = _outputStream->write(data + sent, chunk);
        if (written > 0) {
            sent += written;
            startMs = millis();
            if (_mode == PRINTER_MODE_SERIAL) {
                delay(10); // Flow-control pacing for UART hardware buffer
            }
        } else {
            if (millis() - startMs >= timeoutMs) {
                Serial.println("[PRINTER] ERROR: Stream write timeout.");
                return false;
            }
            delay(2);
        }
        yield();
    }
    return true;
}

void EscPosPrinter::sendCommand(const uint8_t* cmd, size_t length) {
    if (_outputStream) {
        writeAll(cmd, length);
    }
}

void EscPosPrinter::init() {
    const uint8_t cmd[] = { 0x1B, 0x40 }; // ESC @
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::setAlign(TextAlignment align) {
    uint8_t val = 0;
    if (align == ALIGN_CENTER) val = 1;
    else if (align == ALIGN_RIGHT) val = 2;
    
    const uint8_t cmd[] = { 0x1B, 0x61, val }; // ESC a n
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::setBold(bool enable) {
    const uint8_t cmd[] = { 0x1B, 0x45, (uint8_t)(enable ? 1 : 0) }; // ESC E n
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::setUnderline(uint8_t mode) {
    const uint8_t cmd[] = { 0x1B, 0x2D, mode }; // ESC - n
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::setInvert(bool enable) {
    const uint8_t cmd[] = { 0x1D, 0x42, (uint8_t)(enable ? 1 : 0) }; // GS B n
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::setTextSize(uint8_t widthMultiplier, uint8_t heightMultiplier) {
    if (widthMultiplier < 1) widthMultiplier = 1;
    if (widthMultiplier > 8) widthMultiplier = 8;
    if (heightMultiplier < 1) heightMultiplier = 1;
    if (heightMultiplier > 8) heightMultiplier = 8;

    uint8_t n = ((widthMultiplier - 1) << 4) | (heightMultiplier - 1);
    const uint8_t cmd[] = { 0x1D, 0x21, n }; // GS ! n
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::setFontB(bool enable) {
    const uint8_t cmd[] = { 0x1B, 0x4D, (uint8_t)(enable ? 1 : 0) }; // ESC M n
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::print(const String& text) {
    if (_outputStream) {
        _outputStream->print(text);
    }
}

void EscPosPrinter::println(const String& text) {
    if (_outputStream) {
        if (text.length() > 0) {
            _outputStream->print(text);
        }
        _outputStream->write(0x0A); // LF
    }
}

void EscPosPrinter::print(const char* text) {
    if (_outputStream && text) {
        _outputStream->print(text);
    }
}

void EscPosPrinter::println(const char* text) {
    if (_outputStream) {
        if (text && text[0] != '\0') {
            _outputStream->print(text);
        }
        _outputStream->write(0x0A); // LF
    }
}

void EscPosPrinter::feed(uint8_t lines) {
    const uint8_t cmd[] = { 0x1B, 0x64, lines }; // ESC d n
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::cut(bool fullCut) {
    // Feed 3 lines then cut
    // GS V m n (m=65 full cut, m=66 partial cut)
    uint8_t cutType = fullCut ? 65 : 66;
    const uint8_t cmd[] = { 0x1D, 0x56, cutType, 0x03 };
    sendCommand(cmd, sizeof(cmd));
}

void EscPosPrinter::printHorizontalLine(char pattern) {
    setAlign(ALIGN_LEFT);
    char line[CHARACTERS_PER_LINE_A + 1];
    memset(line, pattern, CHARACTERS_PER_LINE_A);
    line[CHARACTERS_PER_LINE_A] = '\0';
    println(line);
}

void EscPosPrinter::printDoubleLine() {
    printHorizontalLine('=');
}

void EscPosPrinter::printHeader(const String& title, const String& subtitle) {
    printDoubleLine();
    setAlign(ALIGN_CENTER);

    setBold(true);
    setTextSize(2, 2);
    println(title);

    setTextSize(1, 1);
    setBold(false);

    if (subtitle.length() > 0) {
        println(subtitle);
    }
    printDoubleLine();
    setAlign(ALIGN_LEFT);
}

void EscPosPrinter::printMasterFooter(const char* closingTagline, bool includeScheduleHint, bool leadingRule) {
    if (leadingRule) {
        printHorizontalLine('-');
    }
    setAlign(ALIGN_CENTER);
    if (closingTagline && closingTagline[0] != '\0') {
        println(closingTagline);
        println("");
    }
    println("For more puzzles, toggle the power");
    println("on the front of the printer.");
    println("");
    println("To change settings, toggle the power");
    println("on the cable behind the printer.");
    if (includeScheduleHint) {
        println("");
        println("To schedule daily puzzles, go to settings.");
    }
    printHorizontalLine('-');
}

void EscPosPrinter::printRasterHeader(const char* title, const char* subtitle, const char* mixSubtitle) {
    ThermalCanvas canvas;
    uint16_t h = ThermalCanvas::measureMasterHeaderHeight(canvas, title, subtitle, mixSubtitle);
    canvas.renderBanded(*this, h, [&](ThermalCanvas& c) {
        c.drawMasterHeader(title, subtitle, mixSubtitle);
    });
}

void EscPosPrinter::printRasterPuzzleHeader(const char* title, const char* diffStr,
                                            const char* instr1, const char* instr2) {
    char combined[192];
    const char* instr = nullptr;
    if (instr1 && instr1[0] != '\0') {
        if (instr2 && instr2[0] != '\0') {
            snprintf(combined, sizeof(combined), "%s %s", instr1, instr2);
            instr = combined;
        } else {
            instr = instr1;
        }
    } else if (instr2 && instr2[0] != '\0') {
        instr = instr2;
    }
    ThermalCanvas canvas;
    uint16_t h = ThermalCanvas::measurePuzzleHeaderHeight(canvas, title, diffStr, instr);
    canvas.renderBanded(*this, h, [&](ThermalCanvas& c) {
        c.drawPuzzleHeader(title, diffStr, instr);
    });
}

void EscPosPrinter::printRasterDivider() {
    ThermalCanvas canvas;
    uint16_t h = ThermalCanvas::getDividerHeight();
    canvas.renderBanded(*this, h, [&](ThermalCanvas& c) {
        c.drawDivider();
    });
}

void EscPosPrinter::printRasterMasterFooter(const char* closingTagline, bool includeScheduleHint, bool leadingRule) {
    ThermalCanvas canvas;
    uint16_t h = ThermalCanvas::measureMasterFooterHeight(canvas, closingTagline, includeScheduleHint, leadingRule);
    canvas.renderBanded(*this, h, [&](ThermalCanvas& c) {
        c.drawMasterFooter(closingTagline, includeScheduleHint, leadingRule);
    });
}

void EscPosPrinter::printKeyValue(const String& key, const String& value, int totalCols) {
    setAlign(ALIGN_LEFT);
    int keyLen = key.length();
    int valLen = value.length();
    int spaces = totalCols - keyLen - valLen;

    if (spaces < 1) {
        print(key);
        print(" ");
        println(value);
        return;
    }

    print(key);
    if (_outputStream) {
        char spaceBuf[65];
        int rem = spaces;
        while (rem > 0) {
            int n = (rem > 64) ? 64 : rem;
            memset(spaceBuf, ' ', n);
            writeAll((const uint8_t*)spaceBuf, (size_t)n);
            rem -= n;
        }
    }
    println(value);
}

size_t EscPosPrinter::writeRaw(const uint8_t* buffer, size_t size) {
    if (_outputStream && size > 0) {
        return writeAll(buffer, size) ? size : 0;
    }
    return 0;
}

bool EscPosPrinter::beginRasterBitmap(uint16_t widthDots, uint16_t totalHeightDots) {
    if (!_outputStream || widthDots == 0 || totalHeightDots == 0) return false;

    // Width must be rounded up to bytes (8 bits per byte)
    uint16_t widthBytes = (widthDots + 7) / 8;

    // Standard ESC/POS GS v 0 command:
    // Format: 0x1D, 0x76, 0x30, m, xL, xH, yL, yH, [data...]
    // m = 0 (normal density)
    const uint8_t header[] = {
        0x1D, 0x76, 0x30, 0x00,
        (uint8_t)(widthBytes & 0xFF),
        (uint8_t)((widthBytes >> 8) & 0xFF),
        (uint8_t)(totalHeightDots & 0xFF),
        (uint8_t)((totalHeightDots >> 8) & 0xFF)
    };
    return writeAll(header, sizeof(header));
}

bool EscPosPrinter::writeRasterRows(const uint8_t* rowData, size_t byteLen) {
    if (!_outputStream || !rowData || byteLen == 0) return false;
    return writeAll(rowData, byteLen);
}

void EscPosPrinter::endRasterBitmap() {
    feed(1);
}

void EscPosPrinter::printRasterBitmap(const uint8_t* bitmapData, uint16_t widthDots, uint16_t heightDots) {
    if (!bitmapData || heightDots == 0) return;
    if (!beginRasterBitmap(widthDots, heightDots)) return;
    size_t totalBytes = (size_t)((widthDots + 7) / 8) * heightDots;
    if (writeRasterRows(bitmapData, totalBytes)) {
        endRasterBitmap();
    }
}

void EscPosPrinter::printSelfTest(const String& ipAddress, const String& currentTimeStr) {
    if (!connect()) return;

    init();
    printHeader("PEN + PAPER PUZZLES", "Thermal Printer Diagnostic Test");
    
    println("");
    setBold(true);
    println("SYSTEM STATUS:");
    const char* ifaceName = (_mode == PRINTER_MODE_W5500_ETH) ? "Direct W5500 RJ45 (Port 9100)" : 
                            ((_mode == PRINTER_MODE_SERIAL) ? "Serial UART2" : "Wi-Fi TCP (Port 9100)");
    printKeyValue("Interface:", ifaceName);
    printKeyValue("ESP32 IP:", ipAddress);
    printKeyValue("Printer Target:", String(PRINTER_IP_ADDR) + ":" + String(PRINTER_TCP_PORT));
    printKeyValue("Date & Time:", currentTimeStr);
    printKeyValue("Paper Width:", String(PAPER_WIDTH_MM) + "mm (80mm)");
    printKeyValue("Printable Area:", String(PRINTABLE_WIDTH_DOTS) + " dots (72mm)");
    
    println("");
    setBold(true);
    println("TYPOGRAPHY & STYLES:");
    setBold(false);
    println("Standard Font A (48 columns per line):");
    println("123456789012345678901234567890123456789012345678");
    printHorizontalLine('.');
    
    setFontB(true);
    println("Condensed Font B (64 columns per line):");
    println("1234567890123456789012345678901234567890123456789012345678901234");
    setFontB(false);
    printHorizontalLine('.');

    setBold(true);
    println("Text Formatting: Bold active");
    setBold(false);
    setUnderline(1);
    println("Text Formatting: Underline active");
    setUnderline(0);

    setInvert(true);
    setAlign(ALIGN_CENTER);
    println(" INVERTED WHITE-ON-BLACK BANNER ");
    setInvert(false);
    setAlign(ALIGN_LEFT);

    println("");
    printHorizontalLine('=');
    setAlign(ALIGN_CENTER);
    println("Printer self-test successful!");
    println("Ready to fetch and print daily puzzles.");
    printHorizontalLine('=');

    feed(3);
    cut(false); // Partial cut
    disconnect();
}
