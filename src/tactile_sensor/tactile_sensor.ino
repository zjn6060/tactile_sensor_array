const int FSR_PIN_1 = A0;
const int FSR_PIN_2 = A1;

// 模块的比较器数字输出（DO），阈值由模块上独立的那颗电位器调节，与 AO 的增益旋钮无关。
// 按实际接线调整这两个引脚。
const int DO_PIN_1 = 2;
const int DO_PIN_2 = 3;

void setup() {
  Serial.begin(9600);
#if defined(ARDUINO_ARCH_STM32)
  analogReadResolution(12);
#endif
  pinMode(DO_PIN_1, INPUT);
  pinMode(DO_PIN_2, INPUT);
}

void loop() {
  int reading1 = analogRead(FSR_PIN_1);
  int reading2 = analogRead(FSR_PIN_2);
  int do1 = digitalRead(DO_PIN_1);
  int do2 = digitalRead(DO_PIN_2);

  Serial.print("ADC1: ");
  Serial.print(reading1);
  Serial.print("  ADC2: ");
  Serial.print(reading2);
  Serial.print("  DO1: ");
  Serial.print(do1);
  Serial.print("  DO2: ");
  Serial.println(do2);

  delay(200);
}
