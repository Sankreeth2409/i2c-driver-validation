import ctypes
import os
import sys
from timed_bus import TimedBus
from sensor import Sensor, StretchingSensor

_LIB_NAME = "libi2c.dylib" if sys.platform == "darwin" else "libi2c.so"
lib = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), _LIB_NAME))

SET_PIN = ctypes.CFUNCTYPE(None, ctypes.c_int)
READ_PIN = ctypes.CFUNCTYPE(ctypes.c_int)
DELAY = ctypes.CFUNCTYPE(None, ctypes.c_int)
U8P = ctypes.POINTER(ctypes.c_uint8)

lib.i2c_set_hal.argtypes = [SET_PIN, SET_PIN, READ_PIN, READ_PIN, DELAY]
lib.i2c_set_hal.restype = None
lib.i2c_write.argtypes = [ctypes.c_uint8, U8P, ctypes.c_int]
lib.i2c_write.restype = ctypes.c_int
lib.i2c_write_read.argtypes = [ctypes.c_uint8, U8P, ctypes.c_int, U8P, ctypes.c_int]
lib.i2c_write_read.restype = ctypes.c_int


class Board:
    """Connects the C driver to a simulated bus with a sensor on it.
    Only the most recently created Board is connected to the driver.
    status: 1 = all ACKed, 0 = NACK, -1 = timeout."""

    def __init__(self, temperature_c=25.0, stretch_us=0):
        self.bus = TimedBus()
        if stretch_us > 0:
            self.sensor = StretchingSensor(self.bus, 0x48, temperature_c, stretch_us)
        else:
            self.sensor = Sensor(self.bus, 0x48, temperature_c)
        self.status = None

        def sda_write(level):
            self.bus.drive("master", "sda", level)

        def scl_write(level):
            self.bus.drive("master", "scl", level)

        def sda_read():
            return self.bus.sda()

        def scl_read():
            return self.bus.scl()

        def delay_us(us):
            self.bus.wait(us)

        self.callbacks = (SET_PIN(sda_write), SET_PIN(scl_write),
                          READ_PIN(sda_read), READ_PIN(scl_read), DELAY(delay_us))
        lib.i2c_set_hal(*self.callbacks)

    def write(self, addr7, data):
        buf = (ctypes.c_uint8 * len(data))(*data)
        self.status = lib.i2c_write(addr7, buf, len(data))
        return self.status == 1

    def read_reg(self, addr7, reg, nbytes=2):
        w = (ctypes.c_uint8 * 1)(reg)
        r = (ctypes.c_uint8 * nbytes)()
        self.status = lib.i2c_write_read(addr7, w, 1, r, nbytes)
        return self.status == 1, list(r)


def to_celsius(value16):
    raw12 = value16 >> 4
    if raw12 & 0x800:
        raw12 -= 4096
    return raw12 * 0.0625


if __name__ == "__main__":
    normal = Board(25.0)
    ok, d = normal.read_reg(0x48, 0x00)
    print(f"Normal sensor    : ACK={ok}, status={normal.status}, bytes={[hex(b) for b in d]}, "
          f"{to_celsius((d[0] << 8) | d[1]):.4f} C, took {normal.bus.t} us")

    slow = Board(25.0, stretch_us=30)
    ok, d = slow.read_reg(0x48, 0x00)
    print(f"Stretching 30 us : ACK={ok}, status={slow.status}, bytes={[hex(b) for b in d]}, "
          f"took {slow.bus.t} us")

    dead = Board(25.0, stretch_us=100000)      # holds the clock far too long
    ok, d = dead.read_reg(0x48, 0x00)
    print(f"Stuck clock      : status={dead.status} (-1 = timeout), took {dead.bus.t} us")