/**
 * @file display.h
 * @brief Display renderer for 7.3" E6 6-color e-ink display (GDEP073E01)
 *
 * Provides initialization, rendering, and power management functions
 * for the GxEPD2_730c_GDEP073E01 driver.
 *
 * Hardware: ESP32-S3-WROOM-1-N8R8 with 7.3" E6 6-color panel
 * Display: 480x800 portrait, 6 colors (B/W/Y/R/Blue/Green)
 */

#ifndef DISPLAY_H
#define DISPLAY_H

#include <SPI.h>
#include <GxEPD2_7C.h>
#include "config.h"

// =============================================================================
// Display Driver Instance
// =============================================================================
// GDEP073E01 driver for E6 6-color panel
// Template parameters: driver class, page height (HEIGHT/4 for memory efficiency)
static GxEPD2_7C<GxEPD2_730c_GDEP073E01, GxEPD2_730c_GDEP073E01::HEIGHT / 4> display(
    GxEPD2_730c_GDEP073E01(PIN_EPD_CS, PIN_EPD_DC, PIN_EPD_RST, PIN_EPD_BUSY)
);

// =============================================================================
// Helper: Get pixel color from 4bpp packed data
// =============================================================================
/**
 * @brief Extract 4-bit color index from packed byte array
 *
 * Data format: 4bpp packed row-major, high nibble = left pixel
 * Each row (480 pixels) packed into 240 bytes
 * Byte at y*240 + x/2 contains pixels at (x, y) and (x+1, y)
 *
 * @param data Pointer to 192KB image data (4bpp packed)
 * @param x X coordinate (0 to CANVAS_WIDTH-1)
 * @param y Y coordinate (0 to CANVAS_HEIGHT-1)
 * @return 4-bit color index (0-6)
 */
inline uint8_t get_pixel_color(const uint8_t* data, int x, int y) {
    // Calculate byte offset (row-major, 2 pixels per byte)
    int byte_offset = y * (CANVAS_WIDTH / 2) + x / 2;
    uint8_t byte_val = data[byte_offset];

    // Extract pixel from packed byte
    // High nibble = left pixel (even x), low nibble = right pixel (odd x)
    if (x % 2 == 0) {
        return (byte_val >> 4) & 0x0F;  // High nibble
    } else {
        return byte_val & 0x0F;         // Low nibble
    }
}

// =============================================================================
// Helper: Map color index to GxEPD2 color constant
// =============================================================================
/**
 * @brief Map color index to GxEPD2 color constant
 *
 * Color indices from Python renderer:
 *   0 = Black, 1 = White, 2 = Yellow, 3 = Red, 5 = Blue, 6 = Green
 *
 * GxEPD2 handles internal conversion to panel-native format via
 * GDEP073E01::_convert_to_native()
 *
 * @param colorIndex Color index (0-6)
 * @return GxEPD2 color constant
 */
inline uint16_t map_color(uint8_t colorIndex) {
    switch (colorIndex) {
        case 0: return GxEPD_BLACK;
        case 1: return GxEPD_WHITE;
        case 2: return GxEPD_YELLOW;
        case 3: return GxEPD_RED;
        case 5: return GxEPD_BLUE;
        case 6: return GxEPD_GREEN;
        default: return GxEPD_WHITE;
    }
}

// =============================================================================
// Main Functions
// =============================================================================

/**
 * @brief Initialize SPI bus and display
 *
 * - Initializes SPI with EPD pins
 * - Initializes display driver
 * - Sets rotation to 3 (180 degree rotation for portrait mode)
 */
inline void display_init() {
    DBG_PRINTLN("[DISPLAY] Initializing SPI bus...");

    // Initialize SPI bus with EPD pins
    SPI.end();
    SPI.begin(PIN_EPD_SCLK, -1, PIN_EPD_DIN, PIN_EPD_CS);

    DBG_PRINTLN("[DISPLAY] SPI initialized");
    DBG_PRINT("[DISPLAY]   SCLK="); DBG_PRINTLN(PIN_EPD_SCLK);
    DBG_PRINT("[DISPLAY]   MOSI=");  DBG_PRINTLN(PIN_EPD_DIN);
    DBG_PRINT("[DISPLAY]   CS=");    DBG_PRINTLN(PIN_EPD_CS);

    // Initialize display driver
    DBG_PRINTLN("[DISPLAY] Initializing display driver...");
    display.init(0, true, 2, false);

    // Set rotation to 3 (180 degree rotation, portrait mode)
    // Native: 800x480 landscape
    // Rotation 1: 480x800 portrait (normal)
    // Rotation 3: 480x800 portrait (180 degree rotated)
    display.setRotation(3);

    DBG_PRINT("[DISPLAY] Logical dimensions: ");
    DBG_PRINT(display.width());
    DBG_PRINT("x");
    DBG_PRINTLN(display.height());
    DBG_PRINTLN("[DISPLAY] Initialization complete");
}

/**
 * @brief Render 192KB 4bpp packed image data to display
 *
 * Uses paged drawing for memory efficiency.
 * Each page is rendered by iterating through all pixels.
 *
 * @param data Pointer to 192KB image data (4bpp packed, 480x800)
 */
inline void display_render(const uint8_t* data) {
    DBG_PRINTLN("[DISPLAY] Starting render...");
    DBG_PRINTLN("[DISPLAY] This may take a while (4bpp packed, paged mode)");

    display.setFullWindow();

    display.firstPage();
    do {
        for (int y = 0; y < CANVAS_HEIGHT; y++) {
            for (int x = 0; x < CANVAS_WIDTH; x++) {
                uint8_t colorIdx = get_pixel_color(data, x, y);
                display.drawPixel(x, y, map_color(colorIdx));
            }
        }
    } while (display.nextPage());

    DBG_PRINTLN("[DISPLAY] Render complete");
}

/**
 * @brief Put display into deep sleep mode
 *
 * Minimizes power consumption when display is not being updated.
 * The display retains the last image while in hibernate mode.
 */
inline void display_hibernate() {
    DBG_PRINTLN("[DISPLAY] Entering hibernate mode...");
    display.hibernate();
    DBG_PRINTLN("[DISPLAY] Display in deep sleep");
}

/**
 * @brief Set EPD pins to INPUT_PULLDOWN for power saving
 *
 * Call this before entering deep sleep to minimize power consumption.
 * Reduces current leakage through floating pins.
 */
inline void display_power_down_pins() {
    DBG_PRINTLN("[DISPLAY] Powering down EPD pins...");

    pinMode(PIN_EPD_BUSY, INPUT_PULLDOWN);
    pinMode(PIN_EPD_RST, INPUT_PULLDOWN);
    pinMode(PIN_EPD_DC, INPUT_PULLDOWN);
    pinMode(PIN_EPD_CS, INPUT_PULLDOWN);
    pinMode(PIN_EPD_SCLK, INPUT_PULLDOWN);
    pinMode(PIN_EPD_DIN, INPUT_PULLDOWN);

    DBG_PRINTLN("[DISPLAY] EPD pins set to INPUT_PULLDOWN");
}

#endif // DISPLAY_H
