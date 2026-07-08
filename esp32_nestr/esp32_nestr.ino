/*
  NESTR ESP32 Sensor Node
  AIoT Smart Stingless Beehive Intelligence System

  Function:
  - Reads hive weight using HX711 + load cell.
  - Reads temperature and humidity using DHT22.
  - Sends sensor readings to Raspberry Pi Flask Gateway.

  Prototype note:
  - Calibration factor must be adjusted based on the actual load cell setup.
  - Sensor thresholds and harvest readiness are handled at the gateway layer.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include "HX711.h"
#include "DHT.h"

// ==============================
// Wi-Fi and gateway configuration
// ==============================
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* GATEWAY_URL = "http://192.168.1.100:5000/api/hive-data";

// Must match API_KEY configured on the gateway. Leave empty if gateway auth is disabled.
const char* GATEWAY_API_KEY = "";

// ==============================
// Device configuration
// ==============================
const char* DEVICE_ID = "NESTR-HIVE-001";

// ==============================
// Sensor pin configuration
// ==============================
#define DHT_PIN 4
#define DHT_TYPE DHT22
#define HX711_DT 16
#define HX711_SCK 17

DHT dht(DHT_PIN, DHT_TYPE);
HX711 scale;

// Adjust this value after calibration.
float calibrationFactor = -7050.0;

// Reading interval in milliseconds.
const unsigned long READING_INTERVAL = 10000;
unsigned long lastReadingTime = 0;

void connectToWiFi() {
  Serial.print("Connecting to Wi-Fi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retryCount = 0;
  while (WiFi.status() != WL_CONNECTED && retryCount < 30) {
    delay(500);
    Serial.print(".");
    retryCount++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi connected.");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWi-Fi connection failed. Restarting connection attempt later.");
  }
}

float readWeightKg() {
  if (!scale.is_ready()) {
    Serial.println("HX711 is not ready.");
    return -1;
  }

  float weightKg = scale.get_units(10);
  if (weightKg < 0) {
    weightKg = 0;
  }
  return weightKg;
}

bool sendDataToGateway(float weightKg, float temperatureC, float humidityPercent) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected. Reconnecting...");
    connectToWiFi();
    return false;
  }

  HTTPClient http;
  http.begin(GATEWAY_URL);
  http.setConnectTimeout(5000);
  http.setTimeout(5000);
  http.addHeader("Content-Type", "application/json");
  if (strlen(GATEWAY_API_KEY) > 0) {
    http.addHeader("X-API-Key", GATEWAY_API_KEY);
  }

  String payload = "{";
  payload += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  payload += "\"weight_kg\":" + String(weightKg, 2) + ",";
  payload += "\"temperature_c\":" + String(temperatureC, 2) + ",";
  payload += "\"humidity_percent\":" + String(humidityPercent, 2);
  payload += "}";

  Serial.println("Sending payload:");
  Serial.println(payload);

  int httpResponseCode = http.POST(payload);
  String response = http.getString();

  Serial.print("HTTP Response Code: ");
  Serial.println(httpResponseCode);
  Serial.println(response);

  http.end();
  return httpResponseCode >= 200 && httpResponseCode < 300;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting NESTR ESP32 Sensor Node...");

  dht.begin();
  scale.begin(HX711_DT, HX711_SCK);
  scale.set_scale(calibrationFactor);
  scale.tare();

  connectToWiFi();
}

void loop() {
  unsigned long currentTime = millis();

  if (currentTime - lastReadingTime >= READING_INTERVAL) {
    lastReadingTime = currentTime;

    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();
    float weight = readWeightKg();

    if (isnan(humidity) || isnan(temperature)) {
      Serial.println("Failed to read from DHT sensor.");
      return;
    }

    if (weight < 0) {
      Serial.println("Invalid weight reading. Data not sent.");
      return;
    }

    Serial.println("===== NESTR Sensor Reading =====");
    Serial.print("Weight: ");
    Serial.print(weight);
    Serial.println(" kg");
    Serial.print("Temperature: ");
    Serial.print(temperature);
    Serial.println(" °C");
    Serial.print("Humidity: ");
    Serial.print(humidity);
    Serial.println(" %");

    bool sent = sendDataToGateway(weight, temperature, humidity);
    Serial.println(sent ? "Data sent successfully." : "Data sending failed.");
  }
}
