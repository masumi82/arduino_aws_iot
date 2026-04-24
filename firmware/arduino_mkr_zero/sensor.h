#pragma once
#include <stdint.h>

class Sensor {
public:
    Sensor();
    void update();
    float temperature() const { return _temp; }
    float humidity()    const { return _humid; }

private:
    float _temp;
    float _humid;
    float _clamp(float v, float lo, float hi);
};
