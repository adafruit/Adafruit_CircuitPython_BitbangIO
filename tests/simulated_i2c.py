# SPDX-FileCopyrightText: KB Sriram
# SPDX-License-Identifier: MIT
"""Implementation of testable I2C devices."""

import dataclasses
import enum
import signal
import types
from typing import Any, Callable, Optional, Union

import simulator as sim
from typing_extensions import TypeAlias

_SignalHandler: TypeAlias = Union[Callable[[int, Optional[types.FrameType]], Any], int, None]


@enum.unique
class State(enum.Enum):
    IDLE = "idle"
    ADDRESS = "address"
    ACK = "ack"
    ACK_DONE = "ack_done"
    WAIT_ACK = "wait_ack"
    READ = "read"
    WRITE = "write"


@dataclasses.dataclass(frozen=True)
class I2CBus:
    scl: sim.Net
    sda: sim.Net


def _switch_to_output(pin: sim.FakePin, value: bool) -> None:
    pin.mode = sim.Mode.OUT
    pin.value(1 if value else 0)


def _switch_to_input(pin: sim.FakePin) -> None:
    pin.init(mode=sim.Mode.IN)
    pin.level = sim.Level.HIGH


class Constant:
    """I2C device that sinks all data and can send a constant."""

    # pylint:disable=too-many-instance-attributes
    # pylint:disable=too-many-arguments
    def __init__(
        self,
        name: str,
        address: int,
        bus: I2CBus,
        ack_data: bool = True,
        clock_stretch_sec: int = 0,
        data_to_send: int = 0,
    ) -> None:
        self._address = address
        self._scl = sim.FakePin(f"{name}_scl_pin", bus.scl)
        self._sda = sim.FakePin(f"{name}_sda_pin", bus.sda)
        self._last_scl_level = bus.scl.level
        self._ack_data = ack_data
        self._clock_stretch_sec = clock_stretch_sec
        self._prev_signal: _SignalHandler = None
        self._state = State.IDLE
        self._bit_count = 0
        self._received = 0
        self._all_received = bytearray()
        self._send_data = data_to_send
        self._sent_bit_count = 0
        self._in_write = 0

        bus.scl.on_level_change(self._on_level_change)
        bus.sda.on_level_change(self._on_level_change)

    def _move_state(self, nstate: State) -> None:
        self._state = nstate

    def _on_start(self) -> None:
        # This resets our state machine unconditionally and
        # starts waiting for an address.
        self._bit_count = 0
        self._received = 0
        self._move_state(State.ADDRESS)

    def _on_stop(self) -> None:
        # Reset and start idling.
        self._reset()

    def _reset(self) -> None:
        self._bit_count = 0
        self._received = 0
        self._move_state(State.IDLE)

    def _clock_release(
        self, ignored_signum: int, ignored_frame: Optional[types.FrameType] = None
    ) -> None:
        # First release the scl line
        _switch_to_input(self._scl)
        # Remove alarms
        signal.alarm(0)
        # Restore any existing signal.
        if self._prev_signal:
            signal.signal(signal.SIGALRM, self._prev_signal)
            self._prev_signal = None

    def _maybe_clock_stretch(self) -> None:
        if not self._clock_stretch_sec:
            return
        if self._state == State.IDLE:
            return
        # pull the clock line low
        _switch_to_output(self._scl, value=False)
        # Set an alarm to release the line after some time.
        self._prev_signal = signal.signal(signal.SIGALRM, self._clock_release)
        signal.alarm(self._clock_stretch_sec)

    def _on_byte_read(self) -> None:
        self._all_received.append(self._received)

    def _on_clock_fall(self) -> None:
        self._maybe_clock_stretch()

        # Return early unless we need to send data.
        if self._state not in {State.ACK, State.ACK_DONE, State.WRITE}:
            return

        if self._state == State.ACK:
            # pull down the data line to start the ack. We want to hold
            # it down until the next clock falling edge.
            if self._ack_data or not self._all_received:
                _switch_to_output(self._sda, value=False)
            self._move_state(State.ACK_DONE)
            return
        if self._state == State.ACK_DONE:
            # The data line has been held between one pair of falling edges - we can
            # let go now if we need to start reading.
            if self._in_write:
                # Note: this will also write out the first bit later in this method.
                self._move_state(State.WRITE)
            else:
                _switch_to_input(self._sda)
                self._move_state(State.READ)

        if self._state == State.WRITE:
            if self._sent_bit_count == 8:
                _switch_to_input(self._sda)
                self._sent_bit_count = 0
                self._move_state(State.WAIT_ACK)
            else:
                bit_value = (self._send_data >> (7 - self._sent_bit_count)) & 0x1
                _switch_to_output(self._sda, value=bit_value == 1)
                self._sent_bit_count += 1

    def _on_clock_rise(self) -> None:
        if self._state not in {State.ADDRESS, State.READ, State.WAIT_ACK}:
            return
        bit_value = 1 if self._sda.net.level == sim.Level.HIGH else 0
        if self._state == State.WAIT_ACK:
            if bit_value:
                # NACK, just reset.
                self._move_state(State.IDLE)
            else:
                # ACK, continue writing.
                self._move_state(State.ACK_DONE)
            return
        self._received = (self._received << 1) | bit_value
        self._bit_count += 1
        if self._bit_count < 8:
            return

        # We've read 8 bits of either address or data sent to us.
        if self._state == State.ADDRESS and self._address != (self._received >> 1):
            # This message isn't for us, reset and start idling.
            self._reset()
            return
        # This message is for us, ack it.
        if self._state == State.ADDRESS:
            self._in_write = self._received & 0x1
        elif self._state == State.READ:
            self._on_byte_read()
        self._bit_count = 0
        self._received = 0
        self._move_state(State.ACK)

    def _on_level_change(self, net: sim.Net) -> None:
        # Handle start/stop events directly.
        if net == self._sda.net and self._scl.net.level == sim.Level.HIGH:
            if net.level == sim.Level.LOW:
                # sda hi->low with scl high
                self._on_start()
            else:
                # sda low->hi with scl high
                self._on_stop()
            return

        # Everything else can be handled as state changes that occur
        # either on the clock rising or falling edge.
        if net == self._scl.net:
            if net.level == sim.Level.HIGH:
                # scl low->high
                self._on_clock_rise()
            else:
                # scl high->low
                self._on_clock_fall()

    def all_received_data(self) -> bytearray:
        return self._all_received
