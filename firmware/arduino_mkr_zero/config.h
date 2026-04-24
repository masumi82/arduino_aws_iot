#pragma once

// Device identity
static const char DEVICE_ID[] = "arduino-mkr-001";
static const char SCHEMA_VERSION[] = "1.0";

// UART
static const uint32_t UART_BAUDRATE = 115200;
static const uint16_t UART_MAX_FRAME_BYTES = 512;

// Pseudo-sensor: temperature (°C)
static const float TEMP_INIT    = 25.0f;
static const float TEMP_MIN     = 15.0f;
static const float TEMP_MAX     = 35.0f;
static const float TEMP_DELTA   = 0.5f;

// Pseudo-sensor: humidity (%)
static const float HUMID_INIT   = 50.0f;
static const float HUMID_MIN    = 20.0f;
static const float HUMID_MAX    = 80.0f;
static const float HUMID_DELTA  = 1.0f;

// Telemetry interval
static const uint32_t INTERVAL_DEFAULT_MS = 10000;
static const uint32_t INTERVAL_MIN_MS     =  5000;
static const uint32_t INTERVAL_MAX_MS     = 30000;

// EEPROM layout
static const int EEPROM_ADDR_INTERVAL = 0x00;  // uint32_t (4 bytes)
static const int EEPROM_ADDR_MAGIC    = 0x04;  // uint8_t  (1 byte)
static const uint8_t EEPROM_MAGIC_BYTE = 0xAB;

// LED pin
static const int LED_PIN = LED_BUILTIN;
