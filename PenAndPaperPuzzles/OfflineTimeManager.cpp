#include "OfflineTimeManager.h"
#include "OfflineConfigManager.h"
#include "EscPosPrinter.h"
#include "ThermalCanvas.h"
#include "OfflinePuzzleComposer.h"

OfflineTimeManager::OfflineTimeManager() :
    _timeSet(false),
    _lastPrintedYear(-1),
    _lastPrintedDay(-1),
    _portalActive(false),
    _ds3231Present(false),
    _portalStartedMs(0),
    _pendingExit(false),
    _pendingExitMs(0),
    _routesConfigured(false),
    _configManager(nullptr),
    _printer(nullptr),
    _server(80) {
}

void OfflineTimeManager::begin() {
    // 1. Check for optional DS3231 hardware RTC via board-aware I2C pins
    Wire.begin(RTC_I2C_SDA_PIN, RTC_I2C_SCL_PIN);
    Wire.beginTransmission(DS3231_I2C_ADDR);
    if (Wire.endTransmission() == 0) {
        _ds3231Present = true;
        Serial.println("[TIME] Found DS3231 hardware RTC on I2C (0x68)!");
        checkAndSyncFromDs3231();
    } else {
        Serial.println("[TIME] No DS3231 hardware RTC detected. Using internal timer / SoftAP sync.");
    }
}

uint8_t OfflineTimeManager::bcdToDec(uint8_t val) {
    return ((val / 16 * 10) + (val % 16));
}

uint8_t OfflineTimeManager::decToBcd(uint8_t val) {
    return ((val / 10 * 16) + (val % 10));
}

bool OfflineTimeManager::checkAndSyncFromDs3231() {
    if (!_ds3231Present) return false;

    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x00); // Start at register 0 (seconds)
    if (Wire.endTransmission() != 0) return false;

    Wire.requestFrom((uint8_t)DS3231_I2C_ADDR, (uint8_t)7);
    if (Wire.available() < 7) return false;

    uint8_t sec  = bcdToDec(Wire.read() & 0x7F);
    uint8_t min  = bcdToDec(Wire.read() & 0x7F);
    uint8_t hour = bcdToDec(Wire.read() & 0x3F);
    Wire.read(); // Day of week (unused)
    uint8_t day  = bcdToDec(Wire.read() & 0x3F);
    uint8_t mon  = bcdToDec(Wire.read() & 0x1F);
    uint16_t yr  = 2000 + bcdToDec(Wire.read());

    struct tm t;
    t.tm_sec  = sec;
    t.tm_min  = min;
    t.tm_hour = hour;
    t.tm_mday = day;
    t.tm_mon  = mon - 1;
    t.tm_year = yr - 1900;
    t.tm_isdst = -1;

    time_t epoch = mktime(&t);
    struct timeval tv = { epoch, 0 };
    settimeofday(&tv, nullptr);

    _timeSet = true;
    Serial.printf("[TIME] Synced time from DS3231: %04d-%02d-%02d %02d:%02d:%02d\n",
                  yr, mon, day, hour, min, sec);
    return true;
}

bool OfflineTimeManager::writeToDs3231(const struct tm& t) {
    if (!_ds3231Present) return false;

    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x00);
    Wire.write(decToBcd(t.tm_sec));
    Wire.write(decToBcd(t.tm_min));
    Wire.write(decToBcd(t.tm_hour));
    Wire.write(decToBcd(t.tm_wday + 1));
    Wire.write(decToBcd(t.tm_mday));
    Wire.write(decToBcd(t.tm_mon + 1));
    Wire.write(decToBcd((t.tm_year + 1900) % 100));
    return (Wire.endTransmission() == 0);
}

void OfflineTimeManager::setSystemTime(time_t epoch, int tzOffsetMinutes) {
    // Convert UTC epoch to local wall-clock epoch based on client timezone offset.
    // In JavaScript, Date.getTimezoneOffset() returns minutes that UTC is ahead of local time
    // (e.g. UTC-5 US Central is +300 min; UTC+9 Tokyo is -540 min).
    // Subtracting (tzOffsetMinutes * 60) converts UTC epoch to the client's local wall-clock time.
    time_t localEpoch = epoch - ((time_t)tzOffsetMinutes * 60);

    struct timeval tv = { localEpoch, 0 };
    settimeofday(&tv, nullptr);
    _timeSet = true;

    time_t now = time(nullptr);
    struct tm* t = localtime(&now);

    Serial.printf("[TIME] System clock set to local wall-clock: %04d-%02d-%02d %02d:%02d:%02d (TZ Offset: %d min applied)\n",
                  t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
                  t->tm_hour, t->tm_min, t->tm_sec, tzOffsetMinutes);

    if (_ds3231Present) {
        writeToDs3231(*t);
        Serial.println("[TIME] Persisted new local time to DS3231 hardware RTC.");
    }
}

void OfflineTimeManager::setSystemTime(int year, int month, int day, int hour, int minute, int second) {
    struct tm t;
    memset(&t, 0, sizeof(t));
    t.tm_sec  = second;
    t.tm_min  = minute;
    t.tm_hour = hour;
    t.tm_mday = day;
    t.tm_mon  = month - 1;
    t.tm_year = year - 1900;
    t.tm_isdst = -1;

    time_t localEpoch = mktime(&t);
    struct timeval tv = { localEpoch, 0 };
    settimeofday(&tv, nullptr);
    _timeSet = true;

    Serial.printf("[TIME] System clock set to device local wall-clock: %04d-%02d-%02d %02d:%02d:%02d\n",
                  year, month, day, hour, minute, second);

    if (_ds3231Present) {
        writeToDs3231(t);
        Serial.println("[TIME] Persisted new local time to DS3231 hardware RTC.");
    }
}

String OfflineTimeManager::getFormattedTime(const char* format) {
    if (!_timeSet) return "Time Not Set (Pending Sync)";

    time_t now = time(nullptr);
    struct tm* t = localtime(&now);
    char buf[64];
    strftime(buf, sizeof(buf), format, t);
    return String(buf);
}

bool OfflineTimeManager::isCronTriggerTime(uint8_t targetHour, uint8_t targetMinute) {
    if (!_timeSet) return false;

    time_t now = time(nullptr);
    struct tm* t = localtime(&now);

    if (t->tm_hour == targetHour && t->tm_min == targetMinute) {
        if (t->tm_year != _lastPrintedYear || t->tm_yday != _lastPrintedDay) {
            Serial.printf("[TIME] 7:00 AM Cron triggered at %02d:%02d!\n", targetHour, targetMinute);
            markPrintedToday();
            return true;
        }
    }
    return false;
}

void OfflineTimeManager::markPrintedToday() {
    time_t now = time(nullptr);
    struct tm* t = localtime(&now);
    _lastPrintedYear = t->tm_year;
    _lastPrintedDay  = t->tm_yday;
}

// -----------------------------------------------------------------------------
// SoftAP Web Setup Portal
// -----------------------------------------------------------------------------
void OfflineTimeManager::startSetupPortal() {
    Serial.println("\n[PORTAL] Starting SoftAP Web Configurator...");
#if (ACTIVE_PRINTER_MODE == PRINTER_MODE_WIFI_TCP)
    WiFi.mode(WIFI_AP_STA);
#else
    WiFi.mode(WIFI_AP);
#endif
    WiFi.setSleep(false); // Keep Wi-Fi radio fully active so beacons broadcast continuously
    IPAddress myIP(192, 168, 4, 1);
    IPAddress gateway(192, 168, 4, 1);
    IPAddress subnet(255, 255, 255, 0);
    WiFi.softAPConfig(myIP, gateway, subnet);
    WiFi.softAP("Pen-And-Paper-Puzzles", nullptr, 1, 0, 4);
    Serial.printf("[PORTAL] Hotspot started! SSID: Pen-And-Paper-Puzzles (Open Network)\n");
    Serial.printf("[PORTAL] Connect phone and visit: http://%s\n", myIP.toString().c_str());

    // Captive portal DNS server (redirect all domains to 192.168.4.1)
    _dnsServer.start(53, "*", myIP);

    setupWebRoutes();
    _server.begin();
    _portalActive = true;
    _portalStartedMs = millis();
    _pendingExit = false;
}

void OfflineTimeManager::stopSetupPortal() {
    if (_portalActive) {
        _server.stop();
        _dnsServer.stop();
        WiFi.softAPdisconnect(true);
#if (ACTIVE_PRINTER_MODE == PRINTER_MODE_WIFI_TCP)
        WiFi.mode(WIFI_STA);
        WiFi.reconnect();
#else
        WiFi.mode(WIFI_OFF);
#endif
        _portalActive = false;
        _pendingExit = false;
        Serial.println("[PORTAL] SoftAP Setup Portal closed.");
    }
}

void OfflineTimeManager::handleClient() {
    if (_portalActive) {
        _dnsServer.processNextRequest();
        _server.handleClient();

        // 5-minute auto-timeout (300,000 ms)
        if (millis() - _portalStartedMs > 300000) {
            Serial.println("[PORTAL] 5-minute inactivity timeout reached -> Auto-closing hotspot.");
            stopSetupPortal();
            return;
        }

        // Pending delayed exit after saving config
        if (_pendingExit && millis() - _pendingExitMs > 1200) {
            _pendingExit = false;
            stopSetupPortal();
        }
    }
}

void OfflineTimeManager::printSetupTicket(EscPosPrinter& printer, const OfflineConfigManager* config) {
    if (!config) {
        config = _configManager;
    }

    if (!printer.isConnected()) {
        if (!printer.connect()) {
            Serial.println("[PORTAL] ERROR: Failed to connect to printer for setup ticket.");
            return;
        }
    }

    printer.init();
    printer.printRasterHeader("PEN + PAPER PUZZLES", nullptr);

    if (config) {
        OfflinePuzzleType activeGames[OFFLINE_PUZZLE_TOTAL];
        uint8_t activeCount = 0;

        for (uint8_t i = 0; i < (uint8_t)OFFLINE_PUZZLE_TOTAL; i++) {
            if (config->isGameEnabled((OfflinePuzzleType)i)) {
                activeGames[activeCount++] = (OfflinePuzzleType)i;
            }
        }

        uint8_t rows = (activeCount + 1) / 2;
        if (rows == 0) rows = 1;

        ThermalCanvas tc;
        int16_t bodyRowH = (int16_t)tc.getFontLineHeight(FONT_BODY_20) + 4;
        int16_t kvRowH = (int16_t)tc.getFontLineHeight(FONT_SUBHEAD_22) + 4;
        uint16_t h = 4 + tc.measureWrappedHeightFont("These are the games that are currently active to print:", 536, FONT_BODY_20, 4) + 12;
        h += (uint16_t)rows * (uint16_t)bodyRowH + 18 + 3 * (uint16_t)kvRowH + 8;
        h = (uint16_t)((h + 7) & ~7);

        String countVal = String(config->getPuzzleCount()) + " Puzzles";
        const char* diffVal = config->getGradeName(config->getPuzzleGrade());
        String schedVal = _timeSet ? config->getDailyScheduleTimeString() : String("(Setup instructions below)");

        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            int16_t curY = 4;
            int16_t bulletOff = (int16_t)(c.getFontLineHeight(FONT_BODY_20) / 2);
            curY += c.drawWrappedTextFont(20, curY, 536,
                                          "These are the games that are currently active to print:",
                                          FONT_BODY_20, 1, 4) + 12;
            for (uint8_t r = 0; r < rows; r++) {
                if (r < activeCount) {
                    c.fillCircle(28, curY + bulletOff, 2, 1);
                    c.drawTextFont(38, curY, config->getPuzzleName(activeGames[r]), FONT_BODY_20);
                } else if (activeCount == 0 && r == 0) {
                    c.drawTextFont(38, curY, "(None)", FONT_BODY_20);
                }
                uint8_t rightIdx = r + rows;
                if (rightIdx < activeCount) {
                    c.fillCircle(296, curY + bulletOff, 2, 1);
                    c.drawTextFont(306, curY, config->getPuzzleName(activeGames[rightIdx]), FONT_BODY_20);
                }
                curY += bodyRowH;
            }
            curY += 8;
            c.drawHLine(20, curY, 536, 1, 1);
            curY += 10;
            c.drawTextFont(20, curY + 4, "Daily Count", FONT_BODY_20);
            c.drawRightTextFont(556, curY, countVal.c_str(), FONT_SUBHEAD_22);
            curY += kvRowH;
            c.drawTextFont(20, curY + 4, "Difficulty", FONT_BODY_20);
            c.drawRightTextFont(556, curY, diffVal, FONT_SUBHEAD_22);
            curY += kvRowH;
            c.drawTextFont(20, curY + 4, "Daily Schedule", FONT_BODY_20);
            c.drawRightTextFont(556, curY, schedVal.c_str(), FONT_SUBHEAD_22);
        });
    }

    // Setup Mode Section
    printer.printRasterPuzzleHeader("SETUP MODE", nullptr,
                                    "To customize your games, schedule, or clock, follow the instructions below:");

    // Step 1: Wi-Fi
    printer.printRasterPuzzleHeader("STEP 1: JOIN WI-FI", nullptr,
                                    "Scan the QR code below to connect to the setup hotspot:");

    ThermalCanvas canvas;
    canvas.renderBanded(printer, 240, [&](ThermalCanvas& c) {
        c.drawQrCode(288, 120, "WIFI:T:nopass;S:Pen-And-Paper-Puzzles;;", 6);
    });
    {
        ThermalCanvas tc;
        int16_t subH = (int16_t)tc.getFontLineHeight(FONT_SUBHEAD_22);
        int16_t capH = (int16_t)tc.getFontLineHeight(FONT_CAPTION_16);
        uint16_t h = (uint16_t)((4 + subH + 4 + capH + 8 + 7) & ~7);
        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            c.drawCenteredTextFont(4, "Network: Pen-And-Paper-Puzzles", FONT_SUBHEAD_22);
            c.drawCenteredTextFont(4 + subH + 4, "(Open Network - No Password)", FONT_CAPTION_16);
        });
    }

    // Step 2: Settings URL
    printer.printRasterPuzzleHeader("STEP 2: OPEN SETTINGS", nullptr,
                                    "Scan the QR code to set up your games:");

    canvas.renderBanded(printer, 216, [&](ThermalCanvas& c) {
        c.drawQrCode(288, 108, "http://192.168.4.1", 6);
    });
    {
        ThermalCanvas tc;
        uint16_t h = (uint16_t)((4 + tc.getFontLineHeight(FONT_SUBHEAD_22) + 8 + 7) & ~7);
        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            c.drawCenteredTextFont(4, "URL: http://192.168.4.1", FONT_SUBHEAD_22);
        });
    }

    // Step 3: Customize & Save
    printer.printRasterPuzzleHeader("STEP 3: CUSTOMIZE & SAVE", nullptr,
                                    "Customize your game selection and schedule:");
    {
        ThermalCanvas tc;
        int16_t bodyRowH = (int16_t)tc.getFontLineHeight(FONT_BODY_20) + 4;
        int16_t subH = (int16_t)tc.getFontLineHeight(FONT_SUBHEAD_22);
        uint16_t h = (uint16_t)((4 + 4 * bodyRowH + 10 + subH + 8 + 7) & ~7);
        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            int16_t curY = 4;
            int16_t bulletOff = (int16_t)(c.getFontLineHeight(FONT_BODY_20) / 2);
            const char* bullets[4] = {
                "Select which games to get",
                "How many games to print",
                "Choose your difficulty level",
                "Set if you want daily prints"
            };
            for (uint8_t i = 0; i < 4; i++) {
                c.fillCircle(44, curY + bulletOff, 2, 1);
                c.drawTextFont(56, curY, bullets[i], FONT_BODY_20);
                curY += bodyRowH;
            }
            curY += 10;
            c.drawCenteredTextFont(curY, "Click Save to apply your settings.", FONT_SUBHEAD_22);
        });
    }

    // Footer
    printer.printRasterMasterFooter("Enjoy your day!", (!config || !config->isDailyScheduleEnabled()), true);

    printer.feed(4);
    printer.cut(false);
    printer.disconnect();
    Serial.println("[PORTAL] Printed setup ticket with dual QR codes!");
}

void OfflineTimeManager::printConfigSavedTicket(EscPosPrinter& printer, const OfflineConfigManager& config) {
    if (!printer.isConnected()) {
        if (!printer.connect()) {
            Serial.println("[PORTAL] ERROR: Failed to connect to printer for config saved ticket.");
            return;
        }
    }

    printer.init();
    printer.printRasterHeader("PEN + PAPER PUZZLES", "Configuration Saved");

    // Categorize active and inactive games
    OfflinePuzzleType activeGames[OFFLINE_PUZZLE_TOTAL];
    uint8_t activeCount = 0;
    OfflinePuzzleType inactiveGames[OFFLINE_PUZZLE_TOTAL];
    uint8_t inactiveCount = 0;

    for (uint8_t i = 0; i < (uint8_t)OFFLINE_PUZZLE_TOTAL; i++) {
        if (config.isGameEnabled((OfflinePuzzleType)i)) {
            activeGames[activeCount++] = (OfflinePuzzleType)i;
        } else {
            inactiveGames[inactiveCount++] = (OfflinePuzzleType)i;
        }
    }

    uint8_t maxRows = (activeCount > inactiveCount) ? activeCount : inactiveCount;
    if (maxRows == 0) maxRows = 1;

    {
        ThermalCanvas tc;
        int16_t capH = (int16_t)tc.getFontLineHeight(FONT_CAPTION_16);
        int16_t bodyRowH = (int16_t)tc.getFontLineHeight(FONT_BODY_20) + 4;
        uint16_t h = (uint16_t)((4 + capH + 6 + (uint16_t)maxRows * (uint16_t)bodyRowH + 16 + 7) & ~7);
        char leftHdr[32], rightHdr[32];
        snprintf(leftHdr, sizeof(leftHdr), "ACTIVE (%d)", (int)activeCount);
        snprintf(rightHdr, sizeof(rightHdr), "INACTIVE (%d)", (int)inactiveCount);

        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            int16_t curY = 4;
            int16_t bulletOff = (int16_t)(c.getFontLineHeight(FONT_BODY_20) / 2);
            c.drawTextFont(20, curY, leftHdr, FONT_CAPTION_16);
            c.drawTextFont(296, curY, rightHdr, FONT_CAPTION_16);
            curY += capH + 6;
            for (uint8_t row = 0; row < maxRows; row++) {
                if (row < activeCount) {
                    c.fillCircle(28, curY + bulletOff, 2, 1);
                    c.drawTextFont(38, curY, config.getPuzzleName(activeGames[row]), FONT_BODY_20);
                } else if (activeCount == 0 && row == 0) {
                    c.drawTextFont(38, curY, "(None)", FONT_BODY_20);
                }
                if (row < inactiveCount) {
                    c.fillCircle(296, curY + bulletOff, 2, 1);
                    c.drawTextFont(306, curY, config.getPuzzleName(inactiveGames[row]), FONT_BODY_20);
                } else if (inactiveCount == 0 && row == 0) {
                    c.drawTextFont(306, curY, "(None)", FONT_BODY_20);
                }
                curY += bodyRowH;
            }
        });
    }

    // Settings Section with Standard Separator
    printer.printRasterPuzzleHeader("SETTINGS", nullptr, nullptr);

    {
        ThermalCanvas tc;
        int16_t kvRowH = (int16_t)tc.getFontLineHeight(FONT_SUBHEAD_22) + 4;
        uint16_t h = (uint16_t)((4 + 4 * kvRowH + 16 + 7) & ~7);
        String countVal = String(config.getPuzzleCount()) + " Puzzles";
        const char* diffVal = config.getGradeName(config.getPuzzleGrade());
        String schedVal = config.getDailyScheduleTimeString();
        String clockVal = getFormattedTime("%I:%M %p");

        tc.renderBanded(printer, h, [&](ThermalCanvas& c) {
            int16_t curY = 4;
            c.drawTextFont(20, curY + 4, "Daily Count", FONT_BODY_20);
            c.drawRightTextFont(556, curY, countVal.c_str(), FONT_SUBHEAD_22);
            curY += kvRowH;
            c.drawTextFont(20, curY + 4, "Difficulty", FONT_BODY_20);
            c.drawRightTextFont(556, curY, diffVal, FONT_SUBHEAD_22);
            curY += kvRowH;
            c.drawTextFont(20, curY + 4, "Daily Schedule", FONT_BODY_20);
            c.drawRightTextFont(556, curY, schedVal.c_str(), FONT_SUBHEAD_22);
            curY += kvRowH;
            c.drawTextFont(20, curY + 4, "Clock", FONT_BODY_20);
            c.drawRightTextFont(556, curY, clockVal.c_str(), FONT_SUBHEAD_22);
        });
    }

    // Footer
    printer.printRasterMasterFooter("Setup complete. Ready for printing!", !config.isDailyScheduleEnabled(), true);

    printer.feed(4);
    printer.cut(false);
    printer.disconnect();
    Serial.println("[PORTAL] Printed configuration saved confirmation ticket!");
}

#include "PortalHtml.h"

void OfflineTimeManager::setupWebRoutes() {
    if (_routesConfigured) {
        return;
    }
    _routesConfigured = true;

    _server.on("/", HTTP_GET, [this]() {
        _portalStartedMs = millis();
        _server.sendHeader("Content-Encoding", "gzip");
        _server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
        _server.send_P(200, "text/html", (const char*)PORTAL_HTML_GZ, sizeof(PORTAL_HTML_GZ));
    });

    _server.on("/api/config", HTTP_GET, [this]() {
        _portalStartedMs = millis();
        const uint32_t allMask = (1UL << (uint8_t)OFFLINE_PUZZLE_TOTAL) - 1UL;
        uint32_t mask = _configManager ? _configManager->getGameMask() : allMask;
        uint8_t count = _configManager ? _configManager->getPuzzleCount() : 5;
        uint8_t grade = _configManager ? (uint8_t)_configManager->getPuzzleGrade() : 3;
        bool schedEn = _configManager ? _configManager->isDailyScheduleEnabled() : true;
        uint8_t schedHr = _configManager ? _configManager->getDailyScheduleHour() : 7;
        uint8_t schedMin = _configManager ? _configManager->getDailyScheduleMinute() : 0;
        String timeStr = getFormattedTime("%I:%M %p");
        char jsonBuf[256];
        snprintf(jsonBuf, sizeof(jsonBuf),
                 "{\"mask\":%lu,\"count\":%u,\"grade\":%u,\"schedEnabled\":%s,\"schedHour\":%u,\"schedMinute\":%u,\"time\":\"%s\",\"timeSet\":%s}",
                 (unsigned long)mask, (unsigned)count, (unsigned)grade,
                 schedEn ? "true" : "false", (unsigned)schedHr, (unsigned)schedMin,
                 timeStr.c_str(), _timeSet ? "true" : "false");
        _server.send(200, "application/json", jsonBuf);
    });

    auto handleSaveConfig = [this]() {
        _portalStartedMs = millis();
        if (_server.hasArg("mask") && _server.hasArg("count") && _server.hasArg("grade")) {
            uint32_t mask = (uint32_t)strtoul(_server.arg("mask").c_str(), NULL, 10);
            uint8_t count = (uint8_t)_server.arg("count").toInt();
            uint8_t grade = (uint8_t)_server.arg("grade").toInt();

            // Automatically sync device clock from client device local time
            if (_server.hasArg("year") && _server.hasArg("hour")) {
                int y  = _server.arg("year").toInt();
                int mo = _server.hasArg("month") ? _server.arg("month").toInt() : 1;
                int d  = _server.hasArg("day") ? _server.arg("day").toInt() : 1;
                int h  = _server.arg("hour").toInt();
                int mi = _server.hasArg("min") ? _server.arg("min").toInt() : 0;
                int s  = _server.hasArg("sec") ? _server.arg("sec").toInt() : 0;
                setSystemTime(y, mo, d, h, mi, s);
            } else if (_server.hasArg("epoch")) {
                long epoch = (long)strtoul(_server.arg("epoch").c_str(), NULL, 10);
                int tzOffset = _server.hasArg("tz") ? _server.arg("tz").toInt() : 0;
                setSystemTime(epoch, tzOffset);
            }

            if (_configManager) {
                _configManager->setGameMask(mask);
                _configManager->setPuzzleCount(count);
                _configManager->setPuzzleGrade((PuzzleGrade)grade);

                if (_server.hasArg("schedEnabled")) {
                    bool schedEn = (_server.arg("schedEnabled") == "1" || _server.arg("schedEnabled") == "true");
                    _configManager->setDailyScheduleEnabled(schedEn);
                }
                if (_server.hasArg("schedHour")) {
                    uint8_t schedHr = (uint8_t)_server.arg("schedHour").toInt();
                    _configManager->setDailyScheduleHour(schedHr);
                }
                if (_server.hasArg("schedMinute")) {
                    uint8_t schedMin = (uint8_t)_server.arg("schedMinute").toInt();
                    _configManager->setDailyScheduleMinute(schedMin);
                }

                _configManager->save();
                Serial.printf("[PORTAL] Saved configuration: Mask=0x%04X, Count=%d, Grade=%d, Schedule=%s\n",
                              mask, count, grade, _configManager->getDailyScheduleTimeString().c_str());
            }

            // Send HTTP response immediately before slow printer I/O
            _server.send(200, "application/json", "{\"status\":\"ok\"}");
            if (_configManager && _printer) {
                printConfigSavedTicket(*_printer, *_configManager);
            }
            _pendingExit = true;
            _pendingExitMs = millis();
        } else {
            _server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Missing parameters\"}");
        }
    };
    _server.on("/api/save-config", HTTP_POST, handleSaveConfig);
    _server.on("/api/save-config", HTTP_GET, handleSaveConfig);

    _server.on("/api/set-time", HTTP_GET, [this]() {
        _portalStartedMs = millis();
        if (_server.hasArg("year") && _server.hasArg("hour")) {
            int y  = _server.arg("year").toInt();
            int mo = _server.hasArg("month") ? _server.arg("month").toInt() : 1;
            int d  = _server.hasArg("day") ? _server.arg("day").toInt() : 1;
            int h  = _server.arg("hour").toInt();
            int mi = _server.hasArg("min") ? _server.arg("min").toInt() : 0;
            int s  = _server.hasArg("sec") ? _server.arg("sec").toInt() : 0;
            setSystemTime(y, mo, d, h, mi, s);

            String timeStr = getFormattedTime("%I:%M %p");
            char jsonBuf[128];
            snprintf(jsonBuf, sizeof(jsonBuf), "{\"status\":\"ok\",\"time\":\"%s\"}", timeStr.c_str());
            _server.send(200, "application/json", jsonBuf);
        } else if (_server.hasArg("epoch")) {
            long epoch = (long)strtoul(_server.arg("epoch").c_str(), NULL, 10);
            int tzOffset = _server.hasArg("tz") ? _server.arg("tz").toInt() : 0;
            setSystemTime(epoch, tzOffset);

            String timeStr = getFormattedTime("%I:%M %p");
            char jsonBuf[128];
            snprintf(jsonBuf, sizeof(jsonBuf), "{\"status\":\"ok\",\"time\":\"%s\"}", timeStr.c_str());
            _server.send(200, "application/json", jsonBuf);
        } else {
            _server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Missing time parameters\"}");
        }
    });

    _server.on("/api/status", HTTP_GET, [this]() {
        _portalStartedMs = millis();
        String timeStr = getFormattedTime();
        char jsonBuf[160];
        snprintf(jsonBuf, sizeof(jsonBuf), "{\"timeSet\":%s,\"time\":\"%s\"}",
                 _timeSet ? "true" : "false", timeStr.c_str());
        _server.send(200, "application/json", jsonBuf);
    });

    _server.on("/api/print-guide", HTTP_GET, [this]() {
        _portalStartedMs = millis();
        if (_server.hasArg("game")) {
            uint8_t gameId = (uint8_t)_server.arg("game").toInt();
            if (_printer) {
                OfflinePuzzleComposer composer;
                bool success = composer.printGameGuide(*_printer, gameId);
                if (success) {
                    char jsonBuf[64];
                    snprintf(jsonBuf, sizeof(jsonBuf), "{\"status\":\"ok\",\"game\":%u}", (unsigned)gameId);
                    _server.send(200, "application/json", jsonBuf);
                    return;
                }
            }
            _server.send(500, "application/json", "{\"status\":\"error\",\"message\":\"Printing failed\"}");
        } else {
            _server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Missing game parameter\"}");
        }
    });

    _server.on("/api/print-sample", HTTP_GET, [this]() {
        _portalStartedMs = millis();
        if (_server.hasArg("game")) {
            uint8_t gameId = (uint8_t)_server.arg("game").toInt();
            if (_printer) {
                OfflinePuzzleComposer composer;
                bool success = composer.printGameSampler(*_printer, gameId);
                if (success) {
                    char jsonBuf[64];
                    snprintf(jsonBuf, sizeof(jsonBuf), "{\"status\":\"ok\",\"game\":%u}", (unsigned)gameId);
                    _server.send(200, "application/json", jsonBuf);
                    return;
                }
            }
            _server.send(500, "application/json", "{\"status\":\"error\",\"message\":\"Printing failed\"}");
        } else {
            _server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Missing game parameter\"}");
        }
    });

    _server.on("/api/exit", HTTP_GET, [this]() {
        _portalStartedMs = millis();
        _server.send(200, "text/html", "<body style='background:#0f172a;color:#f8fafc;font-family:sans-serif;padding:30px;text-align:center;'><h2>Setup portal closing.</h2><p>Ready for morning puzzles!</p></body>");
        _pendingExit = true;
        _pendingExitMs = millis();
    });

    // Captive portal handler for mobile redirect
    _server.onNotFound([this]() {
        _server.sendHeader("Location", "http://192.168.4.1/", true);
        _server.send(302, "text/plain", "");
    });
}


