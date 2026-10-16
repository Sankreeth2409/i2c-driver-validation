class Sensor:
    """TMP102-style temperature sensor on an I2C bus (simplified register map)."""

    def __init__(self, bus, address=0x48, temperature_c=25.0):
        self.address = address
        self.temperature_c = temperature_c
        self.regs = {0x01: 0x60A0, 0x02: 0x4B00, 0x03: 0x5000}   # config, T_low, T_high
        self.pointer = 0
        self.got_pointer = False
        self.wbytes = []
        self.phase = "IDLE"
        self.is_addr = False
        self.reading = False
        self.bits = []
        self.byte = 0
        self.tx = []
        self.tx_index = 0
        self.tx_bit = 0
        self.master_acked = False
        self.prev_sda = 1
        self.prev_scl = 1
        bus.devices.append(self)

    def reg_value(self, reg):
        if reg == 0x00:
            raw = int(round(self.temperature_c / 0.0625)) & 0xFFF   # 12-bit, 0.0625 C per step
            return raw << 4
        return self.regs[reg]

    def handle_write_byte(self, byte):
        if not self.got_pointer:
            self.pointer = byte & 0x03
            self.got_pointer = True
            self.wbytes = []
        else:
            self.wbytes.append(byte)
            if len(self.wbytes) == 2 and self.pointer != 0:       # register 0 is read-only
                self.regs[self.pointer] = (self.wbytes[0] << 8) | self.wbytes[1]
                self.wbytes = []

    def drive_bit(self, bus):
        byte = self.tx[self.tx_index % 2]
        bit = (byte >> (7 - self.tx_bit)) & 1
        bus.drive("sensor", "sda", bit)

    def on_change(self, bus):
        sda, scl = bus.sda(), bus.scl()

        if scl == 1 and self.prev_scl == 1 and sda != self.prev_sda:
            if sda == 0:                                   # START or repeated START
                self.phase, self.is_addr, self.bits = "RX", True, []
            else:                                          # STOP
                self.phase = "IDLE"

        elif scl == 1 and self.prev_scl == 0:              # SCL rising edge
            if self.phase == "RX":
                self.bits.append(sda)
                if len(self.bits) == 8:
                    self.byte = int("".join(str(b) for b in self.bits), 2)
                    self.phase = "RX_DONE"
            elif self.phase == "TX_ACK":                   # master's ACK/NACK for the byte we sent
                self.master_acked = (sda == 0)
                self.phase = "TX_ACK_DONE"

        elif scl == 0 and self.prev_scl == 1:              # SCL falling edge
            if self.phase == "RX_DONE":
                if self.is_addr:
                    if (self.byte >> 1) == self.address:
                        self.reading = bool(self.byte & 1)
                        bus.drive("sensor", "sda", 0)      # ACK the address
                        self.phase = "ACK_ADDR"
                    else:
                        self.phase = "IDLE"                # not for us
                else:
                    self.handle_write_byte(self.byte)
                    bus.drive("sensor", "sda", 0)          # ACK the data byte
                    self.phase = "ACK_DATA"

            elif self.phase == "ACK_ADDR":
                bus.drive("sensor", "sda", 1)              # release after the ACK clock
                if self.reading:
                    value = self.reg_value(self.pointer)
                    self.tx = [value >> 8, value & 0xFF]
                    self.tx_index, self.tx_bit = 0, 0
                    self.drive_bit(bus)                    # put the first bit on SDA
                    self.phase = "TX"
                else:
                    self.phase, self.bits, self.is_addr = "RX", [], False
                    self.got_pointer = False
                    self.wbytes = []

            elif self.phase == "ACK_DATA":
                bus.drive("sensor", "sda", 1)
                self.phase, self.bits = "RX", []

            elif self.phase == "TX":
                self.tx_bit += 1
                if self.tx_bit < 8:
                    self.drive_bit(bus)                    # next bit
                else:
                    bus.drive("sensor", "sda", 1)          # let go so the master can ACK/NACK
                    self.phase = "TX_ACK"

            elif self.phase == "TX_ACK_DONE":
                if self.master_acked:
                    self.tx_index += 1
                    self.tx_bit = 0
                    self.drive_bit(bus)                    # master wants another byte
                    self.phase = "TX"
                else:
                    bus.drive("sensor", "sda", 1)          # NACK: master is done
                    self.phase = "IDLE"

        self.prev_sda, self.prev_scl = bus.sda(), bus.scl()

class StretchingSensor(Sensor):
    """Same sensor, but it holds SCL low for stretch_us after receiving each byte."""

    def __init__(self, bus, address=0x48, temperature_c=25.0, stretch_us=30):
        super().__init__(bus, address, temperature_c)
        self.stretch_us = stretch_us

    def on_change(self, bus):
        before = self.phase
        super().on_change(bus)
        if before == "RX_DONE" and self.phase in ("ACK_ADDR", "ACK_DATA"):
            bus.drive("sensor", "scl", 0)                                     # hold the clock low
            bus.schedule(self.stretch_us, lambda: bus.drive("sensor", "scl", 1))   # release later