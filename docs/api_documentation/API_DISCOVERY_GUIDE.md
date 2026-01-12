# API Discovery Guide

This guide walks you through the process of discovering the APIs used by the target mobile apps (Tager elSaada and Ben Soliman).

## Prerequisites

### Tools to Install

1. **Python Tools**
   ```bash
   pip install mitmproxy frida-tools objection
   ```

2. **Android Environment** (choose one)
   - Android Studio Emulator (with Google Play if apps require it)
   - Genymotion Emulator
   - Physical Android device (rooted recommended)

3. **Frida Server** (for SSL pinning bypass)
   - Download from: https://github.com/frida/frida/releases
   - Match your device architecture (arm64, arm, x86, x86_64)

---

## Step 1: Setup mitmproxy

1. **Start mitmproxy with web interface**
   ```bash
   mitmweb --listen-port 8080 --web-port 8081
   ```

2. **Access the web interface**
   - Open browser at: http://localhost:8081
   - You'll see all intercepted traffic here

3. **Note your computer's IP address**
   ```bash
   # Windows
   ipconfig

   # Linux/Mac
   ifconfig
   ```

---

## Step 2: Configure Android Device/Emulator

### Option A: Android Emulator (Recommended for beginners)

1. **Create emulator in Android Studio**
   - Device: Pixel 4 or similar
   - System Image: Android 11 (API 30) - Google APIs
   - Enable "Cold Boot" in settings

2. **Start emulator with writable system**
   ```bash
   emulator -avd YOUR_AVD_NAME -writable-system
   ```

### Option B: Physical Device (Rooted)

1. Enable Developer Options
2. Enable USB Debugging
3. Connect via ADB

### Configure Proxy

1. **On Android device:**
   - Go to Settings > WiFi
   - Long press on connected network
   - Modify network > Advanced options
   - Set Proxy to Manual
   - Proxy hostname: YOUR_COMPUTER_IP
   - Proxy port: 8080

2. **Install mitmproxy CA certificate**
   - On device browser, go to: http://mitm.it
   - Download the Android certificate
   - Install it (Settings > Security > Install from storage)

---

## Step 3: Bypass SSL Pinning

Most apps use SSL pinning to prevent traffic interception. We need to bypass this.

### Method 1: Frida + Universal Bypass Script (Recommended)

1. **Push Frida server to device**
   ```bash
   adb push frida-server /data/local/tmp/
   adb shell "chmod 755 /data/local/tmp/frida-server"
   ```

2. **Start Frida server**
   ```bash
   adb shell "su -c '/data/local/tmp/frida-server &'"
   ```

3. **Clone bypass scripts**
   ```bash
   git clone https://github.com/httptoolkit/frida-interception-and-unpinning
   cd frida-interception-and-unpinning
   ```

4. **Find app package names**
   ```bash
   # List installed packages
   adb shell pm list packages | grep -i tager
   adb shell pm list packages | grep -i soliman
   ```

5. **Run with SSL bypass**
   ```bash
   # For Tager elSaada
   frida -U -f com.tager.elsaada -l config.js --no-pause

   # For Ben Soliman
   frida -U -f com.bensoliman.app -l config.js --no-pause
   ```

### Method 2: Objection (Alternative)

1. **Connect to running app**
   ```bash
   objection -g com.tager.elsaada explore
   ```

2. **Disable SSL pinning**
   ```
   android sslpinning disable
   ```

---

## Step 4: Capture Traffic

1. **Start the app** with Frida bypass running
2. **Perform actions** in the app:
   - Login with your account
   - Browse categories
   - View products
   - Search for items
   - Check offers

3. **Watch mitmproxy** - you'll see all API calls

---

## Step 5: Document API Endpoints

For each app, document:

### Authentication
```
Endpoint: POST /api/v1/auth/login
Headers:
  - Content-Type: application/json
  - User-Agent: AppName/version (Android ...)
  - X-Device-Id: [device_id]
Request Body:
{
  "phone": "+20xxxxxxxxxx",
  "password": "user_password"
}
Response:
{
  "access_token": "eyJ...",
  "refresh_token": "abc...",
  "expires_in": 3600
}
```

### Categories
```
Endpoint: GET /api/v1/categories
Headers:
  - Authorization: Bearer [token]
Response:
{
  "data": [
    {"id": 1, "name": "Food", "name_ar": "طعام", ...}
  ]
}
```

### Products
```
Endpoint: GET /api/v1/products
Query Params:
  - page: int
  - limit: int
  - category_id: int (optional)
Headers:
  - Authorization: Bearer [token]
Response:
{
  "data": [...],
  "meta": {"total": 1000, "page": 1, "last_page": 20}
}
```

---

## Step 6: Update Scraper Code

Once you've documented the APIs, update these files:

### For Tager elSaada
File: `src/scrapers/tager_elsaada.py`

1. Update `BASE_URL` with actual API base URL
2. Update `ENDPOINTS` dictionary with actual paths
3. Update `authenticate()` method with actual login flow
4. Update `parse_product()` and `parse_category()` with actual field mappings

### For Ben Soliman
File: `src/scrapers/ben_soliman.py`

Same updates as above.

### Update Settings
File: `src/config/settings.py`

Update default base URLs:
```python
tager_elsaada_base_url: str = Field(
    default="https://actual-api-url.com",
)
```

---

## Tips for API Discovery

1. **Start with login** - authenticate first to see protected endpoints

2. **Note all headers** - apps often require specific headers:
   - Authorization (Bearer token)
   - Device-ID
   - App-Version
   - Platform
   - Custom headers (X-Api-Key, etc.)

3. **Check response structure** - note:
   - Data wrapper keys (data, items, results)
   - Pagination format (page/limit, cursor, offset)
   - Error format

4. **Test pagination** - scroll through lists to see how pagination works

5. **Export from mitmproxy** - you can export flows as HAR or JSON

---

## Troubleshooting

### "Connection refused" errors
- Check proxy settings on device
- Verify computer IP and port
- Ensure mitmproxy is running

### SSL errors after bypass
- Try different Frida script
- Check if app updated (might need new bypass)
- Try Method 2 (Objection)

### App crashes with Frida
- Check Frida server version matches frida-tools
- Try older Android version
- Use Genymotion instead of stock emulator

### Traffic not appearing
- Check certificate is installed correctly
- Some apps use certificate pinning - bypass needed
- Check if app uses non-HTTP protocols

---

## Security Notes

- Only use these techniques for authorized purposes
- Don't share discovered API credentials
- Respect rate limits to avoid account bans
- Store credentials securely (use encryption)

---

## Example mitmproxy Filters

```bash
# Show only specific host
~d api.tagerelsaada.com

# Show only JSON responses
~t application/json

# Show only POST requests
~m POST

# Combine filters
~d api.tagerelsaada.com & ~m POST
```

---

## Next Steps

After documenting APIs:

1. Update scraper code with actual endpoints
2. Test authentication with real credentials
3. Run a test scrape
4. Verify data is being stored correctly
5. Start scheduled scraping
