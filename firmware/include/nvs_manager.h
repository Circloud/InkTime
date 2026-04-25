/**
 * @file nvs_manager.h
 * @brief Non-Volatile Storage manager for InkTime 73E firmware
 *
 * Manages persistent configuration using ESP32 Preferences library.
 * Stores WiFi credentials, server settings, photo tracking, and timestamps.
 */

#ifndef NVS_MANAGER_H
#define NVS_MANAGER_H

#include <Preferences.h>
#include <Arduino.h>
#include "config.h"

// =============================================================================
// Device Configuration Structure
// =============================================================================
struct DeviceConfig {
    String wifi_ssid;       // WiFi network name
    String wifi_pass;       // WiFi password
    String server_host;     // Server address (host:port format)
    int8_t tz_offset;       // Timezone offset (-12 to +14)
    uint8_t refresh_hour;   // Daily refresh hour (0-23)
    uint8_t photo_index;    // Current photo index (0 to PHOTO_COUNT_MAX-1)
    String last_date;       // Last processed date (YYYY-MM-DD)
    time_t last_epoch;      // Last successful sync epoch
    bool valid;             // True if wifi_ssid is non-empty

    /**
     * @brief Default constructor initializes with defaults
     */
    DeviceConfig()
        : wifi_ssid("")
        , wifi_pass("")
        , server_host("")
        , tz_offset(DEFAULT_TZ_OFFSET)
        , refresh_hour(DEFAULT_REFRESH_HOUR)
        , photo_index(0)
        , last_date("")
        , last_epoch(0)
        , valid(false)
    {}
};

// =============================================================================
// NVS Manager Functions
// =============================================================================

/**
 * @brief Load all configuration from NVS
 * @return DeviceConfig struct with loaded values or defaults
 */
inline DeviceConfig nvs_load_config() {
    DeviceConfig cfg;
    Preferences prefs;

    prefs.begin(NVS_NAMESPACE, true);  // Read-only mode

    // Load WiFi credentials
    cfg.wifi_ssid = prefs.getString(NVS_KEY_SSID, "");
    cfg.wifi_pass = prefs.getString(NVS_KEY_PASS, "");

    // Load server configuration
    cfg.server_host = prefs.getString(NVS_KEY_HOSTPORT, "");

    // Load timezone and refresh hour
    cfg.tz_offset = prefs.getChar(NVS_KEY_TZ, DEFAULT_TZ_OFFSET);
    cfg.refresh_hour = prefs.getUChar(NVS_KEY_HOUR, DEFAULT_REFRESH_HOUR);

    // Load photo tracking
    cfg.photo_index = prefs.getUChar(NVS_KEY_PHOTO_IDX, 0);
    cfg.last_date = prefs.getString(NVS_KEY_LAST_DATE, "");
    cfg.last_epoch = prefs.getULong64(NVS_KEY_LAST_EPOCH, 0);

    prefs.end();

    // Validate: config is valid if SSID is set
    cfg.valid = (cfg.wifi_ssid.length() > 0);

    DBG_PRINTLN("[NVS] Configuration loaded:");
    DBG_PRINT("[NVS]   SSID: ");
    DBG_PRINTLN(cfg.wifi_ssid);
    DBG_PRINT("[NVS]   Server: ");
    DBG_PRINTLN(cfg.server_host);
    DBG_PRINT("[NVS]   TZ offset: ");
    DBG_PRINTLN(cfg.tz_offset);
    DBG_PRINT("[NVS]   Refresh hour: ");
    DBG_PRINTLN(cfg.refresh_hour);
    DBG_PRINT("[NVS]   Photo index: ");
    DBG_PRINTLN(cfg.photo_index);
    DBG_PRINT("[NVS]   Last date: ");
    DBG_PRINTLN(cfg.last_date);
    DBG_PRINT("[NVS]   Valid: ");
    DBG_PRINTLN(cfg.valid ? "Yes" : "No");

    return cfg;
}

/**
 * @brief Save all configuration to NVS
 * @param cfg DeviceConfig struct with values to save
 */
inline void nvs_save_config(const DeviceConfig& cfg) {
    Preferences prefs;

    prefs.begin(NVS_NAMESPACE, false);  // Read-write mode

    // Save WiFi credentials
    prefs.putString(NVS_KEY_SSID, cfg.wifi_ssid);
    prefs.putString(NVS_KEY_PASS, cfg.wifi_pass);

    // Save server configuration
    prefs.putString(NVS_KEY_HOSTPORT, cfg.server_host);

    // Save timezone and refresh hour
    prefs.putChar(NVS_KEY_TZ, cfg.tz_offset);
    prefs.putUChar(NVS_KEY_HOUR, cfg.refresh_hour);

    // Save photo tracking
    prefs.putUChar(NVS_KEY_PHOTO_IDX, cfg.photo_index);
    prefs.putString(NVS_KEY_LAST_DATE, cfg.last_date);
    prefs.putULong64(NVS_KEY_LAST_EPOCH, cfg.last_epoch);

    prefs.end();

    DBG_PRINTLN("[NVS] Configuration saved");
}

/**
 * @brief Increment photo index with wrap-around
 * @param cfg Reference to DeviceConfig (will be modified and saved)
 *
 * Cycles: 0 -> 1 -> 2 -> 0
 */
inline void nvs_update_photo_index(DeviceConfig& cfg) {
    cfg.photo_index = (cfg.photo_index + 1) % PHOTO_COUNT_MAX;

    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, false);
    prefs.putUChar(NVS_KEY_PHOTO_IDX, cfg.photo_index);
    prefs.end();

    DBG_PRINT("[NVS] Photo index updated to: ");
    DBG_PRINTLN(cfg.photo_index);
}

/**
 * @brief Check if date changed and reset photo index if new day
 * @param cfg Reference to DeviceConfig (will be modified if new day)
 * @param today Current date string (YYYY-MM-DD format)
 * @return true if new day detected, false otherwise
 */
inline bool nvs_check_new_day(DeviceConfig& cfg, const String& today) {
    if (cfg.last_date != today) {
        DBG_PRINT("[NVS] New day detected: ");
        DBG_PRINTLN(today);

        // Reset photo index to 0 for new day
        cfg.photo_index = 0;
        cfg.last_date = today;

        // Save updated values
        Preferences prefs;
        prefs.begin(NVS_NAMESPACE, false);
        prefs.putUChar(NVS_KEY_PHOTO_IDX, cfg.photo_index);
        prefs.putString(NVS_KEY_LAST_DATE, cfg.last_date);
        prefs.end();

        DBG_PRINTLN("[NVS] Photo index reset to 0 for new day");
        return true;
    }

    DBG_PRINTLN("[NVS] Same day, photo index unchanged");
    return false;
}

/**
 * @brief Update last sync epoch in NVS
 * @param cfg Reference to DeviceConfig (will be modified)
 * @param epoch Current epoch time
 */
inline void nvs_update_epoch(DeviceConfig& cfg, time_t epoch) {
    cfg.last_epoch = epoch;

    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, false);
    prefs.putULong64(NVS_KEY_LAST_EPOCH, cfg.last_epoch);
    prefs.end();

    DBG_PRINT("[NVS] Epoch updated to: ");
    DBG_PRINTLN((unsigned long)epoch);
}

/**
 * @brief Clear all NVS configuration (factory reset)
 */
inline void nvs_clear_config() {
    Preferences prefs;

    prefs.begin(NVS_NAMESPACE, false);
    prefs.clear();
    prefs.end();

    DBG_PRINTLN("[NVS] All configuration cleared (factory reset)");
}

/**
 * @brief Check if factory reset is requested via hardware pin
 * @return true if PIN_FACTORY_RESET is LOW at boot
 *
 * Should be called early in setup() before other initializations.
 */
inline bool nvs_is_factory_reset_requested() {
    pinMode(PIN_FACTORY_RESET, INPUT_PULLUP);
    delay(FACTORY_RESET_SAMPLE_DELAY_MS);

    bool reset_requested = (digitalRead(PIN_FACTORY_RESET) == LOW);

    if (reset_requested) {
        DBG_PRINTLN("[NVS] Factory reset requested via hardware pin");
    }

    return reset_requested;
}

#endif // NVS_MANAGER_H
