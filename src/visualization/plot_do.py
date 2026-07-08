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
WINDOW_SECONDS = 15  # 屏幕上保留最近多少秒的数据

LINE_RE = re.compile(r"DO1:\s*(\d)\s+DO2:\s*(\d)")

CHANNELS = ({"label": "通道0 (DO1)", "color": "#2b6cb0"},
            {"label": "通道1 (DO2)", "color": "#2f855a"})

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # 等待 Arduino 复位完成

times = collections.deque()
channel_states = [collections.deque() for _ in CHANNELS]
start_time = time.time()

fig, axes = plt.subplots(len(CHANNELS), 1, figsize=(10, 5), sharex=True)

lines = []
for ax, ch in zip(axes, CHANNELS):
    line, = ax.step([], [], where="post", color=ch["color"], linewidth=2)
    ax.set_ylim(-0.2, 1.2)
    ax.set_yticks([0, 1])
    ax.set_ylabel(ch["label"])
    ax.grid(alpha=0.3)
    lines.append(line)

axes[-1].set_xlabel("时间 (秒)")


def update(_frame):
    while ser.in_waiting:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue

        t = time.time() - start_time
        times.append(t)
        for i, group in enumerate(match.groups()):
            channel_states[i].append(int(group))

    while times and times[0] < times[-1] - WINDOW_SECONDS:
        times.popleft()
        for states in channel_states:
            states.popleft()

    for i, line in enumerate(lines):
        line.set_data(times, channel_states[i])

    if times:
        xlim = (max(0, times[-1] - WINDOW_SECONDS), max(WINDOW_SECONDS, times[-1]))
        for ax in axes:
            ax.set_xlim(*xlim)

    return lines


ani = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
plt.tight_layout()
plt.show()

ser.close()
