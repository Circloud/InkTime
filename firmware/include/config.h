/**
 * @file config.h
 * @brief Centralized configuration constants for InkTime 73E firmware
 *
 * Hardware: ESP32-S3-WROOM-1-N8R8 with 7.3" E6 6-color e-ink display (GDEP073E01)
 * Server endpoint: GET /api/photo returns 192KB 4bpp packed binary
 * Display: 480x800 portrait, rendered with 180 degree rotation
 * Workflow: WiFi connect -> NTP sync -> download -> display -> deep sleep
 */

#ifndef CONFIG_H
#define CONFIG_H

// =============================================================================
// Debug Configuration
// =============================================================================
#define DEBUG_LOG 1

#if DEBUG_LOG
  #define DBG_BEGIN()    Serial.begin(115200)
  #define DBG_PRINT(x)   Serial.print(x)
  #define DBG_PRINTLN(x) Serial.println(x)
#else
  #define DBG_BEGIN()
  #define DBG_PRINT(x)
  #define DBG_PRINTLN(x)
#endif

// =============================================================================
// EPD SPI Pin Definitions (same as 7C variant - same adapter board)
// =============================================================================
#define PIN_EPD_BUSY    14      // Busy signal
#define PIN_EPD_RST     13      // Reset
#define PIN_EPD_DC      12      // Data/Command select
#define PIN_EPD_CS      11      // Chip select
#define PIN_EPD_SCLK    10      // SPI clock
#define PIN_EPD_DIN     9       // SPI MOSI

// =============================================================================
// Factory Reset Pin
// =============================================================================
#define PIN_FACTORY_RESET           38      // Hold LOW during boot to reset
#define FACTORY_RESET_ACTIVE_LOW    1       // Active low (LOW = reset request)
#define FACTORY_RESET_SAMPLE_DELAY_MS 5     // Debounce delay

// =============================================================================
// Display Constants
// =============================================================================
#define CANVAS_WIDTH        480     // Portrait width in pixels
#define CANVAS_HEIGHT       800     // Portrait height in pixels
#define IMAGE_SIZE_BYTES    192000  // 480 * 800 / 2 for 4bpp packed

// =============================================================================
// Color Indices for E6 6-color palette (GxEPD2 native format)
// =============================================================================
// GxEPD2_730c_GDEP073E01 native color mapping:
// 0=Black, 1=White, 2=Yellow, 3=Red, 5=Blue, 6=Green
#define COLOR_BLACK     0
#define COLOR_WHITE     1
#define COLOR_YELLOW    2
#define COLOR_RED       3
#define COLOR_BLUE      5
#define COLOR_GREEN     6

// =============================================================================
// WiFi & AP Configuration
// =============================================================================
#define AP_SSID_PREFIX          "InkTime-"
#define AP_PASSWORD             "12345678"
#define AP_TIMEOUT_MS           300000      // 5 minutes
#define WIFI_CONNECT_TIMEOUT_MS 15000       // 15 seconds

// =============================================================================
// Server & Download Configuration
// =============================================================================
#define SERVER_PORT_DEFAULT     8765
#define DOWNLOAD_TIMEOUT_MS     60000       // 60 seconds

// =============================================================================
// Default Configuration Values
// =============================================================================
#define DEFAULT_TZ_OFFSET       8           // UTC+8 (China Standard Time)
#define DEFAULT_REFRESH_HOUR    8           // 8:00 AM daily refresh

// =============================================================================
// Deep Sleep Configuration
// =============================================================================
#define DEEP_SLEEP_MIN_MINUTES  1           // Minimum sleep duration
#define DEEP_SLEEP_MAX_MINUTES  1440        // Maximum sleep duration (24 hours)

// =============================================================================
// NVS Storage Keys
// =============================================================================
#define NVS_NAMESPACE           "inktime"

// NVS keys for configuration
#define NVS_KEY_SSID            "ssid"
#define NVS_KEY_PASS            "pass"
#define NVS_KEY_HOSTPORT        "hostport"
#define NVS_KEY_TZ              "tz"
#define NVS_KEY_HOUR            "hour"
#define NVS_KEY_ROT180          "rot180"
#define NVS_KEY_LAST_DATE       "last_date"
#define NVS_KEY_LAST_EPOCH      "last_epoch"

// =============================================================================
// Built-in LED (for status indication)
// =============================================================================
#ifndef LED_BUILTIN
#define LED_BUILTIN             2
#endif

#endif // CONFIG_H
