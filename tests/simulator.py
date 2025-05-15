# SPDX-FileCopyrightText: KB Sriram
# SPDX-License-Identifier: MIT
"""Simple logic level simulator to test I2C/SPI interactions."""

import dataclasses
import enum
import functools
import time
from typing import Any, Callable, List, Literal, Optional, Sequence

import digitalio


@enum.unique
class Mode(enum.Enum):
    IN = "IN"
    OUT = "OUT"


@enum.unique
class Level(enum.Enum):
    Z = "Z"
    LOW = "LOW"
    HIGH = "HIGH"


@enum.unique
class Pull(enum.Enum):
    NONE = "NONE"
    UP = "UP"
    DOWN = "DOWN"


def _level_to_vcd(level: Level) -> str:
    """Converts a level to a VCD understandable mnemonic."""
    if level == Level.Z:
        return "Z"
    if level == Level.HIGH:
        return "1"
    return "0"


@dataclasses.dataclass(frozen=True)
class Change:
    """Container to record simulation events."""

    net_name: str
    time_us: int
    level: Level


class Engine:
    """Manages the overall simulation state and clock."""

    def __init__(self) -> None:
        self._start_us = int(time.monotonic() * 1e6)
        self._nets: List["Net"] = []

    def reset(self) -> None:
        """Clears out all existing state and resets the simulation."""
        self._start_us = int(time.monotonic() * 1e6)
        self._nets = []

    def _find_net_by_pin_id(self, pin_id: str) -> Optional["Net"]:
        """Returns a net (if any) that has a pin with the given id."""
        for net in self._nets:
            if net.contains_pin_id(pin_id):
                return net
        return None

    def create_net(
        self, net_id: str, default_level: Level = Level.Z, monitor: bool = False
    ) -> "Net":
        """Creates a new net with the given name. Monitored nets are also traced."""
        net = Net(net_id, default_level=default_level, monitor=monitor)
        self._nets.append(net)
        return net

    def change_history(self) -> Sequence[Change]:
        """Returns an ordered history of all events in monitored nets."""
        monitored_nets = [net for net in self._nets if net.history]
        combined: List[Change] = []
        for net in monitored_nets:
            if net.history:
                for time_us, level in net.history:
                    combined.append(Change(net.name, time_us, level))
        combined.sort(key=lambda v: v.time_us)
        return combined

    def write_vcd(self, path: str) -> None:
        """Writes monitored nets to the provided path as a VCD file."""
        with open(path, "w") as vcdfile:
            vcdfile.write("$version pytest output $end\n")
            vcdfile.write("$timescale 1 us $end\n")
            vcdfile.write("$scope module top $end\n")
            monitored_nets = [net for net in self._nets if net.history]
            for net in monitored_nets:
                vcdfile.write(f"$var wire 1 {net.name} {net.name} $end\n")
            vcdfile.write("$upscope $end\n")
            vcdfile.write("$enddefinitions $end\n")
            combined = self.change_history()
            # History starts when the engine is first reset or initialized.
            vcdfile.write(f"#{self._start_us}\n")
            last_us = self._start_us
            for change in combined:
                if change.time_us != last_us:
                    vcdfile.write(f"#{change.time_us}\n")
                    last_us = change.time_us
                vcdfile.write(f"{_level_to_vcd(change.level)}{change.net_name}\n")


# module global/singleton
engine = Engine()


class FakePin:
    """Test double for a microcontroller pin used in tests."""

    IN = Mode.IN
    OUT = Mode.OUT
    PULL_NONE = Pull.NONE
    PULL_UP = Pull.UP
    PULL_DOWN = Pull.DOWN

    def __init__(self, pin_id: str, net: Optional["Net"] = None):
        self.id = pin_id
        self.mode: Optional[Mode] = None
        self.pull: Optional[Pull] = None
        self.level: Level = Level.Z
        if net:
            # Created directly by the test.
            if engine._find_net_by_pin_id(pin_id):
                raise ValueError(f"{pin_id} has already been created.")
            self.net = net
        else:
            # Created by the library by duplicating an existing id.
            net = engine._find_net_by_pin_id(pin_id)
            if not net:
                raise ValueError(f"Unexpected pin without a net: {pin_id}")
            self.net = net
            self.id = f"{self.id}_dup"
        self.net.add_pin(self)

    def init(self, mode: Mode = Mode.IN, pull: Optional[Pull] = None) -> None:
        if mode != self.mode or pull != self.pull:
            self.mode = mode
            self.pull = pull
            self.net.update()

    def value(self, val: Optional[Literal[0, 1]] = None) -> Optional[Literal[0, 1]]:
        """Set or return the pin Value"""
        if val is None:
            if self.mode != Mode.IN:
                raise ValueError(f"{self.id}: is not an input")
            level = self.net.level
            if level is None:
                # Nothing is actively driving the line - we assume that during
                # testing, this is an error either in the test setup, or
                # something is asking for a value in an uninitialized state.
                raise ValueError(f"{self.id}: value read but nothing is driving the net.")
            return 1 if level == Level.HIGH else 0
        if val in {0, 1}:
            if self.mode != Mode.OUT:
                raise ValueError(f"{self.id}: is not an output")
            nlevel = Level.HIGH if val else Level.LOW
            if nlevel != self.level:
                self.level = nlevel
                self.net.update()
            return None
        raise RuntimeError(f"{self.id}: Invalid value {val} set on pin.")


class Net:
    """A set of pins connected to each other."""

    def __init__(
        self,
        name: str,
        default_level: Level = Level.Z,
        monitor: bool = False,
    ) -> None:
        self.name = name
        self._pins: List[FakePin] = []
        self._default_level = default_level
        self.level = default_level
        self._triggers: List[Callable[["Net"], None]] = []
        self.history = [(engine._start_us, default_level)] if monitor else None

    def update(self) -> None:
        """Resolves the state of this net based on all pins connected to it."""
        result = Level.Z
        # Try to resolve the state of this net by looking at the pin levels
        # for all output pins.
        for pin in self._pins:
            if pin.mode != Mode.OUT:
                continue
            if pin.level == result:
                continue
            if result == Level.Z:
                # This pin is now driving the net.
                result = pin.level
                continue
            # There are conflicting pins!
            raise ValueError(
                f"Conflicting pins on {self.name}: "
                f"{pin.id} is {pin.level}, "
                f" but net was already at {result}"
            )
        # Finally, use any default net state if one was provided. (e.g. a pull-up net.)
        result = self._default_level if result == Level.Z else result

        if result != self.level:
            # Also record a state change if we're being monitored.
            if self.history:
                event_us = int(time.monotonic() * 1e6)
                self.history.append((event_us, result))
            self.level = result
            for trigger in self._triggers:
                trigger(self)

    def add_pin(self, pin: FakePin) -> None:
        self._pins.append(pin)

    def on_level_change(self, trigger: Callable[["Net"], None]) -> None:
        """Calls the trigger whenever the net's level changes."""
        self._triggers.append(trigger)

    def contains_pin_id(self, pin_id: str) -> bool:
        """Returns True if the net has a pin with the given id."""
        for pin in self._pins:
            if pin.id == pin_id:
                return True
        return False


def stub(method: Callable) -> Callable:
    """Decorator to safely insert and remove doubles within tests."""

    @functools.wraps(method)
    def wrapper(*args: Any, **kwds: Any) -> Any:
        # First save any objects we're going to replace with a double.
        pin_module = digitalio.Pin if hasattr(digitalio, "Pin") else None
        try:
            digitalio.Pin = FakePin
            return method(*args, **kwds)
        finally:
            # Replace the saved objects after the test runs.
            if pin_module:
                digitalio.Pin = pin_module

    return wrapper
