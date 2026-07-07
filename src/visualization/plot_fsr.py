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

# --- 运放反馈式压力传感器模块（AO-RES 增益电位器已手动调过）---
# 模块电路：U_o = (1 + R_AO-RES/Rx) * 0.1V，其中 F=0 时 Rx->无穷大，
# U_o 恒为 0.1V（ADC≈20），与增益无关；增益(旋钮)只决定斜率，因此只需一个
# 已知重量的标定点就能定死整条线。
# TODO: 旋钮位置改变后（重新调过增益），把下面两个常量换成新的实测点。
# 两路传感器目前共用同一套标定参数，如果两个模块增益旋钮不一致，需要分别标定。
VCC = 5.0
ADC_MAX = 1023
BASELINE_VOLTAGE = 0.1  # F=0 时的固定输出电压（电路特性，与增益无关）
CAL_KNOWN_FORCE_G = 251.0   # 标定用已知重量（手机）
CAL_KNOWN_ADC = 175         # 该重量下调好增益后实测的 ADC 值

FORCE_THRESHOLDS_G = (20, 200, 600)  # 无压力/轻压/中等压力/重压 分界（克），按抓握场景设定

CHANNELS = ({"label": "通道1 (A0)", "adc_color": "#2b6cb0", "force_color": "#c53030"},
            {"label": "通道2 (A1)", "adc_color": "#2f855a", "force_color": "#b7791f"})

LINE_RE = re.compile(r"ADC1:\s*(\d+)\s+ADC2:\s*(\d+)")


def adc_to_voltage(adc):
    return adc / ADC_MAX * VCC


# 由标定点反推斜率：F = (U_o - BASELINE_VOLTAGE) * _FORCE_PER_VOLT
_FORCE_PER_VOLT = CAL_KNOWN_FORCE_G / (adc_to_voltage(CAL_KNOWN_ADC) - BASELINE_VOLTAGE)


def adc_to_force_g(adc):
    voltage = adc_to_voltage(adc)
    return max(voltage - BASELINE_VOLTAGE, 0.0) * _FORCE_PER_VOLT


def classify_force(force_g):
    low, mid, high = FORCE_THRESHOLDS_G
    if force_g < low:
        return "无压力"
    elif force_g < mid:
        return "轻压"
    elif force_g < high:
        return "中等压力"
    return "重压"


ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # 等待 Arduino 复位完成

times = collections.deque()
channel_data = [
    {"adc": collections.deque(), "force": collections.deque()} for _ in CHANNELS
]
start_time = time.time()

fig, axes = plt.subplots(1, len(CHANNELS), figsize=(14, 6))

adc_lines = []
force_lines = []
status_texts = []
force_axes = []

low_g, mid_g, high_g = FORCE_THRESHOLDS_G

for ax, ch in zip(axes, CHANNELS):
    adc_line, = ax.plot([], [], color=ch["adc_color"], linewidth=1.5, label="ADC 原始读数")
    ax.set_xlabel("时间 (秒)")
    ax.set_ylabel("ADC 读数 (0-1023)", color=ch["adc_color"])
    ax.set_ylim(0, 1023)
    ax.set_title(ch["label"])
    ax.tick_params(axis="y", labelcolor=ch["adc_color"])

    force_ax = ax.twinx()
    force_ax.axhspan(0, low_g, color="#e2e8f0", alpha=0.4)
    force_ax.axhspan(low_g, mid_g, color="#c6f6d5", alpha=0.4)
    force_ax.axhspan(mid_g, high_g, color="#feebc8", alpha=0.4)
    force_ax.axhspan(high_g, 1100, color="#fed7d7", alpha=0.4)
    force_line, = force_ax.plot([], [], color=ch["force_color"], linewidth=1.5, label="估算压力 (g)")
    force_ax.set_ylabel("估算压力 (g)", color=ch["force_color"])
    force_ax.set_ylim(0, 1100)
    force_ax.tick_params(axis="y", labelcolor=ch["force_color"])

    status_text = ax.text(0.02, 0.92, "", transform=ax.transAxes, fontsize=10, va="top")

    adc_lines.append(adc_line)
    force_lines.append(force_line)
    force_axes.append(force_ax)
    status_texts.append(status_text)


def update(_frame):
    while ser.in_waiting:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue
        adcs = (int(match.group(1)), int(match.group(2)))

        t = time.time() - start_time
        times.append(t)
        for data, adc in zip(channel_data, adcs):
            data["adc"].append(adc)
            data["force"].append(adc_to_force_g(adc))

        for i, (ch, data, adc) in enumerate(zip(CHANNELS, channel_data, adcs)):
            force_g = data["force"][-1]
            status_texts[i].set_text(
                f"ADC: {adc}   估算压力: {force_g:.0f}g   状态: {classify_force(force_g)}"
            )

    while times and times[0] < times[-1] - WINDOW_SECONDS:
        times.popleft()
        for data in channel_data:
            data["adc"].popleft()
            data["force"].popleft()

    for i, data in enumerate(channel_data):
        adc_lines[i].set_data(times, data["adc"])
        force_lines[i].set_data(times, data["force"])
        if data["force"]:
            # 跟着当前窗口内的读数动态放大坐标轴，方便看清细节，同时不超过标定量程上限。
            y_max = min(max(data["force"]) * 1.3, 1100)
            force_axes[i].set_ylim(0, max(y_max, 100))

    if times:
        xlim = (max(0, times[-1] - WINDOW_SECONDS), max(WINDOW_SECONDS, times[-1]))
        for ax in axes:
            ax.set_xlim(*xlim)

    return (*adc_lines, *force_lines, *status_texts)


ani = animation.FuncAnimation(fig, update, interval=200, cache_frame_data=False)
plt.tight_layout()
plt.show()

ser.close()
