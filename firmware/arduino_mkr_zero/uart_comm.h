#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

// Serialize and send a telemetry frame over Serial.
void uart_send_telemetry(const char* deviceId, float tempC, float humidPct,
                         bool ledState, uint32_t intervalMs, uint32_t seqNo);

// Try to read one command frame from Serial.
// Returns true and populates outDoc if a complete JSON line was received.
// Returns false if no complete line is available yet.
bool uart_try_read_command(JsonDocument& outDoc);
