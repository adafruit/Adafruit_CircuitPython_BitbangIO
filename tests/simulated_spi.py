# SPDX-FileCopyrightText: KB Sriram
# SPDX-License-Identifier: MIT
"""Implementation of testable SPI devices."""

import dataclasses

import simulator as sim


@dataclasses.dataclass(frozen=True)
class SpiBus:
    enable: sim.Net
    clock: sim.Net
    copi: sim.Net
    cipo: sim.Net


class Constant:
    """Device that always writes a constant."""

    def __init__(self, data: bytearray, bus: SpiBus, polarity: int, phase: int) -> None:
        # convert to binary string array of bits for convenience
        datalen = 8 * len(data)
        self._data = f"{int.from_bytes(data, 'big'):0{datalen}b}"
        self._bit_position = 0
        self._clock = sim.FakePin("const_clock_pin", bus.clock)
        self._last_clock_level = bus.clock.level
        self._cipo = sim.FakePin("const_cipo_pin", bus.cipo)
        self._enable = sim.FakePin("const_enable_pin", bus.enable)
        self._cipo.init(sim.Mode.OUT)
        self._phase = phase
        self._polarity = sim.Level.HIGH if polarity else sim.Level.LOW
        self._enabled = False
        bus.clock.on_level_change(self._on_level_change)
        bus.enable.on_level_change(self._on_level_change)

    def write_bit(self) -> None:
        """Writes the next bit to the cipo net."""
        if self._bit_position >= len(self._data):
            # Just write a zero
            self._cipo.value(0)
            return
        self._cipo.value(int(self._data[self._bit_position]))
        self._bit_position += 1

    def _on_level_change(self, net: sim.Net) -> None:
        if net == self._enable.net:
            # Assumes enable is active high.
            self._enabled = net.level == sim.Level.HIGH
            if self._enabled:
                self._bit_position = 0
                if self._phase == 0:
                    # Write on enable or idle->active
                    self.write_bit()
            return
        if not self._enabled:
            return
        if net != self._clock.net:
            return
        cur_clock_level = net.level
        if cur_clock_level == self._last_clock_level:
            return
        active = 0 if cur_clock_level == self._polarity else 1
        if self._phase == active:
            self.write_bit()
        self._last_clock_level = cur_clock_level
