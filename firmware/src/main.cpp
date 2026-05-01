/**
 * @file main.cpp
 * @brief ESP32-S3 firmware for 7.3" E6 6-color e-ink photo frame (InkTime)
 *
 * Complete firmware workflow:
 * 1. Release GPIO holds from deep sleep
 * 2. Set CPU frequency to 80MHz (power saving)
 * 3. Initialize serial for debug
 * 4. Check factory reset button
 * 5. Load config from NVS
 * 6. If no valid config: start AP portal
 * 7. Connect WiFi (if fail: start AP portal)
 * 8. Sync time via NTP
 * 9. Download photo
 * 10. If success: display image, update photo index
 * 11. Free buffer
 * 12. Sleep until scheduled time
 *
 * Hardware: ESP32-S3-WROOM-1-N8R8 + 7.3" E6 6-color panel (GDEP073E01)
 */

#include <Arduino.h>
#include <SPI.h>
#include <time.h>
#include <esp_sleep.h>
#include <esp_wifi.h>

#include "config.h"
#include "nvs_manager.h"
#include "wifi_manager.h"
#include "downloader.h"
#include "display.h"
#include "sleep_manager.h"

// =============================================================================
// NTP Time Synchronization
// =============================================================================

/**
 * @brief Sync time via NTP and update NVS
 * @param cfg Reference to DeviceConfig (last_date and epoch will be updated)
 * @param outTime Output struct to receive current time
 * @return true on successful sync, false on failure
 */
bool sync_time(DeviceConfig& cfg, struct tm& outTime) {
    DBG_PRINTLN("[NTP] Starting time synchronization...");

    // Configure NTP server with timezone offset
    // TZ format: UTC offset (e.g., "CST-8" for UTC+8)
    String tz_str;
    if (cfg.tz_offset >= 0) {
        tz_str = "CST-" + String(cfg.tz_offset);
    } else {
        tz_str = "CST" + String(cfg.tz_offset);  // Negative already includes minus sign
    }

    configTzTime(tz_str.c_str(), "pool.ntp.org", "time.nist.gov");

    // Wait for time sync with timeout
    const unsigned long NTP_TIMEOUT_MS = 10000;  // 10 seconds
    unsigned long start_time = millis();
    time_t now;
    struct tm timeinfo;

    while (millis() - start_time < NTP_TIMEOUT_MS) {
        time(&now);
        localtime_r(&now, &timeinfo);

        // Check if year is valid (after 2020)
        if (timeinfo.tm_year + 1900 > 2020) {
            outTime = timeinfo;

            // Format current date string
            char date_str[16];
            strftime(date_str, sizeof(date_str), "%Y-%m-%d", &timeinfo);
            String today = String(date_str);

            DBG_PRINT("[NTP] Synced: ");
            DBG_PRINT(asctime(&timeinfo));
            DBG_PRINT("[NTP] Date: ");
            DBG_PRINTLN(today);
            DBG_PRINT("[NTP] Epoch: ");
            DBG_PRINTLN((unsigned long)now);

            // Update NVS with new date and epoch
            nvs_check_new_day(cfg, today);
            nvs_update_epoch(cfg, now);

            return true;
        }

        delay(500);
        DBG_PRINT(".");
    }

    DBG_PRINTLN("");
    DBG_PRINTLN("[NTP] Timeout - failed to sync time");
    return false;
}

// =============================================================================
// Main Entry Point
// =============================================================================
void setup() {
    // =========================================================================
    // Step 1: Release GPIO holds from deep sleep
    // =========================================================================
    // ESP32-S3 may hold GPIO state during deep sleep
    // Release any held pins before initialization
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);

    // =========================================================================
    // Step 2: Set CPU frequency to 80MHz (power saving)
    // =========================================================================
    setCpuFrequencyMhz(80);

    // =========================================================================
    // Step 3: Initialize serial for debug output
    // =========================================================================
    DBG_BEGIN();
    delay(500);  // Wait for serial terminal to connect

    DBG_PRINTLN("");
    DBG_PRINTLN("========================================");
    DBG_PRINTLN("  InkTime 7.3\" E6 6-Color Photo Frame");
    DBG_PRINTLN("  ESP32-S3-WROOM-1-N8R8");
    DBG_PRINTLN("========================================");
    DBG_PRINTLN("");

    // =========================================================================
    // Step 4: Check factory reset button
    // =========================================================================
    if (nvs_is_factory_reset_requested()) {
        DBG_PRINTLN("[MAIN] Factory reset requested, clearing NVS...");
        nvs_clear_config();
        DBG_PRINTLN("[MAIN] Configuration cleared, will enter AP mode");
    }

    // =========================================================================
    // Step 5: Load configuration from NVS
    // =========================================================================
    DeviceConfig cfg = nvs_load_config();

    // =========================================================================
    // Step 6: Check if valid config exists
    // =========================================================================
    if (!cfg.valid) {
        DBG_PRINTLN("[MAIN] No valid configuration found");
        DBG_PRINTLN("[MAIN] Starting AP configuration portal...");
        wifi_start_ap_portal(cfg);
        // Note: AP portal blocks until timeout or reboot
        // If we reach here, it's a timeout - will deep sleep
        return;
    }

    // =========================================================================
    // Step 7: Connect to WiFi
    // =========================================================================
    DBG_PRINTLN("[MAIN] Connecting to WiFi...");
    if (!wifi_connect(cfg)) {
        DBG_PRINTLN("[MAIN] WiFi connection failed");
        DBG_PRINTLN("[MAIN] Starting AP configuration portal...");
        wifi_start_ap_portal(cfg);
        // Note: AP portal blocks until timeout or reboot
        return;
    }

    // =========================================================================
    // Step 8: Sync time via NTP
    // =========================================================================
    DBG_PRINTLN("[MAIN] Syncing time via NTP...");
    struct tm current_time;
    if (!sync_time(cfg, current_time)) {
        DBG_PRINTLN("[MAIN] NTP sync failed, will retry next wake");
        // Sleep and retry later (1 minute minimum)
        sleep_enter_minutes(DEEP_SLEEP_MIN_MINUTES);
        return;
    }

    // =========================================================================
    // Step 9: Download photo
    // =========================================================================
    DBG_PRINTLN("[MAIN] Downloading photo...");

    uint8_t* image_buffer = nullptr;
    bool download_ok = download_photo(cfg, &image_buffer);

    if (!download_ok || image_buffer == nullptr) {
        DBG_PRINTLN("[MAIN] Download failed, will retry next scheduled time");
        // Sleep until next scheduled refresh (don't update index on failure)
        sleep_until_scheduled(cfg, current_time);
        return;
    }

    // =========================================================================
    // Step 10: Display image
    // =========================================================================
    DBG_PRINTLN("[MAIN] Initializing display...");
    display_init();

    DBG_PRINTLN("[MAIN] Rendering image...");
    display_render(image_buffer);

    DBG_PRINTLN("[MAIN] Display update complete");

    // =========================================================================
    // Step 11: Free buffer and cleanup
    // =========================================================================
    free(image_buffer);
    image_buffer = nullptr;
    DBG_PRINTLN("[MAIN] Image buffer freed");

    // Put display to hibernate for power saving
    display_hibernate();
    display_power_down_pins();

    // =========================================================================
    // Step 12: Sleep until scheduled time
    // =========================================================================
    DBG_PRINTLN("[MAIN] Entering deep sleep...");
    DBG_PRINTLN("========================================");
    DBG_PRINTLN("");

    sleep_until_scheduled(cfg, current_time);
}

// =============================================================================
// Empty Loop (never reached - device enters deep sleep after setup)
// =============================================================================
void loop() {
    // Empty - device enters deep sleep at the end of setup()
    // This should never be reached
    delay(10000);
}
