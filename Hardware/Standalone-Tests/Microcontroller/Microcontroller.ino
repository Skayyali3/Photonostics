#include <Wire.h>
#include <Adafruit_INA219.h>
#include <DallasTemperature.h>
#include <OneWire.h>
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

const unsigned long dataInterval = 2000;

String deviceId = "";

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
    Serial.println("[ALERT] Overheat detected.");
  }

  if (adjustedLight > baselineLight * 0.8 && efficiency < 75) {
    Serial.println("[ALERT] Possible dust/soiling detected.");
  }

  if (lightChange > 200 && powerChange > (previousPower * 0.2)) {
    Serial.println("[ALERT] Sudden shading detected."); 
  }

  previousLight = adjustedLight;
  previousPower = powerVal;
}

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("Photonostics Setup: Initialized...");

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

  Serial.print("Device ID: ");
  Serial.println(deviceId);

  ina219.begin();
  sensor.begin();
  sensor.setResolution(12);

  filteredTemp = read_temperature();
  pref.end();
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

    Serial.println("──────────────────────");
    Serial.print("Your device's ID: "); Serial.println(deviceId);
    Serial.print("Light Intensity: "); Serial.print(percentageLight); Serial.println(" %");
    Serial.print("Light: "); Serial.print(adjustedLight); Serial.println(" a.u.");
    Serial.print("Temp: "); Serial.print(tempVal); Serial.println(" °C");
    Serial.print("Power: "); Serial.print(powerVal); Serial.println(" mW");
    Serial.print("Voltage: "); Serial.print(voltageVal); Serial.println(" V");
    Serial.print("Efficiency: "); Serial.print(efficiency); Serial.println(" %");
    Serial.print("Health: "); Serial.print(health); Serial.println(" %");
  }
}