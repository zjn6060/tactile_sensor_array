# FSR_test

Force-sensitive resistor (FSR) pressure sensor test rig: an Arduino reads the
sensor on `A0` and classifies the pressure level, a Python script visualizes
the readings in real time over serial.

## Structure

```
src/
  tactile_sensor/   Arduino firmware (reads FSR on A0, prints "ADC: <value>")
  visualization/    Python live plotting client (pyserial + matplotlib)
docs/               Additional documentation
```

## Hardware

- Arduino UNO (or compatible, FQBN `arduino:avr:uno`)
- FSR connected to analog pin `A0`

## Firmware: build & upload

Requires [arduino-cli](https://arduino.github.io/arduino-cli/).

```bash
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:uno src/tactile_sensor
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno src/tactile_sensor
```

Serial output format: `ADC: <0-1023>  状态: <无压力|轻压|中等压力|重压>` at 9600 baud.
Pressure thresholds (in `tactile_sensor.ino`): `<10` no pressure, `<200` light,
`<500` medium, else heavy.

On Linux, reading `/dev/ttyACM0` requires being in the `dialout` group
(`sudo usermod -aG dialout $USER`, then re-login or `newgrp dialout`).

## Visualization

Requires `pyserial` and `matplotlib` (`pip install --user pyserial matplotlib`),
and a CJK-capable font (e.g. Noto Sans CJK) installed for the Chinese status
labels to render correctly.

```bash
python3 src/visualization/plot_fsr.py
```

Opens a live-updating window showing the last 30 seconds of ADC readings,
with the same four pressure zones color-coded in the background.
