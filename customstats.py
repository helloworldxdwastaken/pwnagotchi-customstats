import logging
import os
import time
import socket

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK


class CustomStats(plugins.Plugin):
    __author__ = 'info.dronx@gmail.com'
    __version__ = '1.2.0'
    __license__ = 'GPL3'
    __description__ = ('Adds a battery column just left of the memtemp readout, '
                       'and the last cracked Wi-Fi (SSID + password) below the face.')

    FIELD_WIDTH = 4   # match memtemp's column width so battery lines up as a 4th column
    CRACKED_MAX = 24  # keep the cracked line left of the memtemp column (x~155)

    def __init__(self):
        self._bat = None
        self._bat_ts = 0
        self._cracked = ''
        self._cracked_ts = 0
        self._cracked_mtime = -1

    def _pad(self, s):
        return ' ' * max(0, self.FIELD_WIDTH - len(s)) + s

    # ---- battery -----------------------------------------------------------
    # Battery % is resolved in this order:
    #   1. pisugar-server's TCP protocol on :8423 (if it happens to be installed)
    #   2. direct I2C read, no server needed:
    #        - PiSugar 3: battery % register @ 0x57
    #        - PiSugar 2: IP5209 gauge voltage @ 0x75, mapped to % via a
    #          discharge curve (the PiSugar 2 gauge only exposes voltage)
    # If nothing answers we show '-'.
    #
    # PiSugar 2 note: the IP5209 only powers up (and answers on I2C) while the
    # board is charging or running the Pi from the battery; if the Pi is fed
    # only through its own USB data port the gauge sleeps and we show '-'.

    # PiSugar 2 default discharge curve (battery volts -> charge %)
    _IP5209_CURVE = [
        (4.16, 100.0), (4.05, 95.0), (4.00, 80.0), (3.92, 65.0),
        (3.86, 40.0), (3.79, 25.0), (3.66, 10.0), (3.52, 6.5),
        (3.49, 3.2), (3.10, 0.0),
    ]

    @staticmethod
    def _volts_to_pct(volts, curve):
        if volts >= curve[0][0]:
            return 100
        if volts <= curve[-1][0]:
            return 0
        for i in range(len(curve) - 1):
            v1, p1 = curve[i]
            v2, p2 = curve[i + 1]
            if v2 <= volts <= v1:
                return int(round(p2 + (volts - v2) * (p1 - p2) / (v1 - v2)))
        return 0

    @staticmethod
    def _read_ip5209_volts(bus):
        # IP5209 battery voltage from two registers (0xa2 low, 0xa3 high)
        low = bus.read_byte_data(0x75, 0xa2)
        high = bus.read_byte_data(0x75, 0xa3)
        if high & 0x20:
            raw = ((high | 0xc0) << 8) + low
            if raw > 32767:
                raw -= 65536
        else:
            raw = ((high & 0x1f) << 8) + low
        return (2600.0 + raw * 0.26855) / 1000.0
    def _read_pisugar_server(self):
        try:
            s = socket.create_connection(('127.0.0.1', 8423), timeout=0.4)
            try:
                s.sendall(b'get battery\n')
                data = s.recv(64).decode('utf-8', 'ignore')
            finally:
                s.close()
            for tok in data.replace('\n', ' ').split():
                try:
                    return int(round(float(tok)))
                except ValueError:
                    continue
        except Exception:
            return None
        return None

    def _read_i2c(self):
        try:
            try:
                from smbus2 import SMBus
            except Exception:
                from smbus import SMBus
            bus = SMBus(1)
        except Exception:
            return None
        try:
            # PiSugar 3: battery % is a direct register at 0x57
            try:
                pct = bus.read_byte_data(0x57, 0x2a)
                if 0 <= pct <= 100:
                    return int(pct)
            except Exception:
                pass
            # PiSugar 2: IP5209 gauge at 0x75 exposes voltage -> map to %
            try:
                volts = self._read_ip5209_volts(bus)
                if 2.5 <= volts <= 4.5:
                    return self._volts_to_pct(volts, self._IP5209_CURVE)
            except Exception:
                pass
        finally:
            try:
                bus.close()
            except Exception:
                pass
        return None

    def _battery(self):
        now = time.time()
        if now - self._bat_ts < 30 and self._bat is not None:
            return self._bat
        self._bat_ts = now
        pct = self._read_pisugar_server()
        if pct is None:
            pct = self._read_i2c()
        self._bat = ('%d%%' % pct) if pct is not None else '-'
        return self._bat

    # ---- last cracked wifi -------------------------------------------------
    def _last_cracked(self, potfile):
        now = time.time()
        if now - self._cracked_ts < 10:
            return self._cracked
        self._cracked_ts = now
        try:
            mtime = os.path.getmtime(potfile)
        except OSError:
            self._cracked = ''
            return self._cracked
        if mtime == self._cracked_mtime:
            return self._cracked
        self._cracked_mtime = mtime
        last = ''
        try:
            with open(potfile, 'r', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = line
        except OSError:
            self._cracked = ''
            return self._cracked
        # wpa-sec.cracked.potfile format: bssid:station:ssid:password
        parts = last.split(':')
        if len(parts) >= 4:
            ssid = parts[2]
            pw = ':'.join(parts[3:])
            combined = '%s: %s' % (ssid, pw)
            if len(combined) > self._cracked_max:
                avail = max(1, self._cracked_max - len(pw) - 2)
                combined = ('%s: %s' % (ssid[:avail], pw))[:self._cracked_max]
            self._cracked = combined
        else:
            self._cracked = ''
        return self._cracked

    # ---- hooks -------------------------------------------------------------
    def on_loaded(self):
        self._potfile = self.options.get('potfile',
                                         '/root/handshakes/wpa-sec.cracked.potfile')
        # default sits one 4-char column left of memtemp's (155, 76) on a 250x122 V3
        self._bat_pos = (int(self.options.get('bat_x', 125)),
                         int(self.options.get('bat_y', 76)))
        self._cracked_pos = (int(self.options.get('cracked_x', 0)),
                             int(self.options.get('cracked_y', 91)))
        self._cracked_max = int(self.options.get('cracked_max', self.CRACKED_MAX))
        logging.info('[customstats] loaded (potfile=%s)' % self._potfile)

    def on_ui_setup(self, ui):
        x, y = self._bat_pos
        ui.add_element('cs_bat_label', Text(color=BLACK, value=self._pad('bat'),
                                            position=(x, y), font=fonts.Small))
        ui.add_element('cs_bat', Text(color=BLACK, value=self._pad('-'),
                                      position=(x, y + 10), font=fonts.Small))
        ui.add_element('cs_cracked', Text(color=BLACK, value='',
                                          position=self._cracked_pos, font=fonts.Small))

    def on_ui_update(self, ui):
        bat = self._pad(self._battery())
        cracked = self._last_cracked(self._potfile)
        with ui._lock:
            ui.set('cs_bat', bat)
            ui.set('cs_cracked', cracked)

    def on_unload(self, ui):
        with ui._lock:
            for key in ('cs_bat_label', 'cs_bat', 'cs_cracked'):
                try:
                    ui.remove_element(key)
                except Exception:
                    pass
        logging.info('[customstats] unloaded')
