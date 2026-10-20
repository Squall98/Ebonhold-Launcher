# -*- coding: utf-8 -*-
"""Journal du launcher : %APPDATA%\\EbonholdLauncher\\launcher.log (1 Mo max, puis .1).

Sert au diagnostic quand un joueur signale un souci : demarrage, catalogue, installations,
pack et patch FR, mise a jour du launcher. Aucune donnee personnelle n'y est ecrite.
"""
import os
import threading
import time

from . import paths

_FILE = os.path.join(paths.data_dir(), "launcher.log")
_LOCK = threading.Lock()


def log(msg):
    line = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), str(msg).replace("\n", " ")[:500])
    with _LOCK:
        try:
            if os.path.exists(_FILE) and os.path.getsize(_FILE) > 1_000_000:
                os.replace(_FILE, _FILE + ".1")
            with open(_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass
