# SPDX-FileCopyrightText: 2020 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_bitbangio`
================================================================================

A library for adding bitbang I2C and SPI to CircuitPython without the built-in bitbangio module.
The interface is intended to be the same as bitbangio and therefore there is no bit order or chip
select functionality. If your board supports bitbangio, it is recommended to use that instead
as the timing should be more reliable.

* Author(s): Melissa LeBlanc-Williams

Implementation Notes
--------------------

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases

"""

try:
    from typing import List, Optional, Type
    from typing_extensions import Literal
    from types import TracebackType
    from circuitpython_typing import WriteableBuffer, ReadableBuffer
    from microcontroller import Pin
except ImportError:
    pass

# imports
from time import monotonic
from digitalio import DigitalInOut

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_BitbangIO.git"

MSBFIRST = 0
LSBFIRST = 1


class _BitBangIO:
    """Base class for subclassing only"""

    def __init__(self) -> None:
        self._locked = False

    def try_lock(self) -> bool:
        """Attempt to grab the lock. Return True on success, False if the lock is already taken."""
        if self._locked:
            return False
        self._locked = True
        return True

    def unlock(self) -> None:
        """Release the lock so others may use the resource."""
        if self._locked:
            self._locked = False
        else:
            raise ValueError("Not locked")

    def _check_lock(self) -> Literal[True]:
        if not self._locked:
            raise RuntimeError("First call try_lock()")
        return True

    def __enter__(self) -> "_BitBangIO":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.deinit()

    # pylint: disable=no-self-use
    def deinit(self) -> None:
        """Free any hardware used by the object."""
        return

    # pylint: enable=no-self-use


class I2C(_BitBangIO):
    """Software-based implementation of the I2C protocol over GPIO pins."""

    def __init__(
        self, scl: Pin, sda: Pin, *, frequency: int = 400000, timeout: float = 1
    ) -> None:
        """Initialize bitbang (or software) based I2C.  Must provide the I2C
        clock, and data pin numbers.
        """
        super().__init__()

        # Set pins as outputs/inputs.
        self._scl = DigitalInOut(scl)
        # rpi gpio does not support OPEN_DRAIN, so we have to emulate it
        # by setting the pin to input for high and output 0 for low
        self._scl.switch_to_input()

        # SDA flips between being input and output
        self._sda = DigitalInOut(sda)
        self._sda.switch_to_input()

        self._delay = (1 / frequency) / 2  # half period
        self._timeout = timeout

    def deinit(self) -> None:
        """Free any hardware used by the object."""
        self._sda.deinit()
        self._scl.deinit()

    def _wait(self) -> None:
        end = monotonic() + self._delay  # half period
        while end > monotonic():
            pass

    def scan(self) -> List[int]:
        """Perform an I2C Device Scan"""
        found = []
        if self._check_lock():
            for address in range(0, 0x80):
                if self._probe(address):
                    found.append(address)
        return found

    def writeto(
        self,
        address: int,
        buffer: ReadableBuffer,
        *,
        start: int = 0,
        end: Optional[int] = None,
    ) -> None:
        """Write data from the buffer to an address"""
        if end is None:
            end = len(buffer)
        if self._check_lock():
            self._write(address, buffer[start:end], True)

    def readfrom_into(
        self,
        address: int,
        buffer: WriteableBuffer,
        *,
        start: int = 0,
        end: Optional[int] = None,
    ) -> None:
        """Read data from an address and into the buffer"""
        if end is None:
            end = len(buffer)

        if self._check_lock():
            readin = self._read(address, end - start)
            for i in range(end - start):
                buffer[i + start] = readin[i]

    def writeto_then_readfrom(
        self,
        address: int,
        buffer_out: ReadableBuffer,
        buffer_in: WriteableBuffer,
        *,
        out_start: int = 0,
        out_end: Optional[int] = None,
        in_start: int = 0,
        in_end: Optional[int] = None,
    ) -> None:
        """Write data from buffer_out to an address and then
        read data from an address and into buffer_in
        """
        if out_end is None:
            out_end = len(buffer_out)
        if in_end is None:
            in_end = len(buffer_in)
        if self._check_lock():
            self._write(address, buffer_out[out_start:out_end], False)
            self.readfrom_into(address, buffer_in, start=in_start, end=in_end)

    def _scl_low(self) -> None:
        self._scl.switch_to_output(value=False)

    def _sda_low(self) -> None:
        self._sda.switch_to_output(value=False)

    def _scl_release(self) -> None:
        """Release and let the pullups lift"""
        # Use self._timeout to add clock stretching
        self._scl.switch_to_input()

    def _sda_release(self) -> None:
        """Release and let the pullups lift"""
        # Use self._timeout to add clock stretching
        self._sda.switch_to_input()

    def _start(self) -> None:
        self._sda_release()
        self._scl_release()
        self._wait()
        self._sda_low()
        self._wait()

    def _stop(self) -> None:
        self._scl_low()
        self._wait()
        self._sda_low()
        self._wait()
        self._scl_release()
        self._wait()
        self._sda_release()
        self._wait()

    def _repeated_start(self) -> None:
        self._scl_low()
        self._wait()
        self._sda_release()
        self._wait()
        self._scl_release()
        self._wait()
        self._sda_low()
        self._wait()

    def _write_byte(self, byte: int) -> bool:
        for bit_position in range(8):
            self._scl_low()

            if byte & (0x80 >> bit_position):
                self._sda_release()
            else:
                self._sda_low()
            self._wait()
            self._scl_release()
            self._wait()

        self._scl_low()
        self._sda.switch_to_input()  # SDA may go high, but SCL is low
        self._wait()

        self._scl_release()
        self._wait()
        ack = self._sda.value  # read the ack

        self._scl_low()
        self._sda_release()
        self._wait()

        return not ack

    def _read_byte(self, ack: bool = False) -> int:
        self._scl_low()
        self._wait()
        # sda will already be an input as we are simulating open drain
        data = 0
        for _ in range(8):
            self._scl_release()
            self._wait()
            data = (data << 1) | int(self._sda.value)
            self._scl_low()
            self._wait()

        if ack:
            self._sda_low()
        # else sda will already be in release (open drain) mode

        self._wait()
        self._scl_release()
        self._wait()
        self._scl_low()
        self._sda_release()

        return data & 0xFF

    def _probe(self, address: int) -> bool:
        self._start()
        ok = self._write_byte(address << 1)
        self._stop()
        return ok > 0

    def _write(self, address: int, buffer: ReadableBuffer, transmit_stop: bool) -> None:
        self._start()
        if not self._write_byte(address << 1):
            # raise RuntimeError("Device not responding at 0x{:02X}".format(address))
            raise RuntimeError(f"Device not responding at 0x{address:02X}")
        for byte in buffer:
            self._write_byte(byte)
        if transmit_stop:
            self._stop()

    def _read(self, address: int, length: int) -> bytearray:
        self._start()
        if not self._write_byte(address << 1 | 1):
            # raise RuntimeError("Device not responding at 0x{:02X}".format(address))
            raise RuntimeError(f"Device not responding at 0x{address:02X}")
        buffer = bytearray(length)
        for byte_position in range(length):
            buffer[byte_position] = self._read_byte(ack=byte_position != length - 1)
        self._stop()
        return buffer


class SPI(_BitBangIO):
    """Software-based implementation of the SPI protocol over GPIO pins."""

    def __init__(
        self, clock: Pin, MOSI: Optional[Pin] = None, MISO: Optional[Pin] = None
    ) -> None:
        """Initialize bit bang (or software) based SPI.  Must provide the SPI
        clock, and optionally MOSI and MISO pin numbers. If MOSI is set to None
        then writes will be disabled and fail with an error, likewise for MISO
        reads will be disabled.
        """
        super().__init__()

        while self.try_lock():
            pass

        self._mosi = None
        self._miso = None

        # Set pins as outputs/inputs.
        self._sclk = DigitalInOut(clock)
        self._sclk.switch_to_output()

        if MOSI is not None:
            self._mosi = DigitalInOut(MOSI)
            self._mosi.switch_to_output()

        if MISO is not None:
            self._miso = DigitalInOut(MISO)
            self._miso.switch_to_input()

        self.configure()
        self.unlock()

    def deinit(self) -> None:
        """Free any hardware used by the object."""
        self._sclk.deinit()
        if self._miso:
            self._miso.deinit()
        if self._mosi:
            self._mosi.deinit()

    def configure(
        self,
        *,
        baudrate: int = 100000,
        polarity: Literal[0, 1] = 0,
        phase: Literal[0, 1] = 0,
        bits: int = 8,
    ) -> None:
        """Configures the SPI bus. Only valid when locked."""
        if self._check_lock():
            if not isinstance(baudrate, int):
                raise ValueError("baudrate must be an integer")
            if not isinstance(bits, int):
                raise ValueError("bits must be an integer")
            if bits < 1 or bits > 8:
                raise ValueError("bits must be in the range of 1-8")
            if polarity not in (0, 1):
                raise ValueError("polarity must be either 0 or 1")
            if phase not in (0, 1):
                raise ValueError("phase must be either 0 or 1")
            self._baudrate = baudrate
            self._polarity = polarity
            self._phase = phase
            self._bits = bits
            self._half_period = (1 / self._baudrate) / 2  # 50% Duty Cyle delay

            # Initialize the clock to the idle state. This is important to
            # guarantee that the clock is at a known (idle) state before
            # any read/write operations.
            self._sclk.value = self._polarity

    def _wait(self, start: Optional[int] = None) -> float:
        """Wait for up to one half cycle"""
        while (start + self._half_period) > monotonic():
            pass
        return monotonic()  # Return current time

    def _should_write(self, to_active: Literal[0, 1]) -> bool:
        """Return true if a bit should be written on the given clock transition."""
        # phase 0: write when active is 0
        # phase 1: write when active is 1
        return self._phase == to_active

    def _should_read(self, to_active: Literal[0, 1]) -> bool:
        """Return true if a bit should be read on the given clock transition."""
        # phase 0: read when active is 1
        # phase 1: read when active is 0
        # Data is read on the idle->active transition only when the phase is 1
        return self._phase == 1 - to_active

    def write(
        self, buffer: ReadableBuffer, start: int = 0, end: Optional[int] = None
    ) -> None:
        """Write the data contained in buf. Requires the SPI being locked.
        If the buffer is empty, nothing happens.
        """
        # Fail MOSI is not specified.
        if self._mosi is None:
            raise RuntimeError("Write attempted with no MOSI pin specified.")
        if end is None:
            end = len(buffer)

        if self._check_lock():
            start_time = monotonic()
            # Note: when we come here, our clock must always be its idle state.
            for byte in buffer[start:end]:
                for bit_position in range(self._bits):
                    bit_value = byte & 0x80 >> bit_position
                    # clock: idle, or has made an active->idle transition.
                    if self._should_write(to_active=0):
                        self._mosi.value = bit_value
                    # clock: wait in idle for half a period
                    start_time = self._wait(start_time)
                    # clock: idle->active
                    self._sclk.value = not self._polarity
                    if self._should_write(to_active=1):
                        self._mosi.value = bit_value
                    # clock: wait in active for half a period
                    start_time = self._wait(start_time)
                    # clock: active->idle
                    self._sclk.value = self._polarity
            # clock: stay in idle for the last active->idle transition
            # to settle.
            start_time = self._wait(start_time)

    # pylint: disable=too-many-branches
    def readinto(
        self,
        buffer: WriteableBuffer,
        start: int = 0,
        end: Optional[int] = None,
        write_value: int = 0,
    ) -> None:
        """Read into the buffer specified by buf while writing zeroes. Requires the SPI being
        locked. If the number of bytes to read is 0, nothing happens.
        """
        if self._miso is None:
            raise RuntimeError("Read attempted with no MISO pin specified.")
        if end is None:
            end = len(buffer)

        if self._check_lock():
            start_time = monotonic()
            for byte_position, _ in enumerate(buffer[start:end]):
                for bit_position in range(self._bits):
                    bit_mask = 0x80 >> bit_position
                    bit_value = write_value & 0x80 >> bit_position
                    # clock: idle, or has made an active->idle transition.
                    if self._should_write(to_active=0):
                        if self._mosi is not None:
                            self._mosi.value = bit_value
                    # clock: wait half a period.
                    start_time = self._wait(start_time)
                    # clock: idle->active
                    self._sclk.value = not self._polarity
                    if self._should_read(to_active=1):
                        if self._miso.value:
                            # Set bit to 1 at appropriate location.
                            buffer[byte_position] |= bit_mask
                        else:
                            # Set bit to 0 at appropriate location.
                            buffer[byte_position] &= ~bit_mask
                    if self._should_write(to_active=1):
                        if self._mosi is not None:
                            self._mosi.value = bit_value
                    # clock: wait half a period
                    start_time = self._wait(start_time)
                    # Clock: active->idle
                    self._sclk.value = self._polarity
                    if self._should_read(to_active=0):
                        if self._miso.value:
                            # Set bit to 1 at appropriate location.
                            buffer[byte_position] |= bit_mask
                        else:
                            # Set bit to 0 at appropriate location.
                            buffer[byte_position] &= ~bit_mask

            # clock: wait another half period for the last transition.
            start_time = self._wait(start_time)

    def write_readinto(
        self,
        buffer_out: ReadableBuffer,
        buffer_in: WriteableBuffer,
        *,
        out_start: int = 0,
        out_end: Optional[int] = None,
        in_start: int = 0,
        in_end: Optional[int] = None,
    ) -> None:
        """Write out the data in buffer_out while simultaneously reading data into buffer_in.
        The lengths of the slices defined by buffer_out[out_start:out_end] and
        buffer_in[in_start:in_end] must be equal. If buffer slice lengths are
        both 0, nothing happens.
        """
        if self._mosi is None:
            raise RuntimeError("Write attempted with no MOSI pin specified.")
        if self._miso is None:
            raise RuntimeError("Read attempted with no MISO pin specified.")
        if out_end is None:
            out_end = len(buffer_out)
        if in_end is None:
            in_end = len(buffer_in)
        if len(buffer_out[out_start:out_end]) != len(buffer_in[in_start:in_end]):
            raise RuntimeError("Buffer slices must be equal length")

        if self._check_lock():
            start_time = monotonic()
            for byte_position, _ in enumerate(buffer_out[out_start:out_end]):
                for bit_position in range(self._bits):
                    bit_mask = 0x80 >> bit_position
                    bit_value = (
                        buffer_out[byte_position + out_start] & 0x80 >> bit_position
                    )
                    in_byte_position = byte_position + in_start
                    # clock: idle, or has made an active->idle transition.
                    if self._should_write(to_active=0):
                        self._mosi.value = bit_value
                    # clock: wait half a period.
                    start_time = self._wait(start_time)
                    # clock: idle->active
                    self._sclk.value = not self._polarity
                    if self._should_read(to_active=1):
                        if self._miso.value:
                            # Set bit to 1 at appropriate location.
                            buffer_in[in_byte_position] |= bit_mask
                        else:
                            buffer_in[in_byte_position] &= ~bit_mask
                    if self._should_write(to_active=1):
                        self._mosi.value = bit_value
                    # clock: wait half a period
                    start_time = self._wait(start_time)
                    # Clock: active->idle
                    self._sclk.value = self._polarity
                    if self._should_read(to_active=0):
                        if self._miso.value:
                            # Set bit to 1 at appropriate location.
                            buffer_in[in_byte_position] |= bit_mask
                        else:
                            buffer_in[in_byte_position] &= ~bit_mask

            # clock: wait another half period for the last transition.
            start_time = self._wait(start_time)

    # pylint: enable=too-many-branches

    @property
    def frequency(self) -> int:
        """Return the currently configured baud rate"""
        return self._baudrate
