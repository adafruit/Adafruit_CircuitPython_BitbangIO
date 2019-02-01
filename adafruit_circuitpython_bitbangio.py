# The MIT License (MIT)
#
# Copyright (c) 2019 Dave Astels for Adafruit Industries
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
`adafruit_circuitpython_bitbangio`
================================================================================

BitBang library for CircuitPython and Python3+Blinka


* Author(s): Dave Astels

Implementation Notes
--------------------

**Hardware:**

.. todo:: Add links to any specific hardware product page(s), or category page(s). Use unordered list & hyperlink rST
   inline format: "* `Link Text <url>`_"

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases

"""

# imports

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_circuitpython_CircuitPython_BitBangIO.git"

import time
import digitalio

class SPI(object):

    def __init__(self, clock=None, MOSI=None, MISO=None):
        if clock is None or MOSI is None or MISO is None:
            return None

        self._clock_pin = digitalio.DigitalInOut(clock)
        self._clock_pin.direction = digitalio.Direction.OUTPUT
        self._clock_pin.value = False

        self._mosi_pin = digitalio.DigitalInOut(MOSI)
        self._mosi_pin.direction = digitalio.Direction.OUTPUT
        self._mosi_pin.value = False

        self._miso_pin = digitalio.DigitalInOut(MISO)
        self._miso_pin.direction = digitalio.Direction.INPUT

        self._baudrate = 0
        self._polarity = 0
        self._phase = 0
        self._bits = 0
        self._spi_sclk_low_time = 0.0

        self.configure()


    def configure(self, baudrate=100000, polarity=0, phase=0, bits=8):
        """Configures the SPI bus. The SPI object must be locked.

        :param int baudrate: the desired clock rate in Hertz. The actual clock rate may be higher or lower
                             due to the granularity of available clock settings.
                            Check the `frequency` attribute for the actual clock rate.
        :param int polarity: the base state of the clock line (0 or 1)
        :param int phase: the edge of the clock that data is captured. First (0)
                          or second (1). Rising or falling depends on clock polarity.
        :param int bits: the number of bits per word
        """
        if polarity != phase:
            raise RuntimeError('Only SPI modes 0 and 3 are supported')
        if bits != 8:
            raise RuntimeError('Only 8-bit words are supported')
        self._baudrate = baudrate
        self._polarity = polarity
        self._phase = phase
        self._bits = bits
        self._spi_sclk_time = max([0.000005, (1 / baudrate) / 2])
        self._clock_pin.value = (polarity == 1)

    @property
    def clock_time(self):
        return self._spi_sclk_low_time

    def try_lock(self):
        """Attempts to grab the SPI lock. Returns True on success.

        :return: True when lock has been grabbed
        """
        return True


    def unlock(self):
        """Releases the SPI lock."""
        pass

    def _leading_edge(self):
        self._clock_pin.value = (self._polarity == 0)


    def _trailing_edge(self):
        self._clock_pin.value = (self._polarity == 1)


    def _transfer_byte(self, tx_byte):
        rx_byte = 0
        bit = 0x80
        for _ in range(0,8):
            if self._phase == 1:
                self._leading_edge()
            self._mosi_pin.value = (tx_byte & bit) != 0
            time.sleep(self._spi_sclk_time)
            if self._phase == 0:
                self._leading_edge()
            if self._phase == 1:
                time.sleep(self._spi_sclk_time)
            if self._miso_pin.value:
                rx_byte |= bit
            if self._phase == 0:
                time.sleep(self._spi_sclk_time)
            self._trailing_edge()
            bit >>= 1
        return rx_byte


    def _transfer(self, buffer_out, buffer_in, out_start=0, out_end=None, in_start=0, in_end=None):
        if out_end is None:
            out_end = len(buffer_out)
        if in_end is None:
            in_end = len(buffer_in)
        if out_start < 0 or out_end < 0 or out_end < out_start:
            return False
        if in_start < 0 or in_end < 0 or in_end < in_start:
            return False
        if (out_end - out_start) != (in_end - in_start):
            return False

        out_index = out_start
        in_index = in_start
        for _ in range(in_start, in_end):
            buffer_in[in_index] = self._transfer_byte(buffer_out[out_index])
            in_index += 1
            out_index += 1
        return True

    def write(self, buffer, start=0, end=None):
        """Write the data contained in ``buffer``. The SPI object must be locked.
        If the buffer is empty, nothing happens.

        :param bytearray buffer: Write out the data in this buffer
        :param int start: Start of the slice of ``buffer`` to write out: ``buffer[start:end]``
        :param int end: End of the slice; this index is not included
        """
        if buffer:
            if end is None:
                end = len(buffer)
            dummy_buffer = bytearray(end - start)
            return self._transfer(buffer, dummy_buffer, start, end)


    def readinto(self, buffer, start=0, end=None, write_value=0):
        """Read into ``buffer`` while writing ``write_value`` for each byte read.
        The SPI object must be locked.
        If the number of bytes to read is 0, nothing happens.

        :param bytearray buffer: Read data into this buffer
        :param int start: Start of the slice of ``buffer`` to read into: ``buffer[start:end]``
        :param int end: End of the slice; this index is not included
        :param int write_value: Value to write while reading. (Usually ignored.)
        """
        if end is None:
            end = len(buffer)
        if start < 0 or end < 0 or end < start:
            return False
        dummy_buffer = bytes([write_value] * (end - start))
        return self._transfer(dummy_buffer, buffer, 0, len(dummy_buffer), start, end)


    def write_readinto(self, buffer_out, buffer_in, out_start=0, out_end=None, in_start=0, in_end=None):
        """Write out the data in ``buffer_out`` while simultaneously reading data into ``buffer_in``.
        The SPI object must be locked.
        The lengths of the slices defined by ``buffer_out[out_start:out_end]`` and ``buffer_in[in_start:in_end]``
        must be equal.
        If buffer slice lengths are both 0, nothing happens.

        :param bytearray buffer_out: Write out the data in this buffer
        :param bytearray buffer_in: Read data into this buffer
        :param int out_start: Start of the slice of buffer_out to write out: ``buffer_out[out_start:out_end]``
        :param int out_end: End of the slice; this index is not included
        :param int in_start: Start of the slice of ``buffer_in`` to read into: ``buffer_in[in_start:in_end]``
        :param int in_end: End of the slice; this index is not included
        """
        return self._transfer(buffer_out, buffer_in, out_start, out_end, in_start, in_end)


    @property
    def frequency(self):
        """The actual SPI bus frequency. This may not match the frequency requested
           due to internal limitations.
        """
        return 1 / self._spi_sclk_low_time


class SPIDevice(object):

    def __init__(self, spi, cs, baudrate=100000, polarity=0, phase=0):
        """
        :param BBSpi spi: The bit banged spi bus object
        :param digitalio.DigitalInOut cs: The chip select pin for this device
        """
        self._spi = spi
        self._cs = digitalio.DigitalInOut(cs)
        self._cs.direction = digitalio.Direction.OUTPUT
        self._cs.value = True
        spi.configure(baudrate=baudrate, polarity=polarity, phase=phase)


    def write(self, buffer, start=0, end=None):
        """Write the data contained in ``buffer``. The SPI object must be locked.
        If the buffer is empty, nothing happens.

        :param bytearray buffer: Write out the data in this buffer
        :param int start: Start of the slice of ``buffer`` to write out: ``buffer[start:end]``
        :param int end: End of the slice; this index is not included
        """
        self._cs.value = False
        time.sleep(self._spi.clock_time)
        self._spi.write(buffer, start=start, end=end)
        time.sleep(self._spi.clock_time)
        self._cs.value = True


    def readinto(self, buffer, start=0, end=None, write_value=0):
        """Read into ``buffer`` while writing ``write_value`` for each byte read.
        The SPI object must be locked.
        If the number of bytes to read is 0, nothing happens.

        :param bytearray buffer: Read data into this buffer
        :param int start: Start of the slice of ``buffer`` to read into: ``buffer[start:end]``
        :param int end: End of the slice; this index is not included
        :param int write_value: Value to write while reading. (Usually ignored.)
        """
        self._cs.value = False
        time.sleep(self._spi.clock_time)
        self._spi.readinto(buffer, start=start, end=end, write_value=write_value)
        time.sleep(self._spi.clock_time)
        self._cs.value = True


    def write_readinto(self, buffer_out, buffer_in, out_start=0, out_end=None, in_start=0, in_end=None):
        """Write out the data in ``buffer_out`` while simultaneously reading data into ``buffer_in``.
        The SPI object must be locked.
        The lengths of the slices defined by ``buffer_out[out_start:out_end]`` and ``buffer_in[in_start:in_end]``
        must be equal.
        If buffer slice lengths are both 0, nothing happens.

        :param bytearray buffer_out: Write out the data in this buffer
        :param bytearray buffer_in: Read data into this buffer
        :param int out_start: Start of the slice of buffer_out to write out: ``buffer_out[out_start:out_end]``
        :param int out_end: End of the slice; this index is not included
        :param int in_start: Start of the slice of ``buffer_in`` to read into: ``buffer_in[in_start:in_end]``
        :param int in_end: End of the slice; this index is not included
        """
        self._cs.value = False
        time.sleep(self._spi.clock_time)
        self._spi.write_readinto(buffer_out, buffer_in, out_start=out_start, out_end=out_end, in_start=in_start, in_end=in_end)
        time.sleep(self._spi.clock_time)
        self._cs.value = True
