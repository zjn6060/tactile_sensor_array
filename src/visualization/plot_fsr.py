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
FORCE_MAX_G = 6000  # 传感器额定量程上限 (RP-C18.3/FSR402)

LINE_RE = re.compile(r"F:\s*([\d.]+)g\s*\(([\d.]+)N\)\s*状态:\s*(\S+)")

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # 等待 Arduino 复位完成

times = collections.deque()
values = collections.deque()
start_time = time.time()

fig, ax = plt.subplots(figsize=(9, 5))
line, = ax.plot([], [], color="#2b6cb0", linewidth=1.5)

# 压力区间背景色,和 sketch 里的力值阈值对应
ax.axhspan(0, 20, color="#e2e8f0", alpha=0.6, label="无压力 (<20g)")
ax.axhspan(20, 1000, color="#c6f6d5", alpha=0.6, label="轻压 (<1000g)")
ax.axhspan(1000, 3000, color="#feebc8", alpha=0.6, label="中等压力 (<3000g)")
ax.axhspan(3000, FORCE_MAX_G, color="#fed7d7", alpha=0.6, label="重压 (>=3000g)")

ax.set_xlabel("时间 (秒)")
ax.set_ylabel("受力 (g)")
ax.set_title("FSR402 压力传感器实时读数")
ax.set_ylim(0, FORCE_MAX_G)
ax.legend(loc="upper right", fontsize=8)

status_text = ax.text(0.02, 0.95, "", transform=ax.transAxes, fontsize=11, va="top")


def update(_frame):
    while ser.in_waiting:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue
        grams = float(match.group(1))
        newtons = float(match.group(2))
        status = match.group(3)
        print(raw)
        t = time.time() - start_time
        times.append(t)
        values.append(grams)
        status_text.set_text(f"F: {grams:.1f}g ({newtons:.2f}N)   状态: {status}")

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
