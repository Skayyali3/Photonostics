## Complete Hardware Connection Guide

This section outlines how to route your connections safely, ensuring your code reads from the correct hardware pins.

### 1. Pinout
Use this reference table to connect your sensors and modules directly to the ESP32. 


| Component | Pin Name | Target Pin / Rail | Wire Function / Notes |
| :--- | :--- | :--- | :--- |
| **All Ground Pins** | GND | **Common Ground Rail** | **Mandatory:** All system grounds must link. |
| **ESP32 Core** | 5V / USB Pin | Battery (+) Output | Powers the logic board (3.3V or 5V). |
| | GND | Common Ground Rail | Main reference point. |
| **DS18B20 Temp** | VCC (Red) | ESP32 3V3 Rail | Power feed. |
| | GND (Black) | Common Ground Rail | System ground. |
| | Data (Yellow) | **ESP32 GPIO 4** | **Requires 4.7kΩ pull-up resistor to 3V3.** |
| **KY-018 LDR** | VCC (+) | ESP32 3V3 Rail | Power feed. |
| | GND (-) | Common Ground Rail | System ground. |
| | Signal (S) | **ESP32 GPIO 34** | Analog stream reading into `smooth_light()`. |
| **INA219 Monitor** | VCC | ESP32 3V3 Rail | Power feed. |
| | GND | Common Ground Rail | System ground. |
| | SDA | **ESP32 GPIO 21** | I2C Data line. |
| | SCL | **ESP32 GPIO 22** | I2C Clock line. |

---

### 2. Solar Power Wiring
Choose **Option A** or **Option B** below depending on how you power your system load.

#### Option A: Connection WITH a Buck Converter (Standard Setup)
Use this setup if you are stepping down the voltage before running your load.

```text
 SOLAR PANEL (+) ──► [ INA219 VIN(+) ]
                       (Internal Shunt)
                     [ INA219 VIN(-) ] ──► [ BUCK CONVERTER IN(+) ] ──► [ LOAD (+) ]

 CENTRAL GND RAIL ◄── [ SOLAR PANEL (-) ] ◄── [ BUCK CONVERTER IN(-) ] ◄── [ LOAD (-) ]
```

#### Option B: Connection WITHOUT a Buck Converter (Direct Setup)
Use this setup if you are connecting your load directly to the solar panel's output.

```text
 SOLAR PANEL (+) ──► [ INA219 VIN(+) ]
                       (Internal Shunt)
                     [ INA219 VIN(-) ] ──────────────────────────────► [ LOAD (+) ]

 CENTRAL GND RAIL ◄── [ SOLAR PANEL (-) ] ◄───────────────────────────── [ LOAD (-) ]
```

---

### 3. Step-by-Step Hardware Validation Checklist
1. **Set Up Grounds:** Run a single jumper wire from an ESP32 `GND` pin to a dedicated blank strip on a breadboard. Connect every other module's `GND` pin to this strip.
2. **Configure the Pull-Up:** Place a **4.7kΩ resistor** directly between the DS18B20 Data wire (GPIO 4) and the 3.3V rail. Without this resistor, your console will output `85.0 °C` or disconnect errors.
3. **Verify the Solar Loop:** Ensure the panel's positive lead touches **only** `VIN(+)` on the INA219 breakout board. The load must consume downstream power from `VIN(-)`.
4. **Boot and Test:** Flash the testing script via the Arduino IDE. Open your Serial Monitor at **115200 baud** to see live metrics printing every 2 seconds.
5. **Test the following code first before the main microcontroller:** *[Click Here](https://github.com/Skayyali3/Photonostics/blob/main/Hardware/Standalone-Tests/Microcontroller/Microcontroller.ino)*