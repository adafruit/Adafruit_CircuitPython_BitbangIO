import board
import digitalio
import adafruit_bitbangio as bitbangio

SCLK = board.D6
MOSI = board.D17
MISO = board.D18

cs = digitalio.DigitalInOut(board.D5)
cs.switch_to_output(value=True)

spi = bitbangio.SPI(SCLK, MOSI=MOSI, MISO=MISO)
cs.value = 0
spi.write([0xD0])
data = [0x00]
spi.readinto(data)
cs.value = 1
print("Result is {}".format(data))
