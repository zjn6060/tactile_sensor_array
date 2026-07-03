const int FSR_PIN = A0;

void setup() {
  Serial.begin(9600);
}

void loop() {
  int reading = analogRead(FSR_PIN);

  Serial.print("ADC: ");
  Serial.print(reading);
  Serial.print("  状态: ");

  if (reading < 10) {
    Serial.println("无压力");
  } else if (reading < 200) {
    Serial.println("轻压");
  } else if (reading < 500) {
    Serial.println("中等压力");
  } else {
    Serial.println("重压");
  }

  delay(200);
}
