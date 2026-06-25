# ESP32 NESTR Sensor Node

## Required Arduino Libraries

- WiFi
- HTTPClient
- HX711 by Bogde
- DHT sensor library by Adafruit
- Adafruit Unified Sensor

## Pin Mapping

| Component | ESP32 Pin |
|---|---:|
| DHT22 Data | GPIO 4 |
| HX711 DT/DOUT | GPIO 16 |
| HX711 SCK | GPIO 17 |
| VCC | 3.3V / 5V based on sensor requirement |
| GND | GND |

## Setup

1. Open `esp32_nestr.ino` in Arduino IDE.
2. Install the required libraries.
3. Select ESP32 board and correct COM port.
4. Update Wi-Fi SSID, password, and Raspberry Pi gateway URL.
5. Upload the sketch to ESP32.
6. Open Serial Monitor at 115200 baud.
