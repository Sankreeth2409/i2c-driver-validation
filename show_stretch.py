import matplotlib.pyplot as plt
from run_sensor import Board
from i2c_decode import decode, format_events, plot_decoded

slow = Board(25.0, stretch_us=30)
slow.read_reg(0x48, 0x00)
events = decode(slow.bus.log)
print(format_events(events))
plot_decoded(slow.bus, events, "Read with clock stretching (sensor holds SCL low for 30 us)", "day5_stretch.png")
plt.show()