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
SAMPLE_WINDOW = 10  # 实时显示/记录时对最近多少个样本取平均，减少抖动
OUTPUT_PATH = "calibration/config.yaml"

VCC = 5.0
ADC_MAX = 1023

CHANNELS = ("通道1 (A0)", "通道2 (A1)")  # 向导交互提示用
CHANNEL_IDS = ("A0", "A1")  # 写入 calibration/config.yaml 的通道标识

LINE_RE = re.compile(r"ADC1:\s*(\d+)\s+ADC2:\s*(\d+)")

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # 等待 Arduino 复位完成

latest = [None, None]
recent = [collections.deque(maxlen=SAMPLE_WINDOW) for _ in CHANNELS]
lock = threading.Lock()
keep_reading = True


def read_serial():
    while keep_reading:
        raw = ser.readline().decode(errors="ignore").strip()
        match = LINE_RE.search(raw)
        if not match:
            continue
        adcs = (int(match.group(1)), int(match.group(2)))
        with lock:
            for i, adc in enumerate(adcs):
                recent[i].append(adc)
                latest[i] = adc


threading.Thread(target=read_serial, daemon=True).start()


def adc_to_voltage(adc):
    return adc / ADC_MAX * VCC


def snapshot_mean(ch_index):
    with lock:
        values = list(recent[ch_index])
    return statistics.mean(values) if values else None


def live_until_enter(ch_index):
    """持续打印实时 ADC/电压，按回车结束并返回这段时间的均值。"""
    stop = threading.Event()

    def wait_for_enter():
        input()
        stop.set()

    threading.Thread(target=wait_for_enter, daemon=True).start()

    while not stop.is_set():
        with lock:
            adc = latest[ch_index]
        if adc is None:
            print("\r  等待串口数据...          ", end="", flush=True)
        else:
            print(f"\r  实时 ADC: {adc:4d}   电压: {adc_to_voltage(adc):.3f}V   ", end="", flush=True)
        time.sleep(0.15)
    print()

    return snapshot_mean(ch_index)


channels_out = []

print("=== 薄膜压力传感器模块校准向导（对照说明书四步）===")

try:
    input("\n步骤一：确认传感器已接入模块 S 端子、模块已上电，就绪后按回车继续...")

    for i, ch_name in enumerate(CHANNELS):
        print(f"\n--- {ch_name} ---")

        input("步骤二：确保该通道传感器上没有任何压力，稳定后按回车开始读取零压基线...")
        print("  正在读取零压基线，按回车确认当前读数稳定：")
        baseline_adc = live_until_enter(i)
        if baseline_adc is None:
            print("  未收到串口数据，跳过该通道，请检查连接。")
            continue
        print(f"  零压基线 ADC ≈ {baseline_adc:.1f}（电压 ≈ {adc_to_voltage(baseline_adc):.3f}V，应接近 0.1V）")

        weight_input = input(
            "\n步骤三：在传感器上稳定施加你要作为满量程的参考重量(g)，输入重量后回车（直接回车跳过该通道）："
        ).strip()
        if not weight_input:
            print("  已跳过该通道的满量程标定。")
            continue
        try:
            ref_weight_g = float(weight_input)
        except ValueError:
            print("  重量输入无效，已跳过该通道。")
            continue

        print("  保持该重量不变，缓慢调节对应电位器旋钮；调好后按回车确认：")
        full_scale_adc = live_until_enter(i)
        if full_scale_adc is None:
            print("  未收到串口数据，跳过该通道，请检查连接。")
            continue
        print(f"  已记录标定点：{ref_weight_g:g}g -> ADC ≈ {full_scale_adc:.1f}")

        channels_out.append({
            "label": CHANNEL_IDS[i],
            "ref_weight_g": ref_weight_g,
            "adc_full_scale": full_scale_adc,
            "adc_baseline": baseline_adc,
        })

    print("\n步骤四：所有通道调节完成。" if len(channels_out) == len(CHANNELS) else "\n部分通道未完成标定（见上方提示）。")

except KeyboardInterrupt:
    print("\n已中断。")

finally:
    keep_reading = False
    ser.close()
    if channels_out:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        config = {}
        if os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        config["channels"] = channels_out
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
        print(f"\n已保存 {len(channels_out)} 个通道的标定点到 {OUTPUT_PATH}")
    else:
        print("\n没有记录任何标定点。")
