# SPDX-FileCopyrightText: KB Sriram
# SPDX-License-Identifier: MIT

from typing import Sequence

import pytest
import simulated_i2c as si2c
import simulator as sim

import adafruit_bitbangio

_SCL_NET = "scl"
_SDA_NET = "sda"


class TestBitbangI2C:
    def setup_method(self) -> None:
        sim.engine.reset()
        # Create nets, with a pullup by default.
        scl = sim.engine.create_net(_SCL_NET, monitor=True, default_level=sim.Level.HIGH)
        sda = sim.engine.create_net(_SDA_NET, monitor=True, default_level=sim.Level.HIGH)
        self.scl_pin = sim.FakePin("scl_pin", scl)
        self.sda_pin = sim.FakePin("sda_pin", sda)
        self.i2cbus = si2c.I2CBus(scl=scl, sda=sda)

    @sim.stub
    @pytest.mark.parametrize("addresses", [[0x42, 0x43]])
    def test_scan(self, addresses: Sequence[int]) -> None:
        # Create a set of data sinks, one for each address.
        for address in addresses:
            si2c.Constant(hex(address), address=address, bus=self.i2cbus)

        with adafruit_bitbangio.I2C(
            scl=self.scl_pin, sda=self.sda_pin, frequency=1000, timeout=1
        ) as i2c:
            i2c.try_lock()
            scanned = i2c.scan()
            i2c.unlock()

        assert addresses == scanned

    @sim.stub
    @pytest.mark.parametrize(
        "data", ["11000011", "00111100", "1010101001010101", "1010101111010100"]
    )
    def test_write(
        self,
        data: str,
    ) -> None:
        datalen = len(data) // 8
        data_array = bytearray(int(data, 2).to_bytes(datalen, byteorder="big"))

        # attach a device that records whatever we send to it.
        device = si2c.Constant("target", address=0x42, bus=self.i2cbus)

        # Write data over the bus and verify the device received it.
        with adafruit_bitbangio.I2C(scl=self.scl_pin, sda=self.sda_pin, frequency=1000) as i2c:
            i2c.try_lock()
            i2c.writeto(address=0x42, buffer=data_array)
            i2c.unlock()

        # Useful to debug signals in pulseview.
        # sim.engine.write_vcd(f"/tmp/test_{data}.vcd")
        assert data_array == device.all_received_data()

    @sim.stub
    def test_write_no_ack(self) -> None:
        # attach a device that will ack the address, but not the data.
        si2c.Constant("target", address=0x42, bus=self.i2cbus, ack_data=False)

        with adafruit_bitbangio.I2C(scl=self.scl_pin, sda=self.sda_pin, frequency=1000) as i2c:
            i2c.try_lock()
            with pytest.raises(RuntimeError) as info:
                i2c.writeto(address=0x42, buffer=b"\x42")
            i2c.unlock()

        assert "not responding" in str(info.value)

    @sim.stub
    @pytest.mark.parametrize("data", ["11000011", "00111100"])
    def test_write_clock_stretching(self, data: str) -> None:
        datalen = len(data) // 8
        data_array = bytearray(int(data, 2).to_bytes(datalen, byteorder="big"))

        # attach a device that does clock stretching, but not exceed our timeout.
        device = si2c.Constant("target", address=0x42, bus=self.i2cbus, clock_stretch_sec=1)

        with adafruit_bitbangio.I2C(
            scl=self.scl_pin, sda=self.sda_pin, frequency=1000, timeout=2.0
        ) as i2c:
            i2c.try_lock()
            i2c.writeto(address=0x42, buffer=data_array)
            i2c.unlock()

        assert data_array == device.all_received_data()

    @sim.stub
    def test_write_clock_timeout(self) -> None:
        # attach a device that does clock stretching, but exceeds our timeout.
        si2c.Constant("target", address=0x42, bus=self.i2cbus, clock_stretch_sec=3)

        with adafruit_bitbangio.I2C(
            scl=self.scl_pin, sda=self.sda_pin, frequency=1000, timeout=1
        ) as i2c:
            i2c.try_lock()
            with pytest.raises(RuntimeError) as info:
                i2c.writeto(address=0x42, buffer=b"\x42")
            i2c.unlock()

        assert "timed out" in str(info.value)

    @sim.stub
    @pytest.mark.parametrize("count", [1, 2, 5])
    @pytest.mark.parametrize("data", ["11000011", "00111100", "10101010", "01010101"])
    def test_readfrom(self, count: int, data: str) -> None:
        value = int(data, 2)
        expected_array = bytearray([value] * count)
        data_array = bytearray(count)

        # attach a device that sends a constant byte of data.
        si2c.Constant("target", address=0x42, bus=self.i2cbus, data_to_send=value)

        # Confirm we were able to read back the data
        with adafruit_bitbangio.I2C(scl=self.scl_pin, sda=self.sda_pin, frequency=1000) as i2c:
            i2c.try_lock()
            i2c.readfrom_into(address=0x42, buffer=data_array)
            i2c.unlock()

        # Useful to debug signals in pulseview.
        # sim.engine.write_vcd(f"/tmp/test_{count}_{data}.vcd")
        assert data_array == expected_array

    @sim.stub
    @pytest.mark.parametrize(
        "send_data",
        [
            "11000011",
            "00111100",
            "10101010",
            "0101010",
        ],
    )
    @pytest.mark.parametrize(
        "expect_data",
        [
            "11000011",
            "00111100",
            "10101010",
            "01010101",
        ],
    )
    def test_writeto_readfrom(self, send_data: str, expect_data: str) -> None:
        send_array = bytearray(int(send_data, 2).to_bytes(1, byteorder="big"))
        expect_value = int(expect_data, 2)
        data_array = bytearray(1)

        # attach a device that sends a constant byte of data.
        device = si2c.Constant("target", address=0x42, bus=self.i2cbus, data_to_send=expect_value)

        # Send the send_data, and check we got back expect_data
        with adafruit_bitbangio.I2C(scl=self.scl_pin, sda=self.sda_pin, frequency=1000) as i2c:
            i2c.try_lock()
            i2c.writeto_then_readfrom(address=0x42, buffer_out=send_array, buffer_in=data_array)
            i2c.unlock()

        # Useful to debug signals in pulseview.
        # sim.engine.write_vcd(f"/tmp/test_{send_data}_{expect_data}.vcd")
        assert send_array == device.all_received_data()
        assert data_array == bytearray([expect_value])
