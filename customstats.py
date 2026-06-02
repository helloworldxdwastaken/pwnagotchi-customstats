import logging
import os
import time
import socket

import pwnagotchi
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK


class CustomStats(plugins.Plugin):
    __author__ = 'info.dronx@gmail.com'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = ('Battery + memory on the left, and the last cracked Wi-Fi '
                       '(SSID + password) below the face.')

    def __init__(self):
        self._membat = '-'
        self._bat = None
        self._bat_ts = 0
        self._cracked = ''
        self._cracked_ts = 0
        self._cracked_mtime = -1

    # ---- battery -----------------------------------------------------------
    # PiSugar's battery gauge (IP5209 on the PiSugar 2) is only readable through
    # pisugar-server's tiny TCP protocol on :8423. We also try a direct PiSugar 3
    # register read as a bonus. If neither answers we just show '-' instead of
    # crashing the UI.
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
            if len(combined) > 38:
                avail = max(1, 38 - len(pw) - 2)
                combined = ('%s: %s' % (ssid[:avail], pw))[:38]
            self._cracked = combined
        else:
            self._cracked = ''
        return self._cracked

    # ---- hooks -------------------------------------------------------------
    def on_loaded(self):
        self._potfile = self.options.get('potfile',
                                         '/root/handshakes/wpa-sec.cracked.potfile')
        self._membat_pos = (int(self.options.get('membat_x', 0)),
                            int(self.options.get('membat_y', 78)))
        self._cracked_pos = (int(self.options.get('cracked_x', 0)),
                            int(self.options.get('cracked_y', 91)))
        logging.info('[customstats] loaded (potfile=%s)' % self._potfile)

    def on_ui_setup(self, ui):
        ui.add_element('cs_membat', Text(color=BLACK, value='MEM -% BAT -',
                                         position=self._membat_pos, font=fonts.Small))
        ui.add_element('cs_cracked', Text(color=BLACK, value='',
                                          position=self._cracked_pos, font=fonts.Small))

    def on_ui_update(self, ui):
        mem = int(pwnagotchi.mem_usage() * 100)
        membat = 'MEM %d%% BAT %s' % (mem, self._battery())
        cracked = self._last_cracked(self._potfile)
        with ui._lock:
            ui.set('cs_membat', membat)
            ui.set('cs_cracked', cracked)

    def on_unload(self, ui):
        with ui._lock:
            try:
                ui.remove_element('cs_membat')
                ui.remove_element('cs_cracked')
            except Exception:
                pass
        logging.info('[customstats] unloaded')
