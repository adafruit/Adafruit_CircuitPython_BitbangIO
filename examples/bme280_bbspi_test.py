import board
from adafruit_circuitpython_bitbangio import SPI
from bme280_bbspi import BME280

print("Testing BME280 BBSPI interface")

# cs = 26
spi = SPI(clock=board.D16, MOSI=board.D21, MISO=board.D20)
sensor = BME280(spi, board.D26)

print('Temperature: {0:.2f}\nHumidity: {1:.2f}\nPressure: {2:.2f}\n'.format(sensor.temperature, sensor.humidity, sensor.pressure))
