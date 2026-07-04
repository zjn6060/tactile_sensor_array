import re
import time
import collections

import numpy as np
import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "AR PL UMing TW MBE"]
plt.rcParams["axes.unicode_minus"] = False

PORT = "/dev/ttyACM0"
BAUD = 9600
WINDOW_SECONDS = 30  # 屏幕上保留最近多少秒的数据

# --- 分压电路参数 ---
# FSR 一端接 VCC，另一端接 Arduino 模拟口，模拟口再经 R_FIXED_OHMS 接地（下拉）。
# Vout/Vcc = R_FIXED/(R_FSR+R_FIXED)  =>  R_FSR = R_FIXED*(Vcc/Vout - 1)
# TODO: 10kΩ 是出厂默认假设值，实测校准后请替换为电路里实际的固定电阻阻值。
R_FIXED_OHMS = 10_000.0
ADC_MAX = 1023

# --- FSR402(RP-C18.3) 压力-电阻标定表，0~6kg 量程（来自规格书《RP-C18.3 压力电阻曲线.pdf》，
# 15mm 硅胶半球头压头测得，厂商拟合 R=153.18*F^-0.699，R²=0.9972）。
# 100kΩ 处为人为补充的"无接触"锚点（FSR 空载电阻通常 >1MΩ，这里给个远大于首个数据点的值即可）。
# TODO: 传感器一致性误差较大，厂商建议逐只校准；换成实测数据后替换本表即可。
_CAL_WEIGHT_G = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100,
                  1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 3000,
                  4000, 5000, 6000]
_CAL_RESISTANCE_KOHM = [100, 6.853, 3.733, 2.82, 2.313, 2.02, 1.743, 1.57,
                         1.42, 1.328, 1.195, 1.104, 1.044, 0.988, 0.948,
                         0.913, 0.871, 0.837, 0.811, 0.774, 0.744, 0.576,
                         0.485, 0.4213, 0.3797]
# np.interp 要求 xp 单调递增，这里按电阻从小到大重新排序（对应重量从大到小）。
_CAL_R_ASC = list(reversed(_CAL_RESISTANCE_KOHM))
_CAL_G_DESC = list(reversed(_CAL_WEIGHT_G))

FORCE_THRESHOLDS_G = (50, 1000, 3000)  # 无压力/轻压/中等压力/重压 分界（克）

LINE_RE = re.compile(r"ADC:\s*(\d+)")


def adc_to_resistance_kohm(adc):
    if adc <= 0:
        return float("inf")
    ratio = adc / ADC_MAX
    r_fsr_ohms = R_FIXED_OHMS * (1 / ratio - 1)
    return max(r_fsr_ohms, 0.0) / 1000.0


def resistance_to_force_g(r_kohm):
    return float(np.interp(r_kohm, _CAL_R_ASC, _CAL_G_DESC))


def adc_to_force_g(adc):
    return resistance_to_force_g(adc_to_resistance_kohm(adc))


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
adc_values = collections.deque()
force_values = collections.deque()
start_time = time.time()

fig, (ax_adc, ax_force) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

adc_line, = ax_adc.plot([], [], color="#2b6cb0", linewidth=1.5)
ax_adc.set_ylabel("ADC 读数 (0-1023)")
ax_adc.set_title("FSR 原始 ADC 读数")
ax_adc.set_ylim(0, 1023)

force_line, = ax_force.plot([], [], color="#c53030", linewidth=1.5)
low_g, mid_g, high_g = FORCE_THRESHOLDS_G
ax_force.axhspan(0, low_g, color="#e2e8f0", alpha=0.6, label=f"无压力 (<{low_g}g)")
ax_force.axhspan(low_g, mid_g, color="#c6f6d5", alpha=0.6, label=f"轻压 (<{mid_g}g)")
ax_force.axhspan(mid_g, high_g, color="#feebc8", alpha=0.6, label=f"中等压力 (<{high_g}g)")
ax_force.axhspan(high_g, 6000, color="#fed7d7", alpha=0.6, label=f"重压 (>={high_g}g)")
ax_force.set_xlabel("时间 (秒)")
ax_force.set_ylabel("估算压力 (g)")
ax_force.set_title("换算压力（分段线性标定，未校准，仅供参考）")
ax_force.set_ylim(0, 6000)
ax_force.legend(loc="upper right", fontsize=8)

status_text = ax_adc.text(0.02, 0.92, "", transform=ax_adc.transAxes, fontsize=11, va="top")


def update(_frame):
    while ser.in_waiting:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue
        adc = int(match.group(1))
        force_g = adc_to_force_g(adc)

        t = time.time() - start_time
        times.append(t)
        adc_values.append(adc)
        force_values.append(force_g)
        status_text.set_text(
            f"ADC: {adc}   估算压力: {force_g:.0f}g   状态: {classify_force(force_g)}"
        )

    while times and times[0] < times[-1] - WINDOW_SECONDS:
        times.popleft()
        adc_values.popleft()
        force_values.popleft()

    adc_line.set_data(times, adc_values)
    force_line.set_data(times, force_values)
    if times:
        xlim = (max(0, times[-1] - WINDOW_SECONDS), max(WINDOW_SECONDS, times[-1]))
        ax_adc.set_xlim(*xlim)
        ax_force.set_xlim(*xlim)
    return adc_line, force_line, status_text


ani = animation.FuncAnimation(fig, update, interval=200, cache_frame_data=False)
plt.tight_layout()
plt.show()

ser.close()
