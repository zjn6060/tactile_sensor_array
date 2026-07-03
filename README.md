# FSR_test

Force-sensitive resistor (FSR402) pressure sensor test rig: an Arduino reads
a linear conversion module wired to the sensor on `A0` and converts the
reading to an actual force in grams/newtons, a Python script visualizes the
readings in real time over serial.

## Structure

```
src/
  tactile_sensor/   Arduino firmware
    tactile_sensor.ino   reads the conversion module's output, prints ADC/V/force
    fsr402.h             voltage->force conversion, shared so it also
                          compiles for a future STM32 port
  visualization/    Python live plotting client (pyserial + matplotlib)
docs/               Additional documentation (sensor datasheets, calibration
                    curves, vendor Arduino example)
```

## Hardware

- Sensor: FSR402-equivalent, 18.3mm sensing area (RP-C18.3-LT), rated
  20g-6kg. Datasheet: `docs/传感器规格书/外形：梳形/薄膜压力传感器/FSR402 长尾 外径18.3mm 量程20g-6Kg RP-C18.3-LT.pdf`
- Board: Arduino UNO today (FQBN `arduino:avr:uno`); the firmware also builds
  for STM32 boards (Arduino core) via `#if defined(ARDUINO_ARCH_STM32)` in
  `tactile_sensor.ino`, which switches to a 12-bit ADC and 3.3V reference.
- Conversion module: a 1-channel "薄膜压力传感器线性转换模块" (same op-amp
  circuit as the 4-channel version documented in `docs/4路薄膜电压转换模块.pdf`
  — no separate 1-channel datasheet was found in `docs/`). The sensor plugs
  into the module's `S` terminals; the module's linear analog output goes to
  `A0`. Powered from the UNO's 5V rail. The module has an on-board trimmer:
  hold a known reference force on the sensor and turn the trimmer until the
  output reads 3.3V (no-load output is a fixed 0.1V) — that reference force
  is `FSR_CAL_FORCE_G` in `tactile_sensor.ino` (defaults to 6000g, the
  sensor's rated max). Update it if you recalibrate to a different force.

## Voltage -> force conversion

`fsr402.h` implements:

1. `fsrAdcToVoltage` — ADC count -> voltage, using the board's ADC max/Vcc.
2. `fsrVoltageToForceGrams` — linearly maps the module's 0.1V-3.3V output to
   0-`FSR_CAL_FORCE_G` grams (the module's op-amp stage already linearizes
   the sensor's resistance, so no resistance/power-law math is needed here).
3. `fsrGramsToNewtons` — grams -> newtons for display.

Accuracy depends entirely on how well the trimmer was calibrated against a
known reference force, plus the module's own linearity spec.

## Firmware: build & upload

Requires [arduino-cli](https://arduino.github.io/arduino-cli/).

```bash
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:uno src/tactile_sensor
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno src/tactile_sensor
```

Serial output format (9600 baud):
`ADC: <count>  V: <volts>  F: <grams>g (<newtons>N)  状态: <无压力|轻压|中等压力|重压>`.
Force thresholds (in `tactile_sensor.ino`): `<20g` no pressure, `<1000g`
light, `<3000g` medium, else heavy — chosen to divide the sensor's rated
20g-6000g range into four bands.

On Linux, reading `/dev/ttyACM0` requires being in the `dialout` group
(`sudo usermod -aG dialout $USER`, then re-login or `newgrp dialout`).

## Visualization

Requires `pyserial` and `matplotlib` (`pip install --user pyserial matplotlib`),
and a CJK-capable font (e.g. Noto Sans CJK) installed for the Chinese status
labels to render correctly.

```bash
python3 src/visualization/plot_fsr.py
```

Opens a live-updating window showing the last 30 seconds of force readings
(grams), with the same four pressure zones color-coded in the background.
