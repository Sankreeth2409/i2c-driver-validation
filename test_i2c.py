import unittest
from run_sensor import Board, to_celsius
from faults import hang_sensor_mid_read, recover_bus
from i2c_decode import decode, format_events, read_bytes

READ_TEMP = "S  0x48 W A  0x00 A  Sr  0x48 R A  0x19 A  0x00 N  P"


class TestI2C(unittest.TestCase):

    def test_read_temperature(self):
        board = Board(25.0)
        ok, d = board.read_reg(0x48, 0x00)
        self.assertTrue(ok)
        self.assertEqual(d, [0x19, 0x00])
        self.assertAlmostEqual(to_celsius((d[0] << 8) | d[1]), 25.0)

    def test_negative_temperature(self):
        board = Board(-10.5)
        ok, d = board.read_reg(0x48, 0x00)
        self.assertTrue(ok)
        self.assertAlmostEqual(to_celsius((d[0] << 8) | d[1]), -10.5)

    def test_write_then_read_back_register(self):
        board = Board(25.0)
        self.assertTrue(board.write(0x48, [0x02, 0x1E, 0x00]))
        ok, d = board.read_reg(0x48, 0x02)
        self.assertTrue(ok)
        self.assertEqual(d, [0x1E, 0x00])

    def test_wrong_address_is_nacked(self):
        board = Board(25.0)
        ok, d = board.read_reg(0x49, 0x00)
        self.assertFalse(ok)
        self.assertEqual(board.status, 0)

    def test_temperature_register_is_read_only(self):
        board = Board(25.0)
        self.assertTrue(board.write(0x48, [0x00, 0x12, 0x34]))
        ok, d = board.read_reg(0x48, 0x00)
        self.assertEqual(d, [0x19, 0x00])

    def test_clock_stretching_is_tolerated(self):
        normal = Board(25.0)
        normal.read_reg(0x48, 0x00)
        normal_time = normal.bus.t

        slow = Board(25.0, stretch_us=30)
        ok, d = slow.read_reg(0x48, 0x00)
        self.assertTrue(ok)
        self.assertEqual(d, [0x19, 0x00])
        self.assertGreater(slow.bus.t, normal_time)

    def test_stuck_clock_times_out(self):
        board = Board(25.0, stretch_us=100000)
        ok, d = board.read_reg(0x48, 0x00)
        self.assertFalse(ok)
        self.assertEqual(board.status, -1)

    def test_stuck_data_line_is_recovered(self):
        board = Board(25.0)
        hang_sensor_mid_read(board.bus, board.sensor)
        self.assertEqual(board.bus.sda(), 0)
        self.assertEqual(recover_bus(), 8)
        self.assertEqual(board.bus.sda(), 1)
        ok, d = board.read_reg(0x48, 0x00)
        self.assertTrue(ok)
        self.assertEqual(d, [0x19, 0x00])

    def test_decoder_reads_the_transaction(self):
        board = Board(25.0)
        board.read_reg(0x48, 0x00)
        events = decode(board.bus.log)
        self.assertEqual(format_events(events), READ_TEMP)
        self.assertEqual(read_bytes(events), [0x19, 0x00])

    def test_decoder_sees_same_transaction_with_stretching(self):
        board = Board(25.0, stretch_us=30)
        board.read_reg(0x48, 0x00)
        self.assertEqual(format_events(decode(board.bus.log)), READ_TEMP)


if __name__ == "__main__":
    unittest.main()