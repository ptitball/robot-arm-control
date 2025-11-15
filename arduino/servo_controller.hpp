#pragma once
#include <Arduino.h>

class ServoController {
public:
    void setup();
    void setPosition(int servoIndex, int angle, int speed);
};
