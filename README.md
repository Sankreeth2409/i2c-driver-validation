# I2C Driver Validation

![CI](https://github.com/sankreeth2409/i2c-driver-validation/actions/workflows/ci.yml/badge.svg)

A bit-banged I2C master driver in C, tested against a simulated bus and a simulated temperature sensor, with a logic-analyzer-style protocol decoder and fault-injection tests.

**Note:** everything is simulated; no hardware was used. The driver touches the bus only through 5 functions (set/read SDA, set/read SCL, delay), so on a real microcontroller they would become GPIO and timer calls. Built step by step with I built this step by step with an AI assistant providing the code; I typed, ran, tested and verified every stage..

## What's in it
| File | Purpose |
|---|---|
| `i2c_driver.c` | Bit-banged I2C master: write, write-then-read with repeated START, clock-stretch timeout, bus recovery |
| `i2c_sim.py` | Open-drain bus model (SDA/SCL) with waveform recording and plotting |
| `timed_bus.py` | Bus with timers, used to model clock stretching |
| `sensor.py` | TMP102-style temperature sensor (register map, reads and writes) and a clock-stretching variant |
| `i2c_decode.py` | Protocol decoder: raw SDA/SCL samples back to readable bus traffic |
| `faults.py` | Fault injection: sensor hung in the middle of a read |
| `test_i2c.py` | 10 automated tests |

## Example: decoded transaction
Reading the temperature register, decoded from the SDA/SCL waveform only:

    S  0x48 W A  0x00 A  Sr  0x48 R A  0x19 A  0x00 N  P

(start, write address 0x48, register 0x00, repeated start, read address, two data bytes = 25.0 C, NACK on the last byte, stop)

![decoded read](docs/day4_decoded.png)

## Faults tested
| Fault | What the driver does |
|---|---|
| Wrong address | Gets a NACK, returns 0 |
| Sensor stretches the clock for 30 us | Waits for SCL to rise; the read takes 527 us instead of 449 us |
| Clock held low forever | Gives up after 200 us and returns -1 |
| Sensor holds SDA low mid-read | Recovery: 8 clock pulses free the bus, then a STOP; the next read works |
| Write to a read-only register | Ignored by the sensor model; the temperature is unchanged |

![clock stretching](docs/day5_stretch.png)
![bus recovery](docs/day6_recovery.png)

## What I learned
- ACK, NACK and START/STOP are defined by who pulls SDA low and when; a decoder only needs the two wires to recover the whole conversation.
- A driver that ignores clock stretching or has no timeout either reads garbage or hangs forever, so both need explicit handling and tests.

## Limitations
- Simulated bus and sensor; no real hardware or real timing jitter
- Single master, 7-bit addresses only, no arbitration
- Sensor model is TMP102-style and simplified, not the full real part

## Run it
    python3 -m venv .venv
    source .venv/bin/activate
    pip install matplotlib
    clang -O2 -Wall -shared -fPIC -o libi2c.dylib i2c_driver.c    # macOS (Linux: gcc ... -o libi2c.so)
    python3 -m unittest -v
    python3 run_sensor.py
    python3 i2c_decode.py
    python3 faults.py
