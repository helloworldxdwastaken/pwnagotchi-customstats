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
    __version__ = '1.1.0'
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
    # PiSugar's gauge (IP5209 on the PiSugar 2) is only readable through
    # pisugar-server's TCP protocol on :8423. A direct PiSugar 3 register read
    # (0x57) is tried as a fallback. If neither answers we show '-'.
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
            import smbus
            bus = smbus.SMBus(1)
            try:
                pct = bus.read_byte_data(0x57, 0x2a)  # PiSugar 3 battery %
                if 0 <= pct <= 100:
                    return int(pct)
            except Exception:
                pass
        except Exception:
            return None
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
