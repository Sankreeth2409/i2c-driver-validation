import matplotlib.pyplot as plt
from i2c_sim import plot_bus
from run_sensor import Board


def decode(log):
    """Turn raw (time, sda, scl) samples into I2C events, using only the two wires."""
    events = []
    prev_sda, prev_scl = log[0][1], log[0][2]
    active = False          # are we inside a transaction?
    first = True            # is the next byte the address byte?
    bits = []
    for t, sda, scl in log[1:]:
        if scl == 1 and prev_scl == 1 and sda != prev_sda:
            if sda == 0:                                   # SDA falls while SCL high
                events.append(("Sr" if active else "S", t))
                active, first, bits = True, True, []
            else:                                          # SDA rises while SCL high
                events.append(("P", t))
                active, bits = False, []
        elif scl == 1 and prev_scl == 0 and active:        # SCL rising edge: sample SDA
            bits.append(sda)
            if len(bits) == 9:                             # 8 data bits + 1 ACK bit
                byte = int("".join(str(b) for b in bits[:8]), 2)
                ack = (bits[8] == 0)                       # low = ACK
                if first:
                    events.append(("ADDR", t, byte >> 1, "R" if byte & 1 else "W", ack))
                    first = False
                else:
                    events.append(("DATA", t, byte, ack))
                bits = []
        prev_sda, prev_scl = sda, scl
    return events


def format_events(events):
    parts = []
    for e in events:
        if e[0] in ("S", "Sr", "P"):
            parts.append(e[0])
        elif e[0] == "ADDR":
            parts.append(f"0x{e[2]:02X} {e[3]} {'A' if e[4] else 'N'}")
        else:
            parts.append(f"0x{e[2]:02X} {'A' if e[3] else 'N'}")
    return "  ".join(parts)


def read_bytes(events):
    """Bytes the master read from the slave."""
    out, reading = [], False
    for e in events:
        if e[0] == "ADDR":
            reading = (e[3] == "R")
        elif e[0] == "DATA" and reading:
            out.append(e[2])
    return out


def plot_decoded(bus, events, title, filename):
    plot_bus(bus, title, filename)
    fig = plt.gcf()
    ax_scl = fig.axes[0]
    for e in events:
        t = e[1]
        if e[0] in ("S", "Sr", "P"):
            ax_scl.text(t, 1.1, e[0], ha="center", fontsize=9, fontweight="bold")
        elif e[0] == "ADDR":
            ax_scl.text(t - 40, 1.1, f"0x{e[2]:02X} {e[3]} {'A' if e[4] else 'N'}", ha="center", fontsize=9)
        else:
            ax_scl.text(t - 40, 1.1, f"0x{e[2]:02X} {'A' if e[3] else 'N'}", ha="center", fontsize=9)
    fig.savefig(filename, dpi=150)


if __name__ == "__main__":
    b1 = Board(25.0)
    b1.read_reg(0x48, 0x00)
    ev1 = decode(b1.bus.log)
    print("Read temperature :", format_events(ev1))

    b2 = Board(25.0)
    b2.write(0x48, [0x02, 0x1E, 0x00])
    ev2 = decode(b2.bus.log)
    print("Write T_low      :", format_events(ev2))

    b3 = Board(25.0)
    b3.read_reg(0x49, 0x00)
    ev3 = decode(b3.bus.log)
    print("Wrong address    :", format_events(ev3))

    print("Decoded read bytes match the sensor:", read_bytes(ev1) == [0x19, 0x00])

    plot_decoded(b1.bus, ev1, "Decoded I2C read of temperature register 0x00", "day4_decoded.png")
    plt.show()