import ctypes
from run_sensor import Board, lib, to_celsius

lib.i2c_recover.argtypes = []
lib.i2c_recover.restype = ctypes.c_int


def hang_sensor_mid_read(bus, sensor):
    """Fault injection: the sensor is stuck halfway through sending a byte and holds SDA low."""
    sensor.phase = "TX"
    sensor.reading = True
    sensor.tx = [0x00, 0x00]
    sensor.tx_index = 0
    sensor.tx_bit = 0
    bus.pulling_low[("sensor", "sda")] = True
    bus.record()
    sensor.prev_sda = bus.sda()


def recover_bus():
    """Run the C driver's bus recovery. Returns the clock pulses used, or -1 if it failed."""
    return lib.i2c_recover()


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    from i2c_sim import plot_bus

    board = Board(25.0)
    hang_sensor_mid_read(board.bus, board.sensor)
    print(f"Before recovery: SDA = {board.bus.sda()} (0 = stuck low)")

    pulses = recover_bus()
    print(f"Recovery used {pulses} clock pulses, SDA = {board.bus.sda()}")

    ok, d = board.read_reg(0x48, 0x00)
    print(f"Read after recovery: ACK={ok}, bytes={[hex(b) for b in d]}, "
          f"{to_celsius((d[0] << 8) | d[1]):.4f} C")

    plot_bus(board.bus, "Stuck SDA freed by 8 clock pulses, then a normal read", "day6_recovery.png")
    plt.show()