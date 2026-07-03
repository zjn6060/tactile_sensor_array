#ifndef FSR402_H
#define FSR402_H

// FSR402 is wired through a dedicated linear conversion module (四路/一路薄膜
// 压力传感器模块, see docs/4路薄膜电压转换模块.pdf — only the 4-channel manual
// is in docs/, but the 1-channel board is the same op-amp circuit per channel).
// The module's on-board trimmer linearizes the sensor's resistance into a
// voltage: turn it until Vout = 3.3V while holding a known reference force on
// the sensor; Vout = 0.1V is the module's fixed no-load output.
static const float FSR_MODULE_V_ZERO = 0.1f; // module output at 0 force
static const float FSR_MODULE_V_FULL = 3.3f; // module output at the calibrated force

inline float fsrAdcToVoltage(int adc, int adcMax, float vcc) {
  return (adc / (float)adcMax) * vcc;
}

// calFullScaleGrams: the force that was held on the sensor while trimming the
// module's pot to 3.3V. Update this if the module gets recalibrated.
inline float fsrVoltageToForceGrams(float voltage, float calFullScaleGrams) {
  float span = FSR_MODULE_V_FULL - FSR_MODULE_V_ZERO;
  float grams = (voltage - FSR_MODULE_V_ZERO) / span * calFullScaleGrams;
  if (grams < 0.0f) {
    grams = 0.0f;
  }
  if (grams > calFullScaleGrams) {
    grams = calFullScaleGrams;
  }
  return grams;
}

inline float fsrGramsToNewtons(float grams) {
  return grams * 9.80665f / 1000.0f;
}

#endif
