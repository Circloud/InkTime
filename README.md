<div align="center">

# InkTime

**Your Best Memories, Resurfaced Daily.**

<img src="esp32/InkTime.jpeg" width="75%">

*AI-powered privacy-first e-ink photo frame that surfaces your buried memories, automatically.*

</div>

## Why InkTime

If you have thousands of photos on your phone or computer, you've probably experienced these problems:

- **Photo frames are static.** Once you put a photo in a frame, it stays there for months or years because swapping prints is tedious.
- **The best photos are buried.** Amid thousands of casual snapshots, the truly meaningful ones are lost, and no one has time to manually curate through a decade of photos.

InkTime solves both. It automatically surfaces your best memories and refreshes the display daily—no manual curation, no printing, no effort. Just a frame that shows you something worth seeing, every day.

## What It Does

InkTime doesn't randomly shuffle photos. Instead, it uses AI to understand your photo library and resurfaces meaningful memories:

- **AI-powered analysis**: Vision models analyze each photo, score it by "memory worthiness", and generate captions
- **On this day in history**: Daily selection shows photos from the same calendar date in past years
- **6-color e-ink display**: Photos are dithered for optimal quality on GDEP073E01 panels
- **Set and forget**: ESP32 wakes once daily, downloads the photo, refreshes display, returns to deep sleep
- **6+ month battery life**: Deep sleep draws <1mA with proper power design

## How It Works

```
Photos on disk
    ↓  photo_analyzer (VLM analysis)
SQLite database
    ↓  server (selection + dithering)
192KB binary
    ↓  HTTP download
ESP32-S3 → E-ink display → Deep sleep
```

## Hardware Requirements

### Required

| Component | Specification |
|-----------|---------------|
| MCU | ESP32-S3-WROOM-1-N8R8 (8MB Flash + 8MB PSRAM) |
| Display | 7.3" E6 6-color (GDEP073E01, 480×800) |
| Adapter | 50-pin e-ink adapter board |

**Important**: Generic ESP32-S3 devkits often lack PSRAM. The N8R8 variant is recommended for the image buffer.

### Optional

- Custom PCB design in `hardware/` folder
- Battery power (2× 18650 cells recommended)

### SPI Pins

| Signal | GPIO |
|--------|------|
| BUSY | 14 |
| RST | 13 |
| DC | 12 |
| CS | 11 |
| SCLK | 10 |
| DIN | 9 |
| Factory Reset | 38 (hold LOW at boot) |

## Quick Start

### 1. Software Setup

```bash
# Clone repository
git clone https://github.com/Circloud/InkTime.git
cd InkTime

# Install uv (if not already)
pip install uv

# Create configuration
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Required: VLM endpoint (OpenAI-compatible)
API_URL=http://127.0.0.1:1234/v1/chat/completions
MODEL_NAME=qwen3.5-4b

# Required: Photo library paths
SELECTION_MODE=date
IMAGE_DIRS=/path/to/your/photos

# Required: Display languages and fonts
DISPLAY_LANGUAGES=en,zh
FONT_PATH_ZH=./server/fonts/LXGWWenKaiLite-Medium.ttf
FONT_PATH_EN=./server/fonts/Lora-Medium.ttf
```

### 2. Analyze Photos

Ensure your VLM server (e.g., LM Studio) is running, then:

```bash
uv run photo_analyzer
```

This scans your photo library, calls the VLM for each photo, and stores results in SQLite. Resumable — run it multiple times as you add photos.

### 3. Start Server

```bash
uv run server
```

Server runs at `http://0.0.0.0:8765`. On first request each day, it selects and renders photos automatically.

### 4. Flash Firmware

```bash
cd firmware
pio run --target upload
pio device monitor  # View debug output
```

### 5. Configure ESP32

On first boot, the ESP32 enters AP mode:
- Connect to WiFi network `InkTime-xxxx` (password: `12345678`)
- Open http://192.168.4.1/ in browser
- Configure:
  - Your WiFi credentials
  - Server address (e.g., `192.168.1.100:8765`)
  - Daily refresh hour (0-23)
  - Timezone (-12 to +14)

The device will reboot, download today's photo, display it, and enter deep sleep.

## Configuration

### Selection Modes

| Mode | Behavior |
|------|----------|
| `date` | "On this day in history" — matches MM-DD from past years, falls back to nearby dates |
| `curated` | Sequential display of all photos in alphabetical order |

Set via `SELECTION_MODE=date` or `SELECTION_MODE=curated` in `.env`.

### Required Settings

| Setting | Description |
|---------|-------------|
| `API_URL` | VLM endpoint (OpenAI-compatible API) |
| `MODEL_NAME` | VLM model name |
| `IMAGE_DIRS` | Photo library paths (comma-separated) |
| `FONT_PATH_ZH` | Chinese font path (if `zh` in languages) |
| `FONT_PATH_EN` | English font path (if `en` in languages) |

See `.env.example` for all available settings including dithering algorithms, enhanced captions, and local area travel detection.

## Project Structure

```
InkTime/
├── photo_analyzer/    # VLM photo analysis
├── server/            # Flask server, dithering, selection
├── firmware/          # ESP32-S3 firmware (PlatformIO)
├── hardware/          # PCB design files
├── tests/             # pytest test suite
└── .env.example       # Configuration template
```

## Acknowledgments

- [GxEPD2](https://github.com/ZinggJM/GxEPD2) by ZinggJM — E-ink display driver (GPL-3.0)
- [epaper-dithering](https://github.com/OpenDisplay/epaper-dithering) — High-quality 6-color dithering (MIT)
- [GeoNames](https://www.geonames.org/) — City location database (CC BY 4.0)
- [LXGW WenKai Lite](https://github.com/lxgw/LxgwWenKai-Lite) by LXGW — Chinese font (OFL-1.1)
- [Lora](https://fonts.google.com/specimen/Lora) — English font (OFL-1.1)