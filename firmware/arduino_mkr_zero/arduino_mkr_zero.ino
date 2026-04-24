#include <EEPROM.h>
#include <ArduinoJson.h>
#include "config.h"
#include "sensor.h"
#include "uart_comm.h"

static Sensor sensor;
static bool     ledState   = false;
static uint32_t intervalMs = INTERVAL_DEFAULT_MS;
static uint32_t sequenceNo = 0;
static uint32_t lastSendAt = 0;

static void loadIntervalFromEeprom() {
    uint8_t magic;
    EEPROM.get(EEPROM_ADDR_MAGIC, magic);
    if (magic != EEPROM_MAGIC_BYTE) return;

    uint32_t stored;
    EEPROM.get(EEPROM_ADDR_INTERVAL, stored);
    if (stored >= INTERVAL_MIN_MS && stored <= INTERVAL_MAX_MS) {
        intervalMs = stored;
    }
}

static void saveIntervalToEeprom(uint32_t value) {
    EEPROM.put(EEPROM_ADDR_INTERVAL, value);
    EEPROM.put(EEPROM_ADDR_MAGIC, EEPROM_MAGIC_BYTE);
}

static void applyCommand(const JsonDocument& doc) {
    const char* type = doc["type"];
    if (!type) return;

    if (strcmp(type, "setLed") == 0) {
        JsonVariantConst val = doc["value"];
        if (val.is<bool>()) {
            ledState = val.as<bool>();
            digitalWrite(LED_PIN, ledState ? HIGH : LOW);
        }
    } else if (strcmp(type, "setInterval") == 0) {
        JsonVariantConst val = doc["value"];
        if (val.is<int>()) {
            uint32_t v = val.as<uint32_t>();
            if (v >= INTERVAL_MIN_MS && v <= INTERVAL_MAX_MS) {
                if (v != intervalMs) {
                    intervalMs = v;
                    saveIntervalToEeprom(v);
                }
            }
        }
    }
}

void setup() {
    Serial.begin(UART_BAUDRATE);
    // Wait for USB-CDC enumeration (MKR Zero); give up after 5 s for headless boot.
    uint32_t deadline = millis() + 5000;
    while (!Serial && millis() < deadline) {}

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    loadIntervalFromEeprom();
    lastSendAt = millis();
}

void loop() {
    uint32_t now = millis();

    if (now - lastSendAt >= intervalMs) {
        sensor.update();
        uart_send_telemetry(DEVICE_ID, sensor.temperature(), sensor.humidity(),
                            ledState, intervalMs, sequenceNo++);
        lastSendAt = now;
    }

    StaticJsonDocument<192> cmdDoc;
    if (uart_try_read_command(cmdDoc)) {
        applyCommand(cmdDoc);
    }
}
