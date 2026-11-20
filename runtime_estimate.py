"""Conservative AC180P runtime estimate using BLUETTI's published formula.

https://www.bluettipower.com/products/ac180p/
1440 Wh * SOC * 90% DoD * 85% efficiency / (output W + 15 W).
This is a load-based estimate, not telemetry from the battery's BMS.
"""
import math
from collections import deque

CAPACITY_WH = 1440
DEPTH_OF_DISCHARGE = .90
EFFICIENCY = .85
SELF_CONSUMPTION_W = 15


def runtime_hours(soc, load_w, capacity_wh=CAPACITY_WH):
    if type(soc) not in (int, float) or not math.isfinite(soc) or not 0 <= soc <= 100:
        return None
    if type(load_w) not in (int, float) or not math.isfinite(load_w) or load_w <= 0:
        return None
    return capacity_wh * soc / 100 * DEPTH_OF_DISCHARGE * EFFICIENCY / (load_w + SELF_CONSUMPTION_W)


def format_runtime(hours):
    if hours is None:
        return '—'
    if hours <= 0:
        return '0 хв'
    minutes = int(hours * 60 // 5) * 5
    if minutes < 5:
        return '≈ <5 хв'
    h, m = divmod(minutes, 60)
    if not h:
        return f'≈ {m} хв'
    return f'≈ {h} год {m:02d} хв' if m else f'≈ {h} год'


class RuntimeEstimator:
    def __init__(self, window_seconds=20, capacity_wh=CAPACITY_WH):
        self.window = window_seconds
        self.samples = deque(maxlen=100)
        self.average_w = None
        self.capacity_wh = capacity_wh

    def clear(self):
        self.samples.clear()
        self.average_w = None

    def update(self, soc, input_w, output_w, now):
        # With external input/bypass, output power isn't battery drain.
        if type(input_w) not in (int, float) or not math.isfinite(input_w) or input_w != 0 or runtime_hours(soc, output_w) is None:
            self.clear()
            return None
        if self.samples and now - self.samples[-1][0] > 6:
            self.clear()
        self.samples.append((now, output_w))
        while self.samples and now - self.samples[0][0] > self.window:
            self.samples.popleft()
        self.average_w = sum(value for _, value in self.samples) / len(self.samples)
        return runtime_hours(soc, self.average_w, self.capacity_wh)
