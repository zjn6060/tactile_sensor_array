import os
import re
import time
import threading
import statistics
import collections

import yaml
import serial

PORT = "/dev/ttyACM0"
BAUD = 9600
SAMPLE_WINDOW = 10  # 实时显示零压基线电压时对最近多少个样本取平均，减少抖动
OUTPUT_PATH = "calibration/config.yaml"

VCC = 5.0
ADC_MAX = 1023

CHANNELS = ("通道1 (A0/DO1)", "通道2 (A1/DO2)")  # 向导交互提示用
CHANNEL_IDS = ("A0", "A1")  # 写入 calibration/config.yaml 的通道标识

LINE_RE = re.compile(r"ADC1:\s*(\d+)\s+ADC2:\s*(\d+)\s+DO1:\s*(\d)\s+DO2:\s*(\d)")

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # 等待 Arduino 复位完成

latest_adc = [None, None]
latest_do = [None, None]
recent_adc = [collections.deque(maxlen=SAMPLE_WINDOW) for _ in CHANNELS]
lock = threading.Lock()
keep_reading = True


def read_serial():
    while keep_reading:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue
        adcs = (int(match.group(1)), int(match.group(2)))
        dos = (int(match.group(3)), int(match.group(4)))
        with lock:
            for i, (adc, do) in enumerate(zip(adcs, dos)):
                recent_adc[i].append(adc)
                latest_adc[i] = adc
                latest_do[i] = do


threading.Thread(target=read_serial, daemon=True).start()


def adc_to_voltage(adc):
    return adc / ADC_MAX * VCC


def snapshot_mean_adc(ch_index):
    with lock:
        values = list(recent_adc[ch_index])
    return statistics.mean(values) if values else None


def live_until_enter(ch_index):
    """持续打印实时 ADC/电压/DO 状态，按回车结束，返回 (平均 ADC, 结束时的 DO 状态)。"""
    stop = threading.Event()

    def wait_for_enter():
        input()
        stop.set()

    threading.Thread(target=wait_for_enter, daemon=True).start()

    while not stop.is_set():
        with lock:
            adc = latest_adc[ch_index]
            do = latest_do[ch_index]
        if adc is None:
            print("\r  等待串口数据...          ", end="", flush=True)
        else:
            do_text = "触发 HIGH" if do else "未触发 LOW"
            print(f"\r  实时 ADC: {adc:4d}   电压: {adc_to_voltage(adc):.3f}V   DO: {do_text}   ", end="", flush=True)
        time.sleep(0.1)
    print()

    with lock:
        final_do = latest_do[ch_index]
    return snapshot_mean_adc(ch_index), final_do


digital_channels_out = []

print("=== 数字输出 (DO) 阈值校准向导 ===")
print("提示：DO_RES 是模块上独立于 AO 增益旋钮的第二颗电位器，专门调节 DO 的触发阈值。")

try:
    input("\n步骤一：确认传感器已接入模块 S 端子、模块已上电，DO 引脚已接到 Arduino，就绪后按回车继续...")

    for i, ch_name in enumerate(CHANNELS):
        print(f"\n--- {ch_name} ---")

        input("步骤二：确保该通道传感器上没有任何压力，稳定后按回车开始读取零压状态...")
        print("  正在读取零压状态，按回车确认当前读数稳定：")
        baseline_adc, baseline_do = live_until_enter(i)
        if baseline_adc is None:
            print("  未收到串口数据，跳过该通道，请检查连接。")
            continue
        print(f"  零压基线 ADC ≈ {baseline_adc:.1f}（电压 ≈ {adc_to_voltage(baseline_adc):.3f}V）")
        if baseline_do:
            print("  警告：没有施加压力时 DO 已经是 HIGH，说明阈值调得过低（太灵敏）。"
                  "建议先调松 DO_RES，再继续下一步。")
        else:
            print("  DO 处于 LOW，符合预期。")

        threshold_input = input(
            "\n步骤三：在传感器上稳定施加你想要作为触发阈值的力(g)，输入数值后回车（直接回车跳过该通道）："
        ).strip()
        if not threshold_input:
            print("  已跳过该通道的阈值标定。")
            continue
        try:
            threshold_force_g = float(threshold_input)
        except ValueError:
            print("  数值输入无效，已跳过该通道。")
            continue

        print("  保持该力度不变，缓慢调节对应的 DO_RES 电位器，直到 DO 刚好从 LOW 变为 HIGH；调好后按回车确认：")
        _, trigger_do = live_until_enter(i)
        if trigger_do is None:
            print("  未收到串口数据，跳过该通道，请检查连接。")
            continue
        if trigger_do:
            print(f"  已确认：{threshold_force_g:g}g 时 DO = HIGH，阈值标定完成。")
        else:
            print(f"  注意：确认时 DO 仍为 LOW，说明还没调到触发点，此次记录可能不准确。")

        digital_channels_out.append({
            "label": CHANNEL_IDS[i],
            "threshold_force_g": threshold_force_g,
            "do_triggered_at_threshold": bool(trigger_do),
            "do_low_at_zero_force": not baseline_do,
        })

    print("\n步骤四：所有通道调节完成。" if len(digital_channels_out) == len(CHANNELS)
          else "\n部分通道未完成标定（见上方提示）。")

except KeyboardInterrupt:
    print("\n已中断。")

finally:
    keep_reading = False
    ser.close()
    if digital_channels_out:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        config = {}
        if os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        config["digital_channels"] = digital_channels_out
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
        print(f"\n已保存 {len(digital_channels_out)} 个通道的 DO 阈值记录到 {OUTPUT_PATH}")
    else:
        print("\n没有记录任何标定点。")
