/**
 * @file wifi_manager.h
 * @brief WiFi connection and AP configuration portal for InkTime 73E firmware
 *
 * Handles WiFi connectivity and provides a captive portal for device configuration.
 * Portal SSID: "InkTime-xxxxxxxx" (MAC suffix)
 * Portal Password: "12345678"
 * Portal IP: 192.168.4.1
 */

#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <WiFi.h>
#include <WebServer.h>
#include <esp_sleep.h>
#include "config.h"
#include "nvs_manager.h"

// =============================================================================
// WiFi Connection
// =============================================================================

/**
 * @brief Connect to WiFi using stored credentials
 * @param cfg Device configuration with WiFi credentials
 * @return true if connected successfully, false on timeout
 *
 * Timeout after WIFI_CONNECT_TIMEOUT_MS milliseconds.
 */
inline bool wifi_connect(const DeviceConfig& cfg) {
    DBG_PRINT("[WiFi] Connecting to: ");
    DBG_PRINTLN(cfg.wifi_ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(cfg.wifi_ssid.c_str(), cfg.wifi_pass.c_str());

    unsigned long start_time = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start_time > WIFI_CONNECT_TIMEOUT_MS) {
            DBG_PRINTLN("[WiFi] Connection timeout");
            WiFi.disconnect(true);
            return false;
        }
        delay(100);
        DBG_PRINT(".");
    }

    DBG_PRINTLN("");
    DBG_PRINT("[WiFi] Connected! IP: ");
    DBG_PRINTLN(WiFi.localIP().toString());
    return true;
}

// =============================================================================
// AP Configuration Portal
// =============================================================================

/**
 * @brief Generate HTML configuration page
 * @param networks Found WiFi networks (comma-separated)
 * @param current Current configuration values
 * @return HTML string
 */
inline String generate_config_html(const String& networks, const DeviceConfig& current) {
    String html = R"rawliteral(<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InkTime Configuration</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 400px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; font-size: 24px; margin-bottom: 20px; text-align: center; }
        label { display: block; margin-top: 15px; font-weight: bold; color: #555; }
        input, select { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        input[type="password"] { font-family: monospace; }
        .hint { font-size: 12px; color: #888; margin-top: 3px; }
        button { width: 100%; margin-top: 25px; padding: 12px; background: #4CAF50; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
        button:hover { background: #45a049; }
    </style>
</head>
<body>
    <div class="container">
        <h1>InkTime Setup</h1>
        <form method="POST" action="/save">
            <label>WiFi Network</label>
            <select id="ssid_select" name="ssid_select" onchange="document.getElementById('ssid_manual').value=''">
                <option value="">-- Select Network --</option>
)rawliteral";

    // Add network options
    int idx = 0;
    int pos = 0;
    while (pos >= 0 && pos < networks.length()) {
        int next = networks.indexOf(',', pos);
        String net;
        if (next < 0) {
            net = networks.substring(pos);
            pos = -1;
        } else {
            net = networks.substring(pos, next);
            pos = next + 1;
        }
        if (net.length() > 0) {
            html += "<option value=\"" + net + "\">" + net + "</option>\n";
        }
    }

    html += R"rawliteral(            </select>
            <label>Or Enter Manually</label>
            <input type="text" id="ssid_manual" name="ssid_manual" placeholder="Enter WiFi name" value=")rawliteral";

    html += current.wifi_ssid;
    html += R"rawliteral(">
            <label>Password</label>
            <input type="password" name="pass" placeholder="WiFi password" value=")rawliteral";

    html += current.wifi_pass;
    html += R"rawliteral(">
            <label>Server Address</label>
            <input type="text" name="host" placeholder="192.168.1.100:8765" value=")rawliteral";

    html += current.server_host;
    html += R"rawliteral(">
            <div class="hint">Host:port format (e.g., 192.168.1.100:8765)</div>
            <label>Refresh Hour</label>
            <select name="hour">
)rawliteral";

    // Hour dropdown (0-23)
    for (int h = 0; h < 24; h++) {
        char buf[8];
        sprintf(buf, "%02d:00", h);
        html += "<option value=\"" + String(h) + "\"";
        if (h == current.refresh_hour) {
            html += " selected";
        }
        html += ">" + String(buf) + "</option>\n";
    }

    html += R"rawliteral(            </select>
            <label>Timezone (UTC)</label>
            <select name="tz">
)rawliteral";

    // Timezone dropdown (-12 to +14)
    for (int tz = -12; tz <= 14; tz++) {
        String label = (tz >= 0) ? "UTC+" + String(tz) : "UTC" + String(tz);
        html += "<option value=\"" + String(tz) + "\"";
        if (tz == current.tz_offset) {
            html += " selected";
        }
        html += ">" + label + "</option>\n";
    }

    html += R"rawliteral(            </select>
            <button type="submit">Save & Reboot</button>
        </form>
    </div>
</body>
</html>
)rawliteral";

    return html;
}

/**
 * @brief Start AP configuration portal (blocking)
 * @param cfg Reference to DeviceConfig (will be updated on save)
 *
 * Creates AP with SSID "InkTime-xxxxxxxx" (last 8 hex of MAC).
 * Serves config page at 192.168.4.1.
 * On save: stores to NVS and reboots.
 * On timeout (5 min): enters deep sleep for 24 hours.
 */
inline void wifi_start_ap_portal(DeviceConfig& cfg) {
    DBG_PRINTLN("[AP] Starting configuration portal...");

    // Generate SSID from MAC address
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char mac_suffix[9];
    sprintf(mac_suffix, "%02X%02X%02X%02X", mac[2], mac[3], mac[4], mac[5]);
    String ap_ssid = String(AP_SSID_PREFIX) + String(mac_suffix);

    DBG_PRINT("[AP] SSID: ");
    DBG_PRINTLN(ap_ssid);

    // Start AP mode
    WiFi.mode(WIFI_AP);
    WiFi.softAP(ap_ssid.c_str(), AP_PASSWORD);

    IPAddress ip(192, 168, 4, 1);
    IPAddress gateway(192, 168, 4, 1);
    IPAddress subnet(255, 255, 255, 0);
    WiFi.softAPConfig(ip, gateway, subnet);

    DBG_PRINT("[AP] IP: ");
    DBG_PRINTLN(ip.toString());

    // Scan for WiFi networks
    DBG_PRINTLN("[AP] Scanning WiFi networks...");
    int num_networks = WiFi.scanNetworks();
    String networks = "";
    for (int i = 0; i < num_networks; i++) {
        if (i > 0) networks += ",";
        networks += WiFi.SSID(i);
    }
    DBG_PRINT("[AP] Found ");
    DBG_PRINT(num_networks);
    DBG_PRINTLN(" networks");

    // Create web server
    WebServer server(80);

    // GET / - Configuration page
    server.on("/", [&]() {
        DBG_PRINTLN("[AP] GET / - Serving config page");
        server.send(200, "text/html", generate_config_html(networks, cfg));
    });

    // POST /save - Save configuration
    server.on("/save", [&]() {
        DBG_PRINTLN("[AP] POST /save - Saving configuration");

        // Get SSID (from dropdown or manual input)
        String ssid = server.arg("ssid_select");
        if (ssid.length() == 0) {
            ssid = server.arg("ssid_manual");
        }

        // Get other parameters
        String pass = server.arg("pass");
        String host = server.arg("host");
        int hour = server.arg("hour").toInt();
        int tz = server.arg("tz").toInt();

        // Validate
        if (ssid.length() == 0) {
            server.send(400, "text/plain", "Error: SSID is required");
            return;
        }

        // Update configuration
        cfg.wifi_ssid = ssid;
        cfg.wifi_pass = pass;
        cfg.server_host = host;
        cfg.refresh_hour = (uint8_t)hour;
        cfg.tz_offset = (int8_t)tz;
        cfg.valid = true;

        // Save to NVS
        nvs_save_config(cfg);

        // Send response and reboot
        server.send(200, "text/plain", "Configuration saved. Rebooting...");
        DBG_PRINTLN("[AP] Configuration saved, rebooting...");

        delay(1000);
        ESP.restart();
    });

    // Start server
    server.begin();
    DBG_PRINTLN("[AP] Server started at http://192.168.4.1/");

    // Main loop with timeout
    unsigned long start_time = millis();
    while (millis() - start_time < AP_TIMEOUT_MS) {
        server.handleClient();
        delay(10);
    }

    // Timeout - enter deep sleep
    DBG_PRINTLN("[AP] Timeout, entering deep sleep...");
    server.stop();
    WiFi.softAPdisconnect(true);

    esp_sleep_enable_timer_wakeup((uint64_t)DEEP_SLEEP_MAX_MINUTES * 60 * 1000000ULL);
    esp_deep_sleep_start();
}

#endif // WIFI_MANAGER_H
