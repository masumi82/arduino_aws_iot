#include "uart_comm.h"
#include "config.h"

static char _rxBuf[UART_MAX_FRAME_BYTES + 1];
static uint16_t _rxLen = 0;
static bool _rxDiscard = false;  // true while discarding an oversized frame

void uart_send_telemetry(const char* deviceId, float tempC, float humidPct,
                         bool ledState, uint32_t intervalMs, uint32_t seqNo) {
    StaticJsonDocument<256> doc;
    doc["schemaVersion"] = SCHEMA_VERSION;
    doc["deviceId"]      = deviceId;
    doc["timestamp"]     = 0;  // Gateway overwrites with RPi time
    doc["temperatureC"]  = tempC;
    doc["humidityPct"]   = humidPct;
    doc["ledState"]      = ledState;
    doc["intervalMs"]    = intervalMs;
    doc["sequenceNo"]    = seqNo;
    serializeJson(doc, Serial);
    Serial.print('\n');
}

bool uart_try_read_command(JsonDocument& outDoc) {
    while (Serial.available()) {
        char c = Serial.read();

        if (_rxDiscard) {
            if (c == '\n') _rxDiscard = false;  // re-sync complete
            continue;
        }

        if (c == '\n') {
            _rxBuf[_rxLen] = '\0';
            bool ok = (_rxLen > 0) &&
                      (deserializeJson(outDoc, _rxBuf) == DeserializationError::Ok);
            _rxLen = 0;
            return ok;
        }

        if (_rxLen < UART_MAX_FRAME_BYTES) {
            _rxBuf[_rxLen++] = c;
        } else {
            // Frame too long — discard until next newline
            _rxLen    = 0;
            _rxDiscard = true;
        }
    }
    return false;
}
