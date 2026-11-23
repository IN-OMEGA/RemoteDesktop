"""Native, time-driven brand reveal; no web player or network dependency."""
from __future__ import annotations

import math
import tkinter as tk
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from nexus_repacks.motion import Motion, color_between

BACKGROUND = '#080f16'
ACCENT = '#adefff'


def partial_path(points, progress):
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    remaining = sum(lengths) * max(0, min(1, progress))
    result = [points[0]]
    for a, b, length in zip(points, points[1:], lengths):
        t = min(1, remaining / length) if length else 1
        result.append((a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t))
        remaining -= length
        if remaining <= 0:
            break
    return [v for point in result for v in point]


class BrandIntro(tk.Canvas):
    def __init__(self, owner, reduced=False, on_complete=None):
        super().__init__(owner, bg=BACKGROUND, highlightthickness=0, bd=0)
        self.motion = Motion(self)
        self.reduced = reduced
        self.finished = False
        self.on_complete = on_complete
        self.progress = 1.0 if reduced else 0.0
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.tk.call('raise', self._w)
        self.bind('<Configure>', lambda e: self.draw(self.progress))
        self.bind('<Button-1>', lambda e: self.finish())
        glow = Image.new('RGBA', (480, 480))
        d = ImageDraw.Draw(glow)
        d.ellipse((100, 100, 380, 380), fill=(109, 219, 255, 34))
        d.ellipse((175, 175, 305, 305), fill=(183, 244, 255, 36))
        self.glow = ImageTk.PhotoImage(glow.filter(ImageFilter.GaussianBlur(55)))
        self._hold_job = None
        self._start_job = self.after(20, self.start)

    def start(self):
        self._start_job = None
        self.motion.animate('reveal', 140 if self.reduced else 1550, self.draw,
                            complete=self.hold, curve='in_out')

    def hold(self):
        self._hold_job = self.after(80 if self.reduced else 120, self.finish)

    def draw(self, t):
        if self.finished:
            return
        self.progress = t
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        cx, cy = w/2, h/2-45
        self.create_image(cx, cy, image=self.glow)
        self.create_oval(cx-95, cy-95, cx+95, cy+95, outline='#19303c', width=1)
        p = 1 if self.reduced else min(1, t*1.45)
        points = [(cx-36, cy+40), (cx-36, cy-40), (cx+36, cy+40), (cx+36, cy-40)]
        coordinates = partial_path(points, p)
        if len(coordinates) >= 4:
            self.create_line(*coordinates, fill='#214754', width=14, capstyle='round', joinstyle='round')
            self.create_line(*coordinates, fill=ACCENT, width=4, capstyle='round', joinstyle='round')
        opacity = 1 if self.reduced else max(0, min(1, (t-.35)/.4))
        self.create_text(cx, cy+145, text='N E X U S', fill=color_between(BACKGROUND, '#effbff', opacity),
                         font=('Segoe UI', 29, 'bold'))
        self.create_text(cx, cy+188, text='R E P A C K S', fill=color_between(BACKGROUND, ACCENT, opacity), font=('Segoe UI', 10))
        self.create_text(cx, h-60, text='Click to enter', fill='#75939f', font=('Segoe UI', 10))

    def finish(self):
        if self.finished:
            return
        self.finished = True
        self.motion.clear()
        for job in (self._start_job, self._hold_job):
            if job:
                self.after_cancel(job)
        owner = self.master
        if not self.reduced:
            owner.attributes('-alpha', 0)
        self.destroy()
        if not self.reduced and getattr(owner, 'motion', None):
            # Separate lifetime: a tab change must not strand window opacity midway.
            old = getattr(owner, '_startup_motion', None)
            if old:
                old.clear()
            owner._startup_motion = Motion(owner)
            owner._startup_motion.animate('launch-window', 240, lambda t: owner.attributes('-alpha', t),
                                         complete=self.on_complete)
        elif self.on_complete:
            self.on_complete()
