# The MIT License (MIT)
#
# Copyright (c) 2020 Melissa LeBlanc-Williams for Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
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

# imports
from time import monotonic
from digitalio import DigitalInOut

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_BitbangIO.git"

MSBFIRST = 0
LSBFIRST = 1


class _BitBangIO:
    """Base class for subclassing only"""

    def __init__(self):
        self._locked = False

    def try_lock(self):
        """Attempt to grab the lock. Return True on success, False if the lock is already taken."""
        if self._locked:
            return False
        self._locked = True
        return True

    def unlock(self):
        """Release the lock so others may use the resource."""
        if self._locked:
            self._locked = False
        else:
            raise ValueError("Not locked")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.deinit()

    # pylint: disable=no-self-use
    def deinit(self):
        """Free any hardware used by the object."""
        return

    # pylint: enable=no-self-use


class SPI(_BitBangIO):
    """Software-based implementation of the SPI protocol over GPIO pins."""

    def __init__(self, clock, MOSI=None, MISO=None):
        """Initialize bit bang (or software) based SPI.  Must provide the SPI
        clock, and optionally MOSI and MISO pin numbers. If MOSI is set to None
        then writes will be disabled and fail with an error, likewise for MISO
        reads will be disabled.
        """
        super().__init__()

        while self.try_lock():
            pass

        self.configure()
        self.unlock()

        # Set pins as outputs/inputs.
        self._sclk = DigitalInOut(clock)
        self._sclk.switch_to_output()

        if MOSI is not None:
            self._mosi = DigitalInOut(MOSI)
            self._mosi.switch_to_output()

        if MISO is not None:
            self._miso = DigitalInOut(MISO)
            self._miso.switch_to_input()

    def configure(self, *, baudrate=100000, polarity=0, phase=0, bits=8):
        """Configures the SPI bus. Only valid when locked."""
        if self._locked:
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

        else:
            raise RuntimeError("First call try_lock()")

    def _wait(self, start=None):
        """Wait for up to one half cycle"""
        while (start + self._half_period) > monotonic():
            pass
        return monotonic()  # Return current time

    def write(self, buffer, start=0, end=None):
        """Write the data contained in buf. Requires the SPI being locked.
        If the buffer is empty, nothing happens.
        """
        # Fail MOSI is not specified.
        if self._mosi is None:
            raise RuntimeError("Write attempted with no MOSI pin specified.")
        if end is None:
            end = len(buffer)

        start_time = monotonic()
        for byte in buffer[start:end]:
            for bit_position in range(self._bits):
                bit_value = byte & 0x80 >> bit_position
                # Set clock to base
                if not self._phase:  # Mode 0, 2
                    self._mosi.value = bit_value
                self._sclk.value = self._polarity
                start_time = self._wait(start_time)

                # Flip clock off base
                if self._phase:  # Mode 1, 3
                    self._mosi.value = bit_value
                self._sclk.value = not self._polarity
                start_time = self._wait(start_time)

        # Return pins to base positions
        self._mosi.value = 0
        self._sclk.value = self._polarity

    def readinto(self, buffer, start=0, end=None, write_value=0):
        """Read into the buffer specified by buf while writing zeroes. Requires the SPI being
        locked. If the number of bytes to read is 0, nothing happens.
        """
        if self._miso is None:
            raise RuntimeError("Read attempted with no MISO pin specified.")
        if end is None:
            end = len(buffer)
        start_time = monotonic()
        for byte_position, _ in enumerate(buffer[start:end]):
            for bit_position in range(self._bits):
                bit_mask = 0x80 >> bit_position
                bit_value = write_value & 0x80 >> bit_position
                # Return clock to base
                self._sclk.value = self._polarity
                start_time = self._wait(start_time)
                # Handle read on leading edge of clock.
                if not self._phase:  # Mode 0, 2
                    if self._mosi is not None:
                        self._mosi.value = bit_value
                    if self._miso.value:
                        # Set bit to 1 at appropriate location.
                        buffer[byte_position] |= bit_mask
                    else:
                        # Set bit to 0 at appropriate location.
                        buffer[byte_position] &= ~bit_mask
                # Flip clock off base
                self._sclk.value = not self._polarity
                start_time = self._wait(start_time)
                # Handle read on trailing edge of clock.
                if self._phase:  # Mode 1, 3
                    if self._mosi is not None:
                        self._mosi.value = bit_value
                    if self._miso.value:
                        # Set bit to 1 at appropriate location.
                        buffer[byte_position] |= bit_mask
                    else:
                        # Set bit to 0 at appropriate location.
                        buffer[byte_position] &= ~bit_mask

        # Return pins to base positions
        self._mosi.value = 0
        self._sclk.value = self._polarity

    # pylint: disable=too-many-branches
    def write_readinto(
        self,
        buffer_out,
        buffer_in,
        *,
        out_start=0,
        out_end=None,
        in_start=0,
        in_end=None
    ):
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

        start_time = monotonic()
        for byte_position, _ in enumerate(buffer_out[out_start:out_end]):
            for bit_position in range(self._bits):
                bit_mask = 0x80 >> bit_position
                bit_value = buffer_out[byte_position + out_start] & 0x80 >> bit_position
                in_byte_position = byte_position + in_start
                # Return clock to 0
                self._sclk.value = self._polarity
                start_time = self._wait(start_time)
                # Handle read on leading edge of clock.
                if not self._phase:  # Mode 0, 2
                    self._mosi.value = bit_value
                    if self._miso.value:
                        # Set bit to 1 at appropriate location.
                        buffer_in[in_byte_position] |= bit_mask
                    else:
                        # Set bit to 0 at appropriate location.
                        buffer_in[in_byte_position] &= ~bit_mask
                # Flip clock off base
                self._sclk.value = not self._polarity
                start_time = self._wait(start_time)
                # Handle read on trailing edge of clock.
                if self._phase:  # Mode 1, 3
                    self._mosi.value = bit_value
                    if self._miso.value:
                        # Set bit to 1 at appropriate location.
                        buffer_in[in_byte_position] |= bit_mask
                    else:
                        # Set bit to 0 at appropriate location.
                        buffer_in[in_byte_position] &= ~bit_mask

        # Return pins to base positions
        self._mosi.value = 0
        self._sclk.value = self._polarity

    # pylint: enable=too-many-branches

    @property
    def frequency(self):
        """Return the currently configured baud rate"""
        return self._baudrate
