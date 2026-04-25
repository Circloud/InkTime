/**
 * @file downloader.h
 * @brief HTTP downloader for photo data from InkTime server
 *
 * Downloads 192KB 4bpp packed binary from server endpoint GET /api/photo/<index>
 * Allocates buffer in PSRAM for large image data.
 */

#ifndef DOWNLOADER_H
#define DOWNLOADER_H

#include <HTTPClient.h>
#include <WiFiClient.h>
#include "config.h"
#include "nvs_manager.h"

/**
 * @brief Download photo binary from server
 *
 * @param cfg Device configuration containing server_host and photo_index
 * @param buffer Output pointer to receive allocated buffer (allocated in PSRAM)
 * @return true on successful download with valid size, false on failure
 *
 * On success:
 *   - *buffer points to PSRAM-allocated memory containing IMAGE_SIZE_BYTES
 *   - Caller is responsible for freeing the buffer
 *
 * On failure:
 *   - *buffer is set to nullptr
 *   - Any allocated memory is freed
 */
inline bool download_photo(const DeviceConfig& cfg, uint8_t** buffer) {
    // Initialize output
    *buffer = nullptr;

    // Validate server host
    if (cfg.server_host.length() == 0) {
        DBG_PRINTLN("[DL] Error: Server host not configured");
        return false;
    }

    // Build URL
    String url;
    if (cfg.server_host.startsWith("http://") || cfg.server_host.startsWith("https://")) {
        url = cfg.server_host;
    } else {
        url = "http://" + cfg.server_host;
    }
    url += "/api/photo/" + String(cfg.photo_index);

    DBG_PRINT("[DL] Downloading from: ");
    DBG_PRINTLN(url);

    // Allocate buffer in PSRAM
    uint8_t* buf = (uint8_t*)ps_malloc(IMAGE_SIZE_BYTES);
    if (buf == nullptr) {
        DBG_PRINTLN("[DL] Error: Failed to allocate PSRAM buffer");
        return false;
    }

    // Perform HTTP GET
    HTTPClient http;
    WiFiClient client;

    http.begin(client, url);
    http.setTimeout(DOWNLOAD_TIMEOUT_MS);

    int httpCode = http.GET();

    if (httpCode != HTTP_CODE_OK) {
        DBG_PRINT("[DL] Error: HTTP code ");
        DBG_PRINTLN(httpCode);
        http.end();
        free(buf);
        return false;
    }

    // Check Content-Length if available
    int contentLength = http.getSize();
    if (contentLength > 0 && contentLength != IMAGE_SIZE_BYTES) {
        DBG_PRINT("[DL] Error: Content-Length mismatch, expected ");
        DBG_PRINT(IMAGE_SIZE_BYTES);
        DBG_PRINT(", got ");
        DBG_PRINTLN(contentLength);
        http.end();
        free(buf);
        return false;
    }

    // Download data
    WiFiClient* stream = http.getStreamPtr();
    size_t totalRead = 0;
    size_t bytesRead;

    while (totalRead < IMAGE_SIZE_BYTES && client.connected()) {
        bytesRead = stream->readBytes((char*)(buf + totalRead), IMAGE_SIZE_BYTES - totalRead);
        totalRead += bytesRead;

        // Check for timeout (no data received)
        if (bytesRead == 0) {
            delay(10);  // Small delay before retry
        }
    }

    http.end();

    // Validate downloaded size
    if (totalRead != IMAGE_SIZE_BYTES) {
        DBG_PRINT("[DL] Error: Download size mismatch, expected ");
        DBG_PRINT(IMAGE_SIZE_BYTES);
        DBG_PRINT(", got ");
        DBG_PRINTLN(totalRead);
        free(buf);
        return false;
    }

    DBG_PRINT("[DL] Success: Downloaded ");
    DBG_PRINT(totalRead);
    DBG_PRINTLN(" bytes");

    *buffer = buf;
    return true;
}

#endif // DOWNLOADER_H
