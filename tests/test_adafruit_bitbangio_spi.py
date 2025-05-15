# SPDX-FileCopyrightText: KB Sriram
# SPDX-License-Identifier: MIT

from typing import Literal, Sequence

import pytest
import simulated_spi as sspi
import simulator as sim

import adafruit_bitbangio

_CLOCK_NET = "clock"
_COPI_NET = "copi"
_CIPO_NET = "cipo"
_ENABLE_NET = "enable"


def _check_bit(
    data: bytearray,
    bits_read: int,
    last_copi_state: sim.Level,
) -> None:
    """Checks that the copi state matches the bit we should be writing."""
    intdata = int.from_bytes(data, "big")
    nbits = 8 * len(data)
    expected_bit_value = (intdata >> (nbits - bits_read - 1)) & 0x1
    expected_level = sim.Level.HIGH if expected_bit_value else sim.Level.LOW
    assert last_copi_state == expected_level


def _check_write(
    data: bytearray,
    change_history: Sequence[sim.Change],
    polarity: Literal[0, 1],
    phase: Literal[0, 1],
    baud: int,
) -> None:
    """Checks that the net level changes have a correct sequence of write events."""
    state = "disabled"
    last_clock_state = sim.Level.Z
    last_copi_state = sim.Level.Z
    last_copi_us = 0
    idle, active = (sim.Level.HIGH, sim.Level.LOW) if polarity else (sim.Level.LOW, sim.Level.HIGH)
    bits_read = 0
    # We want data to be written at least this long before a read
    # transition.
    quarter_period = 1e6 / baud / 4

    for change in change_history:
        if (
            state == "disabled"
            and change.net_name == _ENABLE_NET
            and change.level == sim.Level.HIGH
        ):
            # In this implementation, we should always start out with the
            # clock in the idle state by the time the device is enabled.
            assert last_clock_state == idle
            bits_read = 0
            state = "wait_for_read"
        elif state == "wait_for_read" and change.net_name == _CLOCK_NET:
            # phase 0 reads on idle->active, and phase 1 reads on active->idle.
            should_read = change.level == active if phase == 0 else change.level == idle
            if should_read:
                # Check we have the right data
                _check_bit(data, bits_read, last_copi_state)
                # Check the data  was also set early enough.
                assert change.time_us - last_copi_us > quarter_period
                bits_read += 1
                if bits_read == 8:
                    return
        # Track the last time we changed the clock and data values.
        if change.net_name == _COPI_NET:
            if last_copi_state != change.level:
                last_copi_state = change.level
                last_copi_us = change.time_us
        elif change.net_name == _CLOCK_NET:
            if last_clock_state != change.level:
                last_clock_state = change.level
    # If we came here, we haven't read enough bits.
    pytest.fail("Only {bits_read} bits were read")


class TestBitbangSpi:
    def setup_method(self) -> None:
        sim.engine.reset()
        clock = sim.engine.create_net(_CLOCK_NET, monitor=True)
        copi = sim.engine.create_net(_COPI_NET, monitor=True)
        cipo = sim.engine.create_net(_CIPO_NET, monitor=True)
        enable = sim.engine.create_net(_ENABLE_NET, monitor=True)
        self.clock_pin = sim.FakePin("clock_pin", clock)
        self.copi_pin = sim.FakePin("copi_pin", copi)
        self.cipo_pin = sim.FakePin("cipo_pin", cipo)
        self.enable_pin = sim.FakePin("enable_pin", enable)
        self.enable_pin.init(mode=sim.Mode.OUT)
        self.spibus = sspi.SpiBus(clock=clock, copi=copi, cipo=cipo, enable=enable)
        self._enable_net(0)

    def _enable_net(self, val: Literal[0, 1]) -> None:
        self.enable_pin.value(val)

    @sim.stub
    @pytest.mark.parametrize("baud", [100])
    @pytest.mark.parametrize("polarity", [0, 1])
    @pytest.mark.parametrize("phase", [0, 1])
    @pytest.mark.parametrize("data", ["10101010", "01010101", "01111110", "10000001"])
    def test_write(
        self, baud: int, polarity: Literal[0, 1], phase: Literal[0, 1], data: str
    ) -> None:
        data_array = bytearray(int(data, 2).to_bytes(1, byteorder="big"))
        # Send one byte of data into the void to verify write timing.
        with adafruit_bitbangio.SPI(clock=self.clock_pin, MOSI=self.copi_pin) as spi:
            spi.try_lock()
            spi.configure(baudrate=baud, polarity=polarity, phase=phase, bits=8)
            self._enable_net(1)
            spi.write(data_array)
            self._enable_net(0)

        # Monitored nets can be viewed in sigrock by dumping out a VCD file.
        # sim.engine.write_vcd(f"/tmp/test_{polarity}_{phase}_{data}.vcd")
        _check_write(
            data_array,
            sim.engine.change_history(),
            polarity=polarity,
            phase=phase,
            baud=baud,
        )

    @sim.stub
    @pytest.mark.parametrize("baud", [100])
    @pytest.mark.parametrize("polarity", [0, 1])
    @pytest.mark.parametrize("phase", [0, 1])
    @pytest.mark.parametrize("data", ["10101010", "01010101", "01111110", "10000001"])
    def test_readinto(
        self, baud: int, polarity: Literal[0, 1], phase: Literal[0, 1], data: str
    ) -> None:
        data_int = int(data, 2)
        data_array = bytearray(data_int.to_bytes(1, byteorder="big"))
        # attach a device that sends a constant.
        _ = sspi.Constant(data=data_array, bus=self.spibus, polarity=polarity, phase=phase)

        # Read/write a byte of data
        with adafruit_bitbangio.SPI(
            clock=self.clock_pin, MOSI=self.copi_pin, MISO=self.cipo_pin
        ) as spi:
            spi.try_lock()
            spi.configure(baudrate=baud, polarity=polarity, phase=phase, bits=8)
            self._enable_net(1)
            received_data = bytearray(1)
            spi.readinto(received_data, write_value=data_int)
            self._enable_net(0)

        # Monitored nets can be viewed in sigrock by dumping out a VCD file.
        # sim.engine.write_vcd(f"/tmp/test_{polarity}_{phase}_{data}.vcd")

        # Check we read the constant correctly from our device.
        assert data_array == received_data
        # Check the timing on the data we wrote out.
        _check_write(
            data_array,
            sim.engine.change_history(),
            polarity=polarity,
            phase=phase,
            baud=baud,
        )

    @sim.stub
    @pytest.mark.parametrize("baud", [100])
    @pytest.mark.parametrize("polarity", [0, 1])
    @pytest.mark.parametrize("phase", [0, 1])
    @pytest.mark.parametrize(
        "data", ["10101010", "01010101", "01111110", "10000001", "1000010101111110"]
    )
    def test_write_readinto(
        self, baud: int, polarity: Literal[0, 1], phase: Literal[0, 1], data: str
    ) -> None:
        nbytes = len(data) // 8
        data_array = bytearray(int(data, 2).to_bytes(nbytes, byteorder="big"))
        # attach a device that sends a constant.
        _ = sspi.Constant(data=data_array, bus=self.spibus, polarity=polarity, phase=phase)

        # Read/write data array
        with adafruit_bitbangio.SPI(
            clock=self.clock_pin, MOSI=self.copi_pin, MISO=self.cipo_pin
        ) as spi:
            spi.try_lock()
            spi.configure(baudrate=baud, polarity=polarity, phase=phase, bits=8)
            self._enable_net(1)
            received_data = bytearray(nbytes)
            spi.write_readinto(buffer_out=data_array, buffer_in=received_data)
            self._enable_net(0)

        # Monitored nets can be viewed in sigrock by dumping out a VCD file.
        # sim.engine.write_vcd(f"/tmp/test_{polarity}_{phase}_{data}.vcd")

        # Check we read the constant correctly from our device.
        assert data_array == received_data
        # Check the timing on the data we wrote out.
        _check_write(
            data_array,
            sim.engine.change_history(),
            polarity=polarity,
            phase=phase,
            baud=baud,
        )
