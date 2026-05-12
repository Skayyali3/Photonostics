# PhotonVHealth - Solar Panel Efficiency Monitoring

Welcome to PhotonVHealth for solar panel efficiency monitoring, especially useful for DIY project users. My monitor makes sure external factors such as: 

* Dust Accumulation

* Sudden shading

* Overheating

don't cause sudden losses in the efficiency of your panel(s) while going unnoticed.

---

## Hardware:

### Components Needed:

* **DS18B20 Waterproof:** Temperature
* **KY-018 LDR:** Light Intensity + part of baseline ratio
* **INA219:** Measure Power produced + Voltage
* **ESP32:** Send data to website + Serial monitoring - The Brain
* **Solar Panel:** To measure power produced + voltage
* **Buck Converter (Optional):** Connect INA219 VIN- and VIN+ to Buck Converter + which should also be connected to Solar Panel positive

* **Load:** Either connected to Buck Converter or directly to solar panel
    - if directly: same connection steps as buck converter except replace buck converter with load
    - else: no need to think much about this

* **3.3V battery/5V battery connected directly to USB entry point of ESP32:** Power ESP32 

#### REMINDER: COMMON GND FOR ALL

### Arduino IDE Libraries Needed:

* **Wire.h:** Comes Preinstalled - For I2C Communication

* **Adafruit_INA219.h:** Install Needed - For INA219 functions

* **WiFi.h:**  Comes Preinstalled - To make sure WiFi status is OK before HTTP requests, etc

* **HTTPClient.h:** Install Needed - For HTTP requests

* **WiFiManager.h:**  Install Needed - To allow users to connect to a network without hardcoding credentials

* **ArduinoJson.h:** To send data to server via JSON

* **DallasTemperature.h:** To get temp readings

* **OneWire.h:** DS18B20 functions on OneWire protocol - to initialize sensor

* **WiFiClientSecure.h:** Manage required encryption for the HTTPS requests

* **Preferences.h:** To store device id and device api key in non-voltatile memory of ESP32 (NVS)

---

## Software:

### Tech Used:

* **Flask Backend on Render**

* **HTML/CSS/JS/Jinja/Bootstrap - Frontend**

* **PostgreSQL Database on Supabase**

* **Uptimerobot**

* **The Following Libraries:**

    - flask: backend microframework
    - flask_limiter: rate limit requests
    - psycopg2: PostgreSQL database
    - os: get env variables + robots.txt
    - dotenv: load env variables to use
    - contextlib: database cursor automation
    - datetime: inject year to footer + expiry of reset password tokens
    - secrets: generate auth tokens
    - werkzeug: hash passwords
    - re: regex of device ids
    - email: make body of password reset emails
    - smtplib: send password reset emails
    - pywebpush: send the push notifications themselves
    - json: decode the notification payload
    - logging: log push notification warning/errors
    - threading: make response to ESP32 faster

### Live Demo:

To check out the website: **[Click Here](https://photonvhealth.onrender.com/)**

---

## Licensing:

The device itself is licensed under the MIT license - may be edited upon, improved, etc
For further details: **[Click Here](https://github.com/Skayyali3/PhotonVHealth/blob/main/Hardware/LICENSE)**

The website is licensed under the GNU GPL V3 license - For further details: **[Click Here](https://github.com/Skayyali3/PhotonVHealth/blob/main/website/LICENSE)**

## Author:
**Saif Kayyali**
