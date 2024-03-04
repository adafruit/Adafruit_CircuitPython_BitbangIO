..
  SPDX-FileCopyrightText: KB Sriram
  SPDX-License-Identifier: MIT
..

Bitbangio Tests
===============

These tests run under CPython, and are intended to verify that the
library passes some sanity checks, using a lightweight simulator as
the target device.

These tests run automatically from the standard `circuitpython github
workflow <wf_>`_. To run them manually, first install these packages
if necessary::

  $ pip3 install pytest

Then ensure you're in the *root* directory of the repository and run
the following command::

  $ python -m pytest

Notes on the simulator
======================

`simulator.py` implements a small logic level simulator and a few test
doubles so the library can run under CPython.

The `Engine` class is used as a singleton in the module to co-ordinate
the simulation.

A `Net` holds a list of `FakePins` that are connected together. It
also resolves the overall logic level of the net when a `FakePin` is
updated. It can optionally hold a history of logic level changes,
which may be useful for testing some timing expectations, or export
them as a VCD file for `Pulseview <pv_>`_. Test code can also register
listeners on a `Net` when the net's level changes, so it can simulate
device behavior.

A `FakePin` is a test double for the CircuitPython `Pin` class, and
implements all the functionality so it behaves appropriately in
CPython.

A simulated device can create a `FakePin` for each of its terminals,
and connect them to one or more `Net` instances. It can listen for
level changes on the `Net`, and bitbang the `FakePin` to simulate
behavior. `simulated_spi_device.py` implements a peripheral device
that writes a constant value onto an SPI bus.


.. _wf: https://github.com/adafruit/workflows-circuitpython-libs/blob/6e1562eaabced4db1bd91173b698b1cc1dfd35ab/build/action.yml#L78-L84
.. _pv: https://sigrok.org/wiki/PulseView
