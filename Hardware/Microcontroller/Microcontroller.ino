/*
 * PhotonVHealth - Solar Panel Efficiency Monitoring System
 * ESP32 Microcontroller Prototyping
*/

#include <Wire.h>
#include <Adafruit_INA219.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiManager.h>
#include <ArduinoJson.h>
#include <DallasTemperature.h>
#include <OneWire.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>

WiFiClientSecure client;
Preferences pref;

#define ONE_WIRE_BUS 4
Adafruit_INA219 ina219;
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensor(&oneWire);

const int lightPin = 34;

float lightVal = 0;
float tempVal = 0;
float powerVal = 0;
float voltageVal = 0;
float efficiency = 0;
float adjustedLight = 0;
float percentageLight = 0;
float health = 0;

float baselinePower = 0;
float baselineLight = 0;

float previousLight = 0;
float previousPower = 0;
float filteredTemp = 0;

unsigned long lastOverheatAlert = 0;
unsigned long lastDustAlert = 0;
unsigned long lastShadeAlert = 0;
const unsigned long alertCooldown = 60000;

unsigned long lastDataSend = 0;
unsigned long lastCommandCheck = 0;
const unsigned long dataInterval = 7000;
const unsigned long commandInterval = 31000;

String deviceId = "";
String apiKey = "";

float smooth_light() {
  float sum = 0;
  for (int i = 0; i < 50; i++) {
    sum += analogRead(lightPin);
  }
  return sum / 50.0;
}

float read_temperature() {
  sensor.requestTemperatures();
  float tempC = sensor.getTempCByIndex(0);

  if (tempC == DEVICE_DISCONNECTED_C || tempC == 85.0) {
    Serial.println("Error in temp sensor, falling back to last best temp value.");
    return filteredTemp;
  }

  return tempC;
}

void connect_to_wifi() {
  WiFiManager wm;
  if (!wm.autoConnect("PhotonVHealth-Setup")) {
    ESP.restart();
  }
}

void connect_via_https(HTTPClient &http, String url, bool isJson) {
  http.begin(client, url);
  http.setTimeout(5000);
  if (isJson) {
    http.addHeader("Content-Type", "application/json");
  }
}

void register_device() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  connect_via_https(http, "https://photonvhealth.onrender.com/api/register_device", true);

  String json = "{";
  json += "\"device_id\":\"" + deviceId + "\"";
  json += "}";

  int code = http.POST(json);

  if (code == 200) {
    String body = http.getString();
    Serial.println("Register response: " + body);

    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      apiKey = doc["apiKey"] | "";

      pref.putString("api_key", apiKey);
      Serial.println("API Key saved!");
    }
  } else {
    Serial.print("Device registration failed: ");
    Serial.println(code);
  }

  http.end();
}

void data_to_server() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  connect_via_https(http, "https://photonvhealth.onrender.com/api/data", true);

  String json = "{";
  json += "\"device_id\":\"" + deviceId + "\",";
  json += "\"api_key\":\"" + apiKey + "\",";
  json += "\"power\":" + String(powerVal) + ",";
  json += "\"light\":" + String(adjustedLight) + ",";
  json += "\"percentage\":" + String(percentageLight) + ",";
  json += "\"temp\":" + String(tempVal) + ",";
  json += "\"efficiency\":" + String(efficiency);
  json += "}";

  int statusCode = http.POST(json);

  if (statusCode == 200) {
    String body = http.getString();
    StaticJsonDocument<128> doc;
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      health = doc["health"] | 0.0f;
    }
  } else {
    Serial.print("POST /api/data failed: ");
    Serial.println(statusCode);
  }

  http.end();
  client.stop();
}

void check_commands() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String commandsUrl = "https://photonvhealth.onrender.com/api/commands/" + deviceId;
  connect_via_https(http, commandsUrl, false);

  int statusCode = http.GET();

  if (statusCode == 200) {
    String body = http.getString();
    StaticJsonDocument<128> doc;

    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      bool renew = doc["renew_baseline"] | false;

      if (renew) {
        float newLight = 4095 - smooth_light();
        float newPower = ina219.getPower_mW();

        if (newPower > 0 && newLight > 0) {
          baselinePower = newPower;
          baselineLight = newLight;

          pref.putFloat("base_pwr", baselinePower);
          pref.putFloat("base_lgt", baselineLight);

          Serial.println("Manual baseline renewed!");
          Serial.print("Baseline Power: ");
          Serial.println(baselinePower);
          Serial.print("Baseline Light: ");
          Serial.println(baselineLight);
        }
      }
    }
  } else {
    Serial.print("GET /api/commands failed: ");
    Serial.println(statusCode);
  }

  http.end();
}

void check_alerts() {
  if (previousLight == 0 && previousPower == 0) {
    previousLight = adjustedLight;
    previousPower = powerVal;
    return;
  }

  float currentMA = ina219.getCurrent_mA();

  if (adjustedLight < 150) return;
  if (currentMA < 20) return;

  float lightChange = previousLight - adjustedLight;
  float powerChange = previousPower - powerVal;

  if (tempVal > 45 && efficiency < 90) {
    if (millis() - lastOverheatAlert > alertCooldown) {
      lastOverheatAlert = millis();
      Serial.println("[ALERT] Overheat detected.");
    }
  }

  if (adjustedLight > baselineLight * 0.8 && efficiency < 75) {
    if (millis() - lastDustAlert > alertCooldown) {
      lastDustAlert = millis();
      Serial.println("[ALERT] Possible dust/soiling detected.");
    }
  }

  if (lightChange > 200 && powerChange > (previousPower * 0.2)) {
    if (millis() - lastShadeAlert > alertCooldown) {
      lastShadeAlert = millis();
      Serial.println("[ALERT] Sudden shading detected.");
    }
  }

  previousLight = adjustedLight;
  previousPower = powerVal;
}

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("PhotonVHealth Setup: Initialized...");

  pref.begin("pvh-settings", false);

  deviceId = pref.getString("dev_id", "");
  if (deviceId == "") {
    uint64_t chipid = ESP.getEfuseMac();
    char idBuffer[20];
    sprintf(idBuffer, "PVH_%04X%08X", (uint16_t)(chipid >> 32), (uint32_t)chipid);
    deviceId = String(idBuffer);
    pref.putString("dev_id", deviceId);
    Serial.println("Generated and saved new Device ID.");
  }

  apiKey = pref.getString("api_key", "");
  baselinePower = pref.getFloat("base_pwr", 0.0);
  baselineLight = pref.getFloat("base_lgt", 0.0);

  Serial.print("Device ID: "); Serial.println(deviceId);

  client.setInsecure();

  ina219.begin();
  sensor.begin();
  sensor.setResolution(12);
  connect_to_wifi();

  filteredTemp = read_temperature();

  if (apiKey == "") {
    register_device();
  }

  check_commands();
}

void loop() {
  unsigned long now = millis();
  if (now - lastDataSend >= dataInterval) {
    lastDataSend = now;

    lightVal = smooth_light();
    adjustedLight = 4095 - lightVal;
    powerVal = ina219.getPower_mW();
    voltageVal = ina219.getBusVoltage_V();

    tempVal = read_temperature();
    filteredTemp = filteredTemp * 0.9 + tempVal * 0.1;
    tempVal = filteredTemp;

    if (baselineLight > 0 && baselinePower > 0) {
      float lightRatio = adjustedLight / baselineLight;
      if (lightRatio > 1.2) lightRatio = 1.2;
      if (lightRatio < 0.1) lightRatio = 0.1;

      float expectedPower = baselinePower * lightRatio;

      if (expectedPower > 0.01) {
        efficiency = (powerVal / expectedPower) * 100.0;
      }
    }

    percentageLight = (adjustedLight / 4095.0) * 100.0;

    data_to_server();

    Serial.println("──────────────────────");
    Serial.print("Your device's ID: "); Serial.println(deviceId);
    Serial.print("Light Intensity: "); Serial.print(percentageLight); Serial.println(" %");
    Serial.print("Light: "); Serial.print(adjustedLight); Serial.println(" a.u.");
    Serial.print("Temp: "); Serial.print(tempVal); Serial.println(" °C");
    Serial.print("Power: "); Serial.print(powerVal); Serial.println(" mW");
    Serial.print("Voltage: "); Serial.print(voltageVal); Serial.println(" V");
    Serial.print("Efficiency: "); Serial.print(efficiency); Serial.println(" %");
    Serial.print("Health: "); Serial.print(health); Serial.println(" %");

    check_alerts();
  }

  now = millis();

  if (now - lastCommandCheck >= commandInterval) {
    lastCommandCheck = now;
    check_commands();
  }

  delay(50);
}