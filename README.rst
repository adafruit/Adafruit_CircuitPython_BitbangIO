Introduction
============

.. image:: https://readthedocs.org/projects/adafruit-circuitpython-bitbangio/badge/?version=latest
    :target: https://docs.circuitpython.org/projects/bitbangio/en/latest/
    :alt: Documentation Status

.. image:: https://img.shields.io/discord/327254708534116352.svg
    :target: https://adafru.it/discord
    :alt: Discord

.. image:: https://github.com/adafruit/Adafruit_CircuitPython_BitbangIO/workflows/Build%20CI/badge.svg
    :target: https://github.com/adafruit/Adafruit_CircuitPython_BitbangIO/actions
    :alt: Build Status

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Code Style: Black

A library for adding bitbang I2C and SPI to CircuitPython without the built-in bitbangio module.
The interface is intended to be the same as bitbangio and therefore there is no bit order or chip
select functionality. If your board supports bitbangio, it is recommended to use that instead
as the timing should be more reliable.


Dependencies
=============
This driver depends on:

* `Adafruit CircuitPython <https://github.com/adafruit/circuitpython>`_

Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://circuitpython.org/libraries>`_.

Installing from PyPI
=====================
On supported GNU/Linux systems like the Raspberry Pi, you can install the driver locally `from
PyPI <https://pypi.org/project/adafruit-circuitpython-bitbangio/>`_. To install for current user:

.. code-block:: shell

    pip3 install adafruit-circuitpython-bitbangio

To install system-wide (this may be required in some cases):

.. code-block:: shell

    sudo pip3 install adafruit-circuitpython-bitbangio

To install in a virtual environment in your current project:

.. code-block:: shell

    mkdir project-name && cd project-name
    python3 -m venv .env
    source .env/bin/activate
    pip3 install adafruit-circuitpython-bitbangio

Usage Example
=============

.. code-block:: python

    """
    This example is for demonstrating how to retrieving the
    board ID from a BME280, which is stored in register 0xD0.
    It should return a result of [96]
    """

    import board
    import digitalio
    import adafruit_bitbangio as bitbangio

    # Change these to the actual connections
    SCLK_PIN = board.D6
    MOSI_PIN = board.D17
    MISO_PIN = board.D18
    CS_PIN = board.D5

    cs = digitalio.DigitalInOut(CS_PIN)
    cs.switch_to_output(value=True)

    spi = bitbangio.SPI(SCLK_PIN, MOSI=MOSI_PIN, MISO=MISO_PIN)
    cs.value = 0
    while not spi.try_lock():
        pass
    spi.write([0xD0])
    data = [0x00]
    spi.readinto(data)
    spi.unlock()
    cs.value = 1
    print("Result is {}".format(data))

Documentation
=============

API documentation for this library can be found on `Read the Docs <https://docs.circuitpython.org/projects/bitbangio/en/latest/>`_.

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/adafruit/Adafruit_CircuitPython_BitbangIO/blob/main/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.

Documentation
=============

For information on building library documentation, please check out `this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.
