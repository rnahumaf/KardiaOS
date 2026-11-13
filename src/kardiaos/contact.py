"""Experimental M2 contact flags, verified against labeled local 1L/6L captures.

In the supplied 1L capture, channel 2 had low bits 01 in every accepted sample;
both channels had 00 in the 6L capture. Other nonzero codes are treated as
unavailable, not guessed. This is not an official AliveCor protocol contract.
"""
import numpy as np

CONTACT_SETTLE_SAMPLES = 150  # 500 ms confirmation; loss takes effect immediately.


def channel_available(raw):
    return (np.asarray(raw, dtype=np.int16) & 3) == 0


class ContactTracker:
    def __init__(self):
        self.both_streak = 0

    def reset(self):
        self.both_streak = 0

    def update(self, raw):
        available = channel_available(raw)
        modes = np.zeros(len(available), dtype=np.uint8)
        for index, (first, second) in enumerate(available):
            self.both_streak = self.both_streak + 1 if first and second else 0
            if first:
                modes[index] = 6 if self.both_streak >= CONTACT_SETTLE_SAMPLES else 1
        return modes


def infer_modes(raw, timestamps):
    tracker = ContactTracker()
    result = np.zeros(len(raw), dtype=np.uint8)
    boundaries = np.r_[0, np.flatnonzero(np.diff(timestamps) > .12) + 1, len(raw)]
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        tracker.reset()
        result[start:end] = tracker.update(raw[start:end])
    return result
