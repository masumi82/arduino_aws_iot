#include "sensor.h"
#include "config.h"
#include <Arduino.h>

Sensor::Sensor() : _temp(TEMP_INIT), _humid(HUMID_INIT) {}

void Sensor::update() {
    // random(-100, 101) gives integers in [-100, 100]; scale by 0.01 for floats
    float dt = random(-100, 101) * TEMP_DELTA  / 100.0f;
    float dh = random(-100, 101) * HUMID_DELTA / 100.0f;
    _temp  = _clamp(_temp  + dt, TEMP_MIN,  TEMP_MAX);
    _humid = _clamp(_humid + dh, HUMID_MIN, HUMID_MAX);
}

float Sensor::_clamp(float v, float lo, float hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}
