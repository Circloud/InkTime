/**
 * @file sleep_manager.h
 * @brief Deep sleep management for InkTime 73E firmware
 *
 * Handles scheduled deep sleep with power optimization for ESP32-S3.
 * Calculates sleep duration based on target refresh hour and manages
 * low-power state entry with WiFi disconnect and RTC domain power-off.
 */

#ifndef SLEEP_MANAGER_H
#define SLEEP_MANAGER_H

#include <time.h>
#include <esp_sleep.h>
#include "config.h"
#include "nvs_manager.h"

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * @brief Calculate minutes until next scheduled refresh
 * @param current_hour Current hour (0-23)
 * @param current_min Current minute (0-59)
 * @param target_hour Target refresh hour (0-23)
 * @return Minutes until next refresh (clamped to MIN/MAX range)
 *
 * Logic:
 * - If current < target: delta = target - current
 * - If current >= target: delta = 24*60 - (current - target)
 */
inline uint32_t calc_minutes_to_refresh(int current_hour, int current_min, int target_hour) {
    uint32_t current_total = (current_hour * 60) + current_min;
    uint32_t target_total = (target_hour * 60);

    uint32_t delta;
    if (current_total < target_total) {
        // Target is later today
        delta = target_total - current_total;
    } else {
        // Target is tomorrow
        delta = (24 * 60) - (current_total - target_total);
    }

    // Clamp to configured limits
    if (delta < DEEP_SLEEP_MIN_MINUTES) {
        delta = DEEP_SLEEP_MIN_MINUTES;
    } else if (delta > DEEP_SLEEP_MAX_MINUTES) {
        delta = DEEP_SLEEP_MAX_MINUTES;
    }

    return delta;
}

// =============================================================================
// Main Functions
// =============================================================================

/**
 * @brief Enter deep sleep for specified minutes
 * @param minutes Duration to sleep in minutes
 *
 * Performs:
 * 1. WiFi disconnect and power-off
 * 2. Configure RTC power domains to OFF
 * 3. Enable timer wakeup
 * 4. Enter deep sleep
 */
inline void sleep_enter_minutes(uint32_t minutes) {
    // Clamp to valid range
    if (minutes < DEEP_SLEEP_MIN_MINUTES) {
        minutes = DEEP_SLEEP_MIN_MINUTES;
    } else if (minutes > DEEP_SLEEP_MAX_MINUTES) {
        minutes = DEEP_SLEEP_MAX_MINUTES;
    }

    DBG_PRINT("[SLEEP] Entering deep sleep for ");
    DBG_PRINT(minutes);
    DBG_PRINTLN(" minutes");

    // Disconnect and power off WiFi to save power
    WiFi.disconnect(true, true);  // Disconnect and clear config
    WiFi.mode(WIFI_OFF);

    // Power off RTC domains (not needed for timer wakeup)
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_SLOW_MEM, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_FAST_MEM, ESP_PD_OPTION_OFF);

    // Configure timer wakeup (microseconds)
    uint64_t sleep_time_us = (uint64_t)minutes * 60 * 1000000ULL;
    esp_sleep_enable_timer_wakeup(sleep_time_us);

    DBG_PRINTLN("[SLEEP] Entering deep sleep now...");

    // Enter deep sleep (ESP32 will reset on wake)
    esp_deep_sleep_start();
}

/**
 * @brief Sleep until next scheduled refresh hour
 * @param cfg Device configuration with refresh_hour setting
 * @param now Current time from NTP
 *
 * Calculates time until next refresh and enters deep sleep.
 * On wake, ESP32 resets and runs setup() again.
 */
inline void sleep_until_scheduled(DeviceConfig& cfg, const struct tm& now) {
    uint32_t minutes = calc_minutes_to_refresh(now.tm_hour, now.tm_min, cfg.refresh_hour);

    DBG_PRINT("[SLEEP] Current time: ");
    DBG_PRINT(now.tm_hour);
    DBG_PRINT(":");
    DBG_PRINT(now.tm_min);
    DBG_PRINT(", Target hour: ");
    DBG_PRINT(cfg.refresh_hour);
    DBG_PRINT(", Minutes to sleep: ");
    DBG_PRINTLN(minutes);

    sleep_enter_minutes(minutes);
}

#endif // SLEEP_MANAGER_H
