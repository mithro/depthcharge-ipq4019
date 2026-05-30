#!/usr/bin/env python3
"""Find any WP/wp-related GPIO on gale's EC."""
import time, serial
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
s = serial.Serial(EC, 115200, timeout=0.3)
s.write(b"\r"); time.sleep(0.2); s.read(8192)
for cmd in [
    "gpioget",      # list all GPIOs
    "gpioget WP",
    "gpioget WP_L",
    "gpioget AP_FLASH_WP",
    "gpioget AP_FLASH_WP_L",
    "gpioget EC_WP_L",
    "gpioget AP_SPI_WP_L",
    "gpioget FLASH_WP",
    "gpioget GPIO_WP_L",
]:
    s.write((cmd + "\r").encode()); time.sleep(0.6)
    out = s.read(16384).decode("latin1", "replace").rstrip()
    print(f"--- {cmd} ---")
    print(out[:3000])
    print()
s.close()
