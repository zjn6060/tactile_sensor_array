import re
import time
import collections

import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "AR PL UMing TW MBE"]
plt.rcParams["axes.unicode_minus"] = False

PORT = "/dev/ttyACM0"
BAUD = 9600
WINDOW_SECONDS = 30  # 屏幕上保留最近多少秒的数据

LINE_RE = re.compile(r"ADC:\s*(\d+)")

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # 等待 Arduino 复位完成

times = collections.deque()
values = collections.deque()
start_time = time.time()

fig, ax = plt.subplots(figsize=(9, 5))
line, = ax.plot([], [], color="#2b6cb0", linewidth=1.5)

# 压力区间背景色,方便对照 sketch 里的阈值
ax.axhspan(0, 10, color="#e2e8f0", alpha=0.6, label="无压力 (<10)")
ax.axhspan(10, 200, color="#c6f6d5", alpha=0.6, label="轻压 (<200)")
ax.axhspan(200, 500, color="#feebc8", alpha=0.6, label="中等压力 (<500)")
ax.axhspan(500, 1023, color="#fed7d7", alpha=0.6, label="重压 (>=500)")

ax.set_xlabel("时间 (秒)")
ax.set_ylabel("ADC 读数 (0-1023)")
ax.set_title("FSR 压力传感器实时读数")
ax.set_ylim(0, 1023)
ax.legend(loc="upper right", fontsize=8)

status_text = ax.text(0.02, 0.95, "", transform=ax.transAxes, fontsize=11, va="top")


def classify(reading):
    if reading < 10:
        return "无压力"
    elif reading < 200:
        return "轻压"
    elif reading < 500:
        return "中等压力"
    return "重压"


def update(_frame):
    while ser.in_waiting:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue
        reading = int(match.group(1))
        t = time.time() - start_time
        times.append(t)
        values.append(reading)
        status_text.set_text(f"ADC: {reading}   状态: {classify(reading)}")

    while times and times[0] < times[-1] - WINDOW_SECONDS:
        times.popleft()
        values.popleft()

    line.set_data(times, values)
    if times:
        ax.set_xlim(max(0, times[-1] - WINDOW_SECONDS), max(WINDOW_SECONDS, times[-1]))
    return line, status_text


ani = animation.FuncAnimation(fig, update, interval=200, cache_frame_data=False)
plt.tight_layout()
plt.show()

ser.close()
