from i2c_sim import Bus


class TimedBus(Bus):
    """Bus with timers: a device can schedule an action for a later time."""

    def __init__(self):
        self.timers = []          # (time, function) pairs that fire when time reaches them
        super().__init__()

    def schedule(self, delay_us, fn):
        self.timers.append((self.t + delay_us, fn))

    def wait(self, us):
        target = self.t + us
        while self.timers:
            self.timers.sort(key=lambda item: item[0])
            when, fn = self.timers[0]
            if when > target:
                break
            self.timers.pop(0)
            self.t = max(self.t, when)
            fn()
        self.t = target
        self.record()