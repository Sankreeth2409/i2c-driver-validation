import matplotlib.pyplot as plt

HALF = 5   # microseconds per half clock


class Bus:
    """Open-drain bus: a line is HIGH only if nobody is pulling it LOW."""

    def __init__(self):
        self.t = 0                    # time in microseconds
        self.pulling_low = {}         # (device, line) -> True if that device pulls the line low
        self.devices = []
        self.busy = False
        self.log = []                 # (time, sda, scl) every time something changes
        self.record()

    def level(self, line):
        for (device, ln), low in self.pulling_low.items():
            if ln == line and low:
                return 0
        return 1

    def sda(self):
        return self.level("sda")

    def scl(self):
        return self.level("scl")

    def record(self):
        self.log.append((self.t, self.sda(), self.scl()))

    def drive(self, device, line, level):
        """level 0 = pull the line low, level 1 = let go of the line."""
        self.pulling_low[(device, line)] = (level == 0)
        self.record()
        if not self.busy:
            self.busy = True
            for d in self.devices:
                d.on_change(self)
            self.busy = False

    def wait(self, us):
        self.t += us
        self.record()


class Slave:
    """A simple I2C slave that only accepts writes."""

    def __init__(self, bus, address):
        self.address = address
        self.phase = "IDLE"           # IDLE, BITS, ACK_PENDING, ACK
        self.is_addr = False
        self.bits = []
        self.byte = 0
        self.received = []
        self.prev_sda = 1
        self.prev_scl = 1
        bus.devices.append(self)

    def on_change(self, bus):
        sda, scl = bus.sda(), bus.scl()

        if scl == 1 and self.prev_scl == 1 and sda != self.prev_sda:
            if sda == 0:                                  # START: SDA falls while SCL is high
                self.phase, self.is_addr, self.bits = "BITS", True, []
            else:                                         # STOP: SDA rises while SCL is high
                self.phase = "IDLE"

        elif scl == 1 and self.prev_scl == 0:             # SCL rising edge: sample a bit
            if self.phase == "BITS":
                self.bits.append(sda)
                if len(self.bits) == 8:
                    self.byte = int("".join(str(b) for b in self.bits), 2)
                    self.phase = "ACK_PENDING"

        elif scl == 0 and self.prev_scl == 1:             # SCL falling edge
            if self.phase == "ACK_PENDING":
                if self.is_addr:
                    ack = (self.byte >> 1) == self.address and (self.byte & 1) == 0
                else:
                    ack = True
                    self.received.append(self.byte)
                if ack:
                    bus.drive("slave", "sda", 0)          # pull SDA low = ACK
                    self.phase = "ACK"
                else:
                    self.phase = "IDLE"                   # NACK: ignore everything until next START
            elif self.phase == "ACK":
                bus.drive("slave", "sda", 1)              # release SDA after the ACK clock
                self.phase, self.bits, self.is_addr = "BITS", [], False

        self.prev_sda, self.prev_scl = bus.sda(), bus.scl()


# ---------- Bit-banged master ----------
def i2c_start(bus):
    bus.drive("master", "sda", 1)
    bus.drive("master", "scl", 1)
    bus.wait(HALF)
    bus.drive("master", "sda", 0)
    bus.wait(HALF)
    bus.drive("master", "scl", 0)
    bus.wait(HALF)


def i2c_write_bit(bus, bit):
    bus.drive("master", "sda", bit)
    bus.wait(2)
    bus.drive("master", "scl", 1)
    bus.wait(HALF)
    bus.drive("master", "scl", 0)
    bus.wait(2)


def i2c_read_ack(bus):
    bus.drive("master", "sda", 1)          # let go of SDA so the slave can pull it low
    bus.wait(2)
    bus.drive("master", "scl", 1)
    bus.wait(2)
    ack = (bus.sda() == 0)                 # low = ACK, high = NACK
    bus.wait(HALF - 2)
    bus.drive("master", "scl", 0)
    bus.wait(2)
    return ack


def i2c_write_byte(bus, byte):
    for i in range(7, -1, -1):
        i2c_write_bit(bus, (byte >> i) & 1)
    return i2c_read_ack(bus)


def i2c_stop(bus):
    bus.drive("master", "sda", 0)
    bus.wait(2)
    bus.drive("master", "scl", 1)
    bus.wait(HALF)
    bus.drive("master", "sda", 1)
    bus.wait(HALF)


def i2c_write(bus, addr7, data):
    i2c_start(bus)
    ok = i2c_write_byte(bus, (addr7 << 1) | 0)
    if ok:
        for b in data:
            ok = i2c_write_byte(bus, b)
            if not ok:
                break
    i2c_stop(bus)
    return ok


def run(addr7, data):
    bus = Bus()
    slave = Slave(bus, 0x48)
    ok = i2c_write(bus, addr7, data)
    return bus, slave, ok


def plot_bus(bus, title, filename):
    t = [r[0] for r in bus.log]
    sda = [r[1] for r in bus.log]
    scl = [r[2] for r in bus.log]
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(12, 4))
    ax1.step(t, scl, where="post", color="black")
    ax1.set_ylabel("SCL")
    ax1.set_title(title)
    ax2.step(t, sda, where="post", color="black")
    ax2.set_ylabel("SDA")
    ax2.set_xlabel("Time (us)")
    for ax in (ax1, ax2):
        ax.set_ylim(-0.2, 1.3)
        ax.set_yticks([0, 1])
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)


if __name__ == "__main__":
    bus1, slave1, ok1 = run(0x48, [0x01, 0xA5])
    print(f"Address 0x48: ACK = {ok1}, slave got {[hex(b) for b in slave1.received]}, took {bus1.t} us")

    bus2, slave2, ok2 = run(0x50, [0x01, 0xA5])
    print(f"Address 0x50: ACK = {ok2}, slave got {[hex(b) for b in slave2.received]}, took {bus2.t} us")

    plot_bus(bus1, "I2C write to 0x48 (device present)", "day1_ack.png")
    plot_bus(bus2, "I2C write to 0x50 (no device, NACK)", "day1_nack.png")
    plt.show()