import re
import time
import collections

import yaml
import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "AR PL UMing TW MBE"]
plt.rcParams["axes.unicode_minus"] = False

PORT = "/dev/ttyACM0"
BAUD = 9600
WINDOW_SECONDS = 30  # 屏幕上保留最近多少秒的数据
FORCE_MAX_G = 6000  # 传感器额定量程上限 (RP-C18.3/FSR402)

# --- 运放反馈式压力传感器模块（AO-RES 增益电位器已手动调过）---
# 模块电路：U_o = (1 + R_AO-RES/Rx) * 0.1V，其中 F=0 时 Rx->无穷大，
# U_o 恒为固定基线电压，与增益无关；增益(旋钮)只决定斜率，因此只需一个
# 已知重量的标定点就能定死整条线。
# 标定点来自 calibrate_fsr.py 校准向导生成的 calibration/config.yaml，
# 两路模块增益旋钮各自独立调节，因此每个通道单独标定（含各自的零压基线）。
VCC = 5.0
ADC_MAX = 1023
CALIBRATION_PATH = "calibration/config.yaml"

FORCE_THRESHOLDS_G = (20, 200, 600)  # 无压力/轻压/中等压力/重压 分界（克），按抓握场景设定

# hw_index = 该通道在串口一行数据（ADC1/ADC2）里的位置，与标定/显示是否启用无关
CHANNELS = ({"id": "A0", "hw_index": 0, "label": "通道1 (A0)", "adc_color": "#2b6cb0", "force_color": "#c53030"},
            {"id": "A1", "hw_index": 1, "label": "通道2 (A1)", "adc_color": "#2f855a", "force_color": "#b7791f"})

with open(CALIBRATION_PATH, encoding="utf-8") as f:
    _calibration_by_id = {ch["label"]: ch for ch in yaml.safe_load(f)["channels"]}

# 只画已标定的通道；未标定的通道跳过（仍会被解析，只是不显示/不计算压力）。
PLOT_CHANNELS = [ch for ch in CHANNELS if ch["id"] in _calibration_by_id]
_skipped = [ch["id"] for ch in CHANNELS if ch["id"] not in _calibration_by_id]

if not PLOT_CHANNELS:
    raise SystemExit(
        f"{CALIBRATION_PATH} 里没有任何已标定的通道；请先用 calibrate_fsr.py 完成标定再运行。"
    )
if _skipped:
    print(f"提示：{', '.join(_skipped)} 尚未标定，本次只显示：{', '.join(ch['id'] for ch in PLOT_CHANNELS)}")

CAL_KNOWN_FORCE_G = tuple(_calibration_by_id[ch["id"]]["ref_weight_g"] for ch in PLOT_CHANNELS)
CAL_KNOWN_ADC = tuple(_calibration_by_id[ch["id"]]["adc_full_scale"] for ch in PLOT_CHANNELS)
CAL_BASELINE_ADC = tuple(_calibration_by_id[ch["id"]]["adc_baseline"] for ch in PLOT_CHANNELS)

LINE_RE = re.compile(r"ADC1:\s*(\d+)\s+ADC2:\s*(\d+)")


def adc_to_voltage(adc):
    return adc / ADC_MAX * VCC


# 由标定点反推斜率：F = (U_o - 该通道零压基线电压) * _FORCE_PER_VOLT，每个通道各一条
_BASELINE_VOLTAGE = [adc_to_voltage(adc) for adc in CAL_BASELINE_ADC]
_FORCE_PER_VOLT = [
    known_force_g / (adc_to_voltage(known_adc) - baseline_v)
    for known_force_g, known_adc, baseline_v in zip(CAL_KNOWN_FORCE_G, CAL_KNOWN_ADC, _BASELINE_VOLTAGE)
]


def adc_to_force_g(adc, ch_index):
    voltage = adc_to_voltage(adc)
    return max(voltage - _BASELINE_VOLTAGE[ch_index], 0.0) * _FORCE_PER_VOLT[ch_index]


FORCE_SMOOTHING_ALPHA = 0.2  # 估算压力的低通滤波系数：越小越平滑（响应更慢），越大越接近原始读数

_smoothed_force_g = [None] * len(PLOT_CHANNELS)  # 每个通道的滤波器状态（上一次的平滑值）


def low_pass_force_g(raw_force_g, ch_index):
    prev = _smoothed_force_g[ch_index]
    smoothed = raw_force_g if prev is None else (
        FORCE_SMOOTHING_ALPHA * raw_force_g + (1 - FORCE_SMOOTHING_ALPHA) * prev
    )
    _smoothed_force_g[ch_index] = smoothed
    return smoothed


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
    {"adc": collections.deque(), "force": collections.deque()} for _ in PLOT_CHANNELS
]
start_time = time.time()

fig, axes = plt.subplots(1, len(PLOT_CHANNELS), figsize=(7 * len(PLOT_CHANNELS), 6))
if len(PLOT_CHANNELS) == 1:
    axes = [axes]

adc_lines = []
force_lines = []
status_texts = []
force_axes = []

low_g, mid_g, high_g = FORCE_THRESHOLDS_G

for ax, ch in zip(axes, PLOT_CHANNELS):
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

    status_text = ax.text(
        0.02, 0.95, "", transform=ax.transAxes, fontsize=12, fontweight="bold",
        va="top", bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.85, edgecolor=ch["force_color"]),
    )

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
        for i, (ch, data) in enumerate(zip(PLOT_CHANNELS, channel_data)):
            adc = adcs[ch["hw_index"]]
            data["adc"].append(adc)
            raw_force_g = adc_to_force_g(adc, i)
            data["force"].append(low_pass_force_g(raw_force_g, i))

            voltage = adc_to_voltage(adc)
            force_g = data["force"][-1]
            status_texts[i].set_text(
                f"ADC: {adc}   电压: {voltage:.3f}V\n估算压力: {force_g:.0f}g   状态: {classify_force(force_g)}"
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
