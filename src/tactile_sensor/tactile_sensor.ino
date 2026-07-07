const int FSR_PIN_1 = A0;
const int FSR_PIN_2 = A1;

void setup() {
  Serial.begin(9600);
}

void loop() {
  int reading1 = analogRead(FSR_PIN_1);
  int reading2 = analogRead(FSR_PIN_2);

  Serial.print("ADC1: ");
  Serial.print(reading1);
  Serial.print("  ADC2: ");
  Serial.println(reading2);

  delay(200);
}
