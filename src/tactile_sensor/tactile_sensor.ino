#include "fsr402.h"

const int FSR_PIN = A0; // module's linear analog output pin

// Calibration reference: hold this much force on the sensor while trimming
// the conversion module's pot until its output reads 3.3V. Matches FSR402's
// rated max load; update if the module gets recalibrated to a different force.
const float FSR_CAL_FORCE_G = 6000.0f;

#if defined(ARDUINO_ARCH_STM32)
const int ADC_MAX = 4095; // 12-bit ADC
const float VCC = 3.3f;
#else
const int ADC_MAX = 1023; // Arduino UNO: 10-bit ADC, 5V reference (also powers the module)
const float VCC = 5.0f;
#endif

void setup() {
  Serial.begin(9600);
#if defined(ARDUINO_ARCH_STM32)
  analogReadResolution(12);
#endif
}

void loop() {
  int adc = analogRead(FSR_PIN);
  float voltage = fsrAdcToVoltage(adc, ADC_MAX, VCC);
  float forceGrams = fsrVoltageToForceGrams(voltage, FSR_CAL_FORCE_G);
  float forceNewtons = fsrGramsToNewtons(forceGrams);

  Serial.print("ADC: ");
  Serial.print(adc);
  Serial.print("  V: ");
  Serial.print(voltage, 2);
  Serial.print("  F: ");
  Serial.print(forceGrams, 1);
  Serial.print("g (");
  Serial.print(forceNewtons, 2);
  Serial.print("N)  状态: ");

  if (forceGrams < 20) {
    Serial.println("无压力");
  } else if (forceGrams < 1000) {
    Serial.println("轻压");
  } else if (forceGrams < 3000) {
    Serial.println("中等压力");
  } else {
    Serial.println("重压");
  }

  delay(200);
}
