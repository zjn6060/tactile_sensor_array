import re
import csv
import time
import threading
import statistics
import collections

import serial

PORT = "/dev/ttyACM0"
BAUD = 9600
SAMPLE_WINDOW = 10  # 记录时对最近多少个样本取平均，减少抖动
OUTPUT_CSV = "calibration_samples.csv"

LINE_RE = re.compile(r"ADC:\s*(\d+)")

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # 等待 Arduino 复位完成

recent = collections.deque(maxlen=SAMPLE_WINDOW)
latest_adc = None
lock = threading.Lock()


def read_serial():
    global latest_adc
    while True:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue
        adc = int(match.group(1))
        with lock:
            recent.append(adc)
            latest_adc = adc


threading.Thread(target=read_serial, daemon=True).start()

print("放好已知重量、读数稳定后按回车记录一个标定点；直接回车不输入重量可跳过；Ctrl+C 结束并保存。")

rows = []
try:
    while True:
        input("\n按回车采样当前读数...")
        with lock:
            snapshot = list(recent)
        if not snapshot:
            print("还没收到串口数据，请检查连接。")
            continue
        avg_adc = statistics.mean(snapshot)
        print(f"最近 {len(snapshot)} 次采样：当前 ADC={latest_adc}，均值={avg_adc:.1f}")
        weight_input = input("这个读数对应的实际重量(g)，直接回车跳过本次记录：").strip()
        if not weight_input:
            continue
        rows.append((float(weight_input), avg_adc, latest_adc))
        print(f"已记录：{weight_input}g -> ADC均值 {avg_adc:.1f}")
except KeyboardInterrupt:
    pass
finally:
    ser.close()
    if rows:
        with open(OUTPUT_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["weight_g", "adc_mean", "adc_last_sample"])
            writer.writerows(rows)
        print(f"\n已保存 {len(rows)} 个标定点到 {OUTPUT_CSV}")
    else:
        print("\n没有记录任何标定点。")
