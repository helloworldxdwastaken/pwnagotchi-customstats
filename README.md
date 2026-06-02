# pwnagotchi-customstats

A small [pwnagotchi](https://github.com/jayofelony/pwnagotchi) UI plugin that adds two things to the screen:

- **Battery + memory** together on the left.
- **The last cracked Wi-Fi** (SSID + password) below the face.

![screenshot](screenshot.png)

*(the cracked line above shows a demo entry; it stays blank until something actually cracks)*

## How it works

- **Memory** comes from pwnagotchi itself (`pwnagotchi.mem_usage()`).
- **Battery** is read from [`pisugar-server`](https://github.com/PiSugar/pisugar-power-manager-rs) over its local TCP port `8423`, with a direct PiSugar 3 I2C read (`0x57`) as a fallback. If neither answers it just shows `-` instead of crashing the UI. (A bare PiSugar 2's gauge is only reachable through `pisugar-server`, so install that if you want a real %.)
- **Last cracked Wi-Fi** is read from the [`wpa-sec`](https://wpa-sec.stanev.org/) plugin's results file (`/root/handshakes/wpa-sec.cracked.potfile`, format `bssid:station:ssid:password`). The most recent line is shown. The line is blank until that file has an entry.

## Install

1. Copy the plugin into your custom-plugins folder (path is whatever `main.custom_plugins` points to in your config — default below):

   ```bash
   scp customstats.py pi@10.0.0.2:/tmp/
   ssh pi@10.0.0.2 'sudo mkdir -p /etc/pwnagotchi/custom-plugins && sudo mv /tmp/customstats.py /etc/pwnagotchi/custom-plugins/'
   ```

2. Enable it in `/etc/pwnagotchi/config.toml`:

   ```toml
   main.plugins.customstats.enabled = true
   ```

   (If you also run the `memtemp` plugin you may want to disable it, since this shows memory too and they can overlap.)

3. Restart:

   ```bash
   sudo systemctl restart pwnagotchi
   ```

## Options

All optional — sensible defaults are tuned for the Waveshare 2.13" V3 (250×122). Override in `config.toml` to reposition for other displays:

```toml
main.plugins.customstats.potfile   = "/root/handshakes/wpa-sec.cracked.potfile"
main.plugins.customstats.membat_x  = 0
main.plugins.customstats.membat_y  = 78
main.plugins.customstats.cracked_x = 0
main.plugins.customstats.cracked_y = 91
```

## Note on use

The cracked-Wi-Fi line just displays results produced by the `wpa-sec` plugin. Only capture and crack handshakes for networks you own or are explicitly authorized to test.

## License

GPL-3.0, matching pwnagotchi.
