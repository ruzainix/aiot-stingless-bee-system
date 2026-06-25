# NESTR Web Dashboard

This is a lightweight prototype dashboard for displaying live hive readings and condition alerts.

## Run Locally

Open `index.html` in a browser, or serve using:

```bash
python -m http.server 8080
```

## Configure

Edit `script.js`:

- Change `DEVICE_ID` if your ESP32 uses another hive ID.
- Change `API_BASE` to the Raspberry Pi IP address if needed.
