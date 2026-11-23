"""Time-based, interruptible UI motion. Only one callback per animation key."""
from __future__ import annotations

import time
import ctypes
import os
from functools import lru_cache


class FrameClock:
    """Request precise Windows wakeups only while there is active UI motion."""
    active = set()
    requested = False

    @classmethod
    def acquire(cls, key):
        if not cls.active and os.name == 'nt':
            cls.requested = ctypes.windll.winmm.timeBeginPeriod(1) == 0
        cls.active.add(key)

    @classmethod
    def release(cls, key):
        cls.active.discard(key)
        if not cls.active and cls.requested:
            ctypes.windll.winmm.timeEndPeriod(1)
            cls.requested = False

TIMING = {'hover': 120, 'press': 90, 'panel': 280, 'exit': 140, 'page': 300,
          'hero': 460, 'support': 260, 'stagger': 45, 'reduced': 140}


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 4


def easing(t, kind='out'):
    t = max(0.0, min(1.0, t))
    if kind == 'in':
        return t ** 3
    if kind == 'in_out':
        return t*t*(3-2*t)
    return ease_out(t)


def system_reduced_motion():
    if os.name != 'nt':
        return False
    enabled = ctypes.c_int(1)
    if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
        return not bool(enabled.value)
    return False


class Motion:
    def __init__(self, widget):
        self.widget = widget
        self.jobs = {}
        self.tokens = {}
        self.intervals = []
        widget.bind('<Destroy>', lambda event: self.clear() if event.widget is widget else None, add='+')

    def cancel(self, key):
        FrameClock.release((id(self), key))
        self.tokens[key] = self.tokens.get(key, 0) + 1
        callback = self.jobs.pop(key, None)
        if callback:
            try:
                self.widget.after_cancel(callback)
            except Exception:
                pass

    def clear(self):
        for key in list(self.tokens):
            self.cancel(key)

    def animate(self, key, duration, update, delay=0, complete=None, curve='out'):
        self.cancel(key)
        FrameClock.acquire((id(self), key))
        token = self.tokens[key]
        start = time.perf_counter() + delay / 1000
        previous = [None]

        def tick():
            if self.tokens.get(key) != token:
                return
            try:
                if not self.widget.winfo_exists():
                    self.cancel(key)
                    return
            except Exception:
                self.cancel(key)
                return
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed < 0:
                self.jobs[key] = self.widget.after(max(1, int(-elapsed)), tick)
                return
            progress = min(1.0, elapsed / max(1, duration))
            now = time.perf_counter()
            if previous[0] is not None:
                self.intervals.append((now-previous[0])*1000)
                self.intervals = self.intervals[-2000:]
            previous[0] = now
            try:
                update(easing(progress, curve))
            except Exception:
                self.cancel(key)
                raise
            if self.tokens.get(key) != token:
                return
            if progress < 1:
                self.jobs[key] = self.widget.after(16, tick)
            else:
                self.jobs.pop(key, None)
                FrameClock.release((id(self), key))
                if complete:
                    complete()

        self.jobs[key] = self.widget.after(max(0, delay), tick)


@lru_cache(maxsize=256)
def _oklab(color):
    rgb = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
    r,g,b = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    l = (.4122214708*r+.5363325363*g+.0514459929*b)**(1/3)
    m = (.2119034982*r+.6806995451*g+.1073969566*b)**(1/3)
    s = (.0883024619*r+.2817188376*g+.6299787005*b)**(1/3)
    return (.2104542553*l+.793617785*m-.0040720468*s,
            1.9779984951*l-2.428592205*m+.4505937099*s,
            .0259040371*l+.7827717662*m-.808675766*s)


def color_between(a, b, t):
    if t <= 0:
        return a
    if t >= 1:
        return b
    light,aa,bb = [x+(y-x)*t for x,y in zip(_oklab(a),_oklab(b))]
    l = (light+.3963377774*aa+.2158037573*bb)**3
    m = (light-.1055613458*aa-.0638541728*bb)**3
    s = (light-.0894841775*aa-1.291485548*bb)**3
    linear = (4.0767416621*l-3.3077115913*m+.2309699292*s,
              -1.2684380046*l+2.6097574011*m-.3413193965*s,
              -.0041960863*l-.7034186147*m+1.707614701*s)
    rgb = [12.92*v if v <= .0031308 else 1.055*v**(1/2.4)-.055 for v in linear]
    return '#' + ''.join(f'{round(max(0,min(1,v))*255):02x}' for v in rgb)
