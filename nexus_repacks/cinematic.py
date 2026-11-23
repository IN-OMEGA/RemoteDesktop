"""Cinematic native UI. The downloader and security gate remain in app.Nexus."""
from __future__ import annotations

import math
import time
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageTk

from nexus_repacks import app as base
from nexus_repacks import library
from nexus_repacks.motion import Motion, color_between, TIMING, system_reduced_motion

INK = '#080f16'
SURFACE = '#101e29'
TEXT = '#effbff'
DIM = '#9bb7c5'
ICE = '#bdefff'
LIME = '#adefff'  # Historical name kept for the existing action components.

# Keep inherited functional screens in the same palette.
base.BG = INK
base.PANEL = SURFACE
base.BLUE = '#adefff'
base.MUTED = DIM


class AnimatedDialog(ctk.CTkToplevel):
    def __init__(self, owner, title, width, height):
        super().__init__(owner)
        # Alpha hides initial layout without interfering with CTk's Windows title-bar remap.
        self.attributes('-alpha', 0)
        self.geometry(f'{width}x{height}')
        self.title(title)
        self.configure(fg_color=INK)
        self.resizable(False, False)
        self.transient(owner)
        self.motion = Motion(self)
        self._closing = False
        self.target_width, self.target_height = width, height
        self.attributes('-alpha', 0)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.after(30, self.reveal)

    def reveal(self):
        if self._closing:
            return
        self.update_idletasks()
        reduced = getattr(self.master, 'reduced_motion', False)
        x = self.master.winfo_rootx() + (self.master.winfo_width() - self.target_width) // 2
        y = self.master.winfo_rooty() + (self.master.winfo_height() - self.target_height) // 2
        y = max(35, y)
        travel = 0 if reduced else 18
        self.geometry(f'{self.target_width}x{self.target_height}+{x}+{y+travel}')
        self.deiconify()
        self.lift()
        self.update_idletasks()
        # Freeze the already measured layout, then slide rows in with staggered timing.
        measured = []
        for child in self.winfo_children():
            if child.winfo_manager() == 'pack':
                measured.append((child, child.winfo_x(), child.winfo_y(), child.winfo_width(), child.winfo_height()))
        for child, cx, cy, cw, ch in measured:
            child.pack_forget()
            scale = child._get_widget_scaling() if hasattr(child, '_get_widget_scaling') else 1
            child.configure(width=round(cw/scale), height=round(ch/scale))
        def move(t):
            self.attributes('-alpha', t)
            self.geometry(f'{self.target_width}x{self.target_height}+{x}+{round(y+travel*(1-t))}')
        self.motion.animate('window', TIMING['reduced'] if reduced else TIMING['panel'], move, complete=self.deiconify)
        for i, (child, cx, cy, cw, ch) in enumerate(measured):
            scale = child._get_widget_scaling() if hasattr(child, '_get_widget_scaling') else 1
            cx, cy = cx/scale, cy/scale
            foreground = child.cget('fg_color') if isinstance(child, ctk.CTkButton) else None
            text_color = child.cget('text_color') if isinstance(child, (ctk.CTkButton, ctk.CTkLabel)) else None
            def reveal_row(t, w=child, a=cx, b=cy, width=cw, height=ch, fg=foreground, text=text_color):
                w.place(x=round(a+(0 if reduced else 16)*(1-t)), y=b)
                if isinstance(fg, str) and fg.startswith('#'):
                    w.configure(fg_color=color_between(INK, fg, t))
                if isinstance(text, str) and text.startswith('#'):
                    w.configure(text_color=color_between(INK, text, t))
            self.motion.animate(f'row-{i}', TIMING['reduced'] if reduced else 240, reveal_row,
                                delay=0 if reduced else 30+min(i, 9)*40)

    def destroy(self):
        if self._closing:
            return
        self._closing = True
        for child in self.winfo_children():
            if isinstance(child, ctk.CTkButton):
                child.configure(state='disabled')
        self.motion.clear()
        try:
            alpha = float(self.attributes('-alpha'))
        except Exception:
            alpha = 1
        self.motion.animate('close', TIMING['exit'], lambda t: self.attributes('-alpha', alpha * (1-t)),
                            complete=lambda: super(AnimatedDialog, self).destroy(), curve='in')


class CinematicNexus(base.Nexus):
    def __init__(self, smoke=False):
        self.motion = None
        self.scene = None
        self.scene_generation = 0
        self.art_cache = {}
        self.background_cache = {}
        self.background_current = None
        self.background_photo = None
        self.scene_photos = []
        self._scene_size = (0, 0)
        self._resize_job = None
        self._nav = {}
        self._page_idle = None
        self._navigation_active = False
        self._pending_page = None
        self._active_dialog = None
        self._click_times = {}
        self._last_game_step = 0
        self.reduced_motion = system_reduced_motion()
        super().__init__(smoke=smoke)
        self.motion = Motion(self)
        mode = self.settings.get('reduced_motion')
        self.reduced_motion = system_reduced_motion() if mode is None else bool(mode)
        self.configure(fg_color=INK)
        self.content.configure(fg_color=INK)
        self.content.pack_propagate(False)
        self.page_host.grid_configure(column=1, padx=(14, 32))
        self.footer_bar.grid_configure(column=1, padx=(20, 32))
        self.build_topbar()
        self.footer.configure(text_color='#697b96', font=('Segoe UI', 10))
        self.motion_button = ctk.CTkButton(self.footer_bar, text='', command=self.cycle_motion,
            width=170, height=28, fg_color='#142137', hover_color='#253b5b', font=('Segoe UI', 10), corner_radius=8)
        self.motion_button.pack(side='right', padx=(15, 0))
        self.bind('<F8>', lambda event: self.cycle_motion())
        self.refresh_motion_label()
        self.after(2000, self.poll_motion_preference)
        self.after(80, self.page_enter)
        if not smoke:
            self.attributes('-alpha', 0)
            self.after(40, self.show_intro)

    def show_intro(self):
        from nexus_repacks.intro import BrandIntro
        if getattr(self, '_intro', None) and self._intro.winfo_exists():
            return
        try:
            self._intro = BrandIntro(self, self.reduced_motion, on_complete=self.page_enter)
        finally:
            self.attributes('-alpha', 1)

    def build_topbar(self):
        top = ctk.CTkFrame(self, fg_color=INK, corner_radius=0, height=76)
        top.grid(row=0, column=1, sticky='ew', padx=(20, 32), pady=(24, 18))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text='Your next world starts here.', text_color=DIM,
                     font=('Segoe UI', 13), anchor='w').grid(row=0, column=0, sticky='w')
        self._button(top, '＋  Add a game', self.import_menu, width=160).grid(row=0, column=1, padx=(15, 10))
        ctk.CTkButton(top, text='⛶', width=42, height=42, command=self.toggle_fullscreen,
                     fg_color=SURFACE, hover_color='#294755', text_color=ICE, corner_radius=12).grid(row=0, column=2)

    def _button(self, parent, text, command, primary=False, **kw):
        key = str(parent)+'/'+text
        return ctk.CTkButton(parent, text=text,
            command=lambda: self.guarded_action(key, command, parent), height=44,
            fg_color=LIME if primary else '#1a263b', text_color=INK if primary else TEXT,
            hover_color='#d7f8ff' if primary else '#27414e', corner_radius=12,
            border_width=0 if primary else 1, border_color='#2a3a53',
            font=('Segoe UI', 13, 'bold'), **kw)

    def _build_header(self):
        self.grid_columnconfigure(0, weight=0, minsize=218)
        self.grid_columnconfigure(1, weight=1)
        bar = ctk.CTkFrame(self, fg_color='#0d1922', width=194, corner_radius=22, border_width=1, border_color='#203540')
        bar.grid(row=0, column=0, rowspan=3, sticky='nsew', padx=(18, 14), pady=18)
        bar.grid_propagate(False)
        bar.pack_propagate(False)
        mark = tk.Canvas(bar, width=56, height=56, bg='#0d1922', highlightthickness=0)
        mark.create_oval(1,1,55,55,fill='#1b3946',outline='#335c6b')
        mark.create_line(17,40,17,16,39,40,39,16,fill='#37606e',width=8,capstyle='round',joinstyle='round')
        mark.create_line(17,40,17,16,39,40,39,16,fill=LIME,width=2.5,capstyle='round',joinstyle='round')
        mark.pack(anchor='w', padx=22, pady=(28, 15))
        ctk.CTkLabel(bar, text='N E X U S', font=('Segoe UI', 19, 'bold'), text_color=TEXT).pack(anchor='w', padx=22)
        ctk.CTkLabel(bar, text='R E P A C K S', font=('Segoe UI', 9), text_color=ICE).pack(anchor='w', padx=24, pady=(0, 42))
        ctk.CTkLabel(bar, text='PERSONAL SPACE', text_color='#7996a5', font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=24, pady=(0, 14))
        for text, page in (('▦   Library', 'library'), ('▧   Catalog', 'catalog'), ('↓   Downloads', 'downloads'), ('◇   Protection', 'protection')):
            button = ctk.CTkButton(bar, text=text, command=lambda p=page: self.request_page(p), width=162,
                 height=46, fg_color='transparent', hover_color='#203b48', text_color=DIM, anchor='w',
                 font=('Segoe UI', 12, 'bold'), corner_radius=12)
            button.pack(padx=16, pady=5)
            self._nav[page] = button
        ctk.CTkLabel(bar, text='A U R O R A   /   ' + '.'.join(base.APP_VERSION.split('.')[:2]) + '\n\nF11  Fullscreen\nF8   Animations', justify='left', text_color='#849fab',
                     font=('Segoe UI', 10)).pack(side='bottom', anchor='w', padx=24, pady=28)

    def nav_state(self):
        for name, button in self._nav.items():
            button.configure(fg_color='#243f4b' if name == self.current_page else 'transparent',
                             text_color=ICE if name == self.current_page else DIM,
                             text_color_disabled=ICE,
                             state='disabled' if name == self.current_page else 'normal')

    def popup_active(self):
        popup = self._active_dialog
        return popup if popup and popup.winfo_exists() and not popup._closing else None

    def guarded_action(self, key, action, owner=None):
        if self._update_notice:
            self._update_notice.show()
            return
        popup = self.popup_active()
        if popup and (owner is None or owner.winfo_toplevel() is not popup):
            popup.lift()
            return
        if owner is not None and getattr(owner.winfo_toplevel(), '_closing', False):
            return
        now = time.monotonic()
        if now-self._click_times.get(key, -100) < .4:
            return
        self._click_times[key] = now
        action()

    def request_page(self, page):
        if self.popup_active():
            self.popup_active().lift()
            return
        if self._navigation_active:
            self._pending_page = page
            return
        if self.current_page == page:
            return
        self._pending_page = page
        self._navigation_active = True
        def leave(t):
            self.content.place_configure(x=round((0 if self.reduced_motion else -12)*t))
        def commit():
            target, self._pending_page = self._pending_page or page, None
            self._navigation_active = False
            if target == self.current_page:
                self.page_enter()
            else:
                {'library': self.show_library, 'catalog': self.show_catalog, 'downloads': self.show_downloads, 'protection': self.show_protection}[target]()
        self.motion.animate('page-exit', 90 if self.reduced_motion else 120, leave, complete=commit, curve='in')

    def clear(self):
        self.scene_generation += 1
        if self.scene and self.scene.winfo_exists():
            self.scene.bindtags(())
        if self._page_idle:
            self.after_cancel(self._page_idle)
            self._page_idle = None
        if self.motion:
            self.motion.clear()
        if self._resize_job:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        self.scene = None
        self.scene_photos = []
        self.content.place_configure(x=0, y=0)
        super().clear()
        if self.motion:
            self.motion.clear()

    def page_enter(self):
        self.nav_state()
        if not self.motion:
            return
        self._navigation_active = True
        def slide(t):
            self.content.place_configure(x=round((0 if self.reduced_motion else 18)*(1-t)))
        def complete():
            self._navigation_active = False
            pending, self._pending_page = self._pending_page, None
            if pending and pending != self.current_page:
                self.after_idle(lambda: self.request_page(pending))
        self.motion.animate('page', TIMING['reduced'] if self.reduced_motion else TIMING['page'], slide, complete=complete)

    def refresh_motion_label(self):
        mode = self.settings.get('reduced_motion')
        label = ('Auto · ' if mode is None else '') + ('reduced motion' if self.reduced_motion else 'standard motion')
        self.motion_button.configure(text=label+'  F8')

    def apply_motion_mode(self):
        mode = self.settings.get('reduced_motion')
        selected = system_reduced_motion() if mode is None else bool(mode)
        changed = selected != self.reduced_motion
        self.reduced_motion = selected
        self.refresh_motion_label()
        if changed:
            self.motion.clear()
            self._navigation_active = False
            pending, self._pending_page = self._pending_page, None
            self.content.place_configure(x=0)
            if self.current_page == 'library':
                self.render_scene(entrance=False)
            if pending and pending != self.current_page:
                self.after_idle(lambda: self.request_page(pending))

    def cycle_motion(self):
        current = self.settings.get('reduced_motion')
        self.settings['reduced_motion'] = False if current is None else True if current is False else None
        library.atomic_json(library.STATE/'settings.json', self.settings)
        self.apply_motion_mode()

    def poll_motion_preference(self):
        if self.settings.get('reduced_motion') is None:
            self.apply_motion_mode()
        self.after(2000, self.poll_motion_preference)

    def show_downloads(self):
        super().show_downloads()
        self.page_enter()

    def show_catalog(self):
        super().show_catalog()
        self.page_enter()

    def show_protection(self, game=None):
        super().show_protection(game)
        self.page_enter()

    def show_library(self):
        self.current_page = 'library'
        self.clear()
        self.card_widgets = {}
        self.scene = tk.Canvas(self.content, bg=INK, highlightthickness=0, bd=0)
        self.scene.pack(fill='both', expand=True)
        self.scene.bind('<Configure>', self.resize_scene)
        self.scene.bind('<MouseWheel>', lambda event: 'break')
        games = self.visible_games()
        if games:
            self.selected = next((g for g in games if self.selected and self.selected.id == g.id), games[0])
        canvas = self.scene
        def initial_render():
            self._page_idle = None
            if self.current_page == 'library' and self.scene is canvas:
                self.render_scene(entrance=True)
        self._page_idle = self.after_idle(initial_render)
        self.page_enter()

    def resize_scene(self, event):
        if event.widget is not self.scene or self.current_page != 'library':
            return
        size = (event.width, event.height)
        if size == self._scene_size:
            return
        self._scene_size = size
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(100, self.finish_resize)

    def finish_resize(self):
        self._resize_job = None
        if self.current_page == 'library':
            self.render_scene(entrance=False)

    def artwork(self, game):
        if not game:
            return None
        path = game.image
        if not path or not Path(path).is_file():
            path = library.local_image(game) if game.root else ''
            if path:
                game.image = path
        if path in self.art_cache:
            return self.art_cache[path]
        try:
            with Image.open(path) as source:
                source.load()
                image = source.convert('RGB')
                image.thumbnail((1600, 1600))
                self.art_cache[path] = image.copy()
                return self.art_cache[path]
        except Exception:
            return None

    def make_background(self, game, width, height):
        key = (game.id if game else '', width, height, game.image if game else '')
        if key in self.background_cache:
            return self.background_cache[key]
        # Frost and light are rasterized once; never blur large surfaces per frame.
        image = Image.new('RGB', (width, height), INK)
        glow = Image.new('RGB', (max(1,width//3), max(1,height//3)), INK)
        gd = ImageDraw.Draw(glow)
        gw, gh = glow.size
        gd.ellipse((gw*.25, -gh*.2, gw*1.2, gh*.8), fill='#163746')
        image = glow.filter(ImageFilter.GaussianBlur(45)).resize((width,height), Image.Resampling.BILINEAR)
        draw = ImageDraw.Draw(image)
        bottom = height-228
        draw.rounded_rectangle((2, 88, width-3, bottom), radius=24, fill='#10212c', outline='#294754', width=1)
        art = self.artwork(game)
        x, y = round(width*.52), 104
        aw, ah = width-x-18, max(100,bottom-y-16)
        if art:
            cover = ImageOps.fit(art,(aw,ah),Image.Resampling.LANCZOS,centering=(.5,.35))
            cover = ImageEnhance.Color(cover).enhance(.82)
            mask=Image.new('L',cover.size)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,aw-1,ah-1),radius=20,fill=255)
            image.paste(cover,(x,y),mask)
        else:
            draw.rounded_rectangle((x,y,x+aw,y+ah),radius=20,fill='#1c3c49')
            for i in range(6):
                offset=i*20
                bounds=(x+30+offset,y+20+offset,x+aw-30-offset,y+ah-20-offset)
                if bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:
                    break
                draw.arc(bounds,200,510,fill='#426774',width=1)
        # Deliberately asymmetric specular rim; restrained cyan, never electric cobalt.
        draw=ImageDraw.Draw(image)
        draw.line((26,89,width*.38,89),fill='#7fb7c7',width=1)
        if len(self.background_cache)>8:
            self.background_cache.clear()
        self.background_cache[key]=image
        return image

    def set_background(self, image, animate=True):
        canvas = self.scene
        if not canvas:
            return
        previous = self.background_current
        self.background_current = image
        if previous and previous.size != image.size:
            previous = previous.resize(image.size, Image.Resampling.BILINEAR)
        self.background_photo = ImageTk.PhotoImage(previous if previous and animate else image)
        if getattr(self, 'background_item', None) and canvas.type(self.background_item):
            canvas.itemconfigure(self.background_item, image=self.background_photo)
        else:
            self.background_item = canvas.create_image(0, 0, image=self.background_photo, anchor='nw', tags='backdrop')
        canvas.tag_lower('backdrop')
        image_id = self.background_item
        generation = self.scene_generation
        if self.motion and previous and animate:
            # Quantized, precomputed frames keep blend arithmetic off the event thread.
            last = [-1]
            def blend(t):
                if not self.valid_scene(canvas, generation):
                    return
                frame = round(t * 12)
                if frame == last[0]:
                    return
                last[0] = frame
                frames = getattr(self, '_backdrop_frames', [])
                blended = frames[min(len(frames)-1, max(0, round(t*len(frames))-1))] if frames else image
                self.background_photo = ImageTk.PhotoImage(blended)
                canvas.itemconfigure(image_id, image=self.background_photo)
            self.motion.animate('backdrop', TIMING['reduced'] if self.reduced_motion else 360, blend, curve='in_out')

    def text(self, x, y, text, size=14, color=TEXT, weight='normal', **kw):
        return self.scene.create_text(x, y, text=text, anchor='nw', fill=color,
             font=('Segoe UI', size, weight), **kw)

    def hover(self, tag, enter, leave):
        canvas, generation = self.scene, self.scene_generation
        def dispatch(cursor, callback):
            if self.valid_scene(canvas, generation):
                canvas.configure(cursor=cursor)
                callback()
        canvas.tag_bind(tag, '<Enter>', lambda e=None: dispatch('hand2', enter))
        canvas.tag_bind(tag, '<Leave>', lambda e=None: dispatch('', leave))

    def valid_scene(self, canvas, generation):
        return self.current_page == 'library' and self.scene is canvas and self.scene_generation == generation and canvas.winfo_exists()

    def action(self, x, y, width, text, command, primary=False, tag='action', height=48):
        canvas, generation = self.scene, self.scene_generation
        color = LIME if primary else '#18283f'
        r=12
        rect = self.scene.create_polygon(x+r,y,x+width-r,y,x+width,y,x+width,y+r,
            x+width,y+height-r,x+width,y+height,x+width-r,y+height,x+r,y+height,x,y+height,x,y+height-r,x,y+r,x,y,
            smooth=True,splinesteps=16,fill=color,outline=color,width=1,tags=(tag,))
        label = self.scene.create_text(x+width/2, y+height/2, text=text, fill=INK if primary else TEXT,
             font=('Segoe UI', 12, 'bold'), tags=(tag,))
        def pressed(event):
            if not self.valid_scene(canvas, generation):
                return
            canvas.itemconfigure(rect, fill='#87c4d5' if primary else '#395779')
            self.motion.animate('hover-'+tag, TIMING['press'],
                lambda t: change(t, '#87c4d5' if primary else '#395779', color))
            self.guarded_action('scene-'+tag, command, canvas)
        canvas.tag_bind(tag, '<Button-1>', pressed)
        def change(t, start, end):
            if self.valid_scene(canvas, generation):
                canvas.itemconfigure(rect, fill=color_between(start, end, t))
        def enter():
            if self.motion:
                self.motion.animate('hover-'+tag, TIMING['hover'], lambda t: change(t, color, '#daf8ff' if primary else '#2a4161'))
        def leave():
            if self.motion:
                self.motion.animate('hover-'+tag, TIMING['hover'], lambda t: change(t, '#daf8ff' if primary else '#2a4161', color))
        self.hover(tag, enter, leave)
        return [rect, label]

    def reveal_items(self, items, key, delay=0, distance=22):
        if not self.motion:
            return
        if self.reduced_motion:
            distance, delay = 0, 0
        original = {item: self.scene.coords(item) for item in items}
        for item, coords in original.items():
            moved = [value + distance if i % 2 else value for i, value in enumerate(coords)]
            self.scene.coords(item, *moved)
            self.scene.itemconfigure(item, state='hidden')
        canvas = self.scene
        generation = self.scene_generation
        colors = dict(self.item_colors)
        def update(t):
            if not self.valid_scene(canvas, generation):
                return
            for item, coords in original.items():
                canvas.itemconfigure(item, state='normal')
                moved = [value + distance * (1-t) if i % 2 else value for i, value in enumerate(coords)]
                canvas.coords(item, *moved)
                if canvas.type(item) == 'text':
                    # Text fades against the dark left-side vignette.
                    target = colors.get(item, TEXT)
                    canvas.itemconfigure(item, fill=color_between(INK, target, t))
        duration = TIMING['reduced'] if self.reduced_motion else TIMING['hero'] if key == 'headline' else TIMING['support']
        self.motion.animate(key, duration, update, delay=delay)

    def render_scene(self, entrance=True):
        if not self.scene or not self.scene.winfo_exists():
            return
        if self.motion:
            for key in list(self.motion.tokens):
                if key not in ('page', 'page-exit'):
                    self.motion.cancel(key)
        self.scene_generation += 1
        generation = self.scene_generation
        canvas = self.scene
        width, height = max(730,canvas.winfo_width()), max(565,canvas.winfo_height())
        canvas.delete('all')
        self.background_item=None
        self.card_widgets={}
        self.scene_photos=[]
        self.item_colors={}
        games=self.visible_games()
        game=self.selected if games else None
        initial=self.background_current or Image.new('RGB',(width,height),INK)
        if initial.size!=(width,height):
            initial=initial.resize((width,height),Image.Resampling.BILINEAR)
        self.set_background(initial,animate=False)
        self.text(2,0,'Library',28,TEXT,'bold')
        self.text(3,47,f'{len(games):02d} games in your personal collection',11,DIM)
        refresh=self.text(width-116,21,'↻  Refresh',11,ICE,tags='refresh')
        canvas.tag_bind('refresh','<Button-1>',lambda e:self.guarded_action('refresh',self.refresh,canvas))
        self.hover('refresh',lambda:canvas.itemconfigure(refresh,fill=TEXT),lambda:canvas.itemconfigure(refresh,fill=ICE))
        hero_bottom=height-228
        hero_height=hero_bottom-88
        x=28
        title_y=148+max(0,(hero_height-340)*.4)
        eyebrow=self.text(x,title_y-36,'IN THE SPOTLIGHT  /  YOUR PICK',9,ICE,'bold')
        title=self.text(x-2,title_y,game.title if game else 'Enter a\nnew world.',
                        min(42,max(27,width//36)),TEXT,'bold',width=round(width*.46))
        box=canvas.bbox(title)
        desc_y=(box[3] if box else 220)+14
        description=(game.description if game else '')
        if not description or description.startswith('No matching game details'):
            description='Your game, your world. Browse your collection and pick up the adventure.'
        # Bound body copy to leave room for controls on small desktop windows.
        description=description[:145]+('…' if len(description)>145 else '')
        desc=self.text(x,desc_y,description,11,DIM,width=round(width*.43))
        button_y=min(max(desc_y+64,title_y+140),hero_bottom-140)
        # Long custom titles yield space to launch controls, not overlap them.
        if desc_y+48>button_y-12:
            canvas.itemconfigure(desc,state='hidden')
        if game:
            result=self.results.get(game.id)
            actions=self.action(x,button_y,182,'▶   Play' if result and not result.blocked else '▶   Scan and play',lambda:self.play(game),True,'play')
            actions+=self.action(x+194,button_y,94,'Scan',lambda:self.scan_game(game),tag='scan')
            actions+=self.action(x+300,button_y,44,'•••',self.game_menu,tag='options')
            actions+=self.action(x,button_y+54,240,'Skip scan and play…',lambda:self.skip_scan_and_play(game),
                                 tag='skip-scan',height=32)
            verdict=result.status if result else 'Not scanned yet'
            if game.id in self._unscanned_launches:
                verdict='UNVERIFIED · SCAN SKIPPED'
            status=self.text(x,button_y+94,'●  '+verdict,9,'#f2b4a7' if game.id in self._unscanned_launches or result and result.blocked else DIM)
            try:
                self.digest=result.hashes.get(str(Path(game.launcher).relative_to(game.root)),'') if result else ''
            except ValueError:
                self.digest=''
            digest=self.text(x,button_y+114,'SHA-256  '+(self.digest if self.digest else 'available after scanning'),8,'#91acb9',width=round(width*.44))
            if self.digest:
                canvas.itemconfigure(digest,tags='digest-copy')
                canvas.tag_bind('digest-copy','<Button-1>',lambda e:self.copy_digest())
            extras=[status,digest]
        else:
            self.digest=''
            actions=self.action(x,button_y,220,'＋   Add my first game',self.import_menu,True,'import-empty')
            extras=[]
        rail_y=height-166
        self.text(2,rail_y-39,'Your entire collection',15,TEXT,'bold')
        self.text(width-160,rail_y-32,'←  →   TO BROWSE',8,DIM)
        capacity=max(1,(width-4)//228)
        selected_index=next((i for i,g in enumerate(games) if game and g.id==game.id),0)
        start=max(0,min(selected_index-1,len(games)-capacity))
        tile_items=[]
        for i,item in enumerate(games[start:start+capacity]):
            tx=4+i*228
            tag='game-'+item.id
            active=bool(game and game.id==item.id)
            border=canvas.create_rectangle(tx-2,rail_y-2,tx+211,rail_y+127,fill='#1c3541',
                        outline=ICE if active else '#28414e',width=2 if active else 1,tags=tag)
            raw=self.artwork(item)
            if raw:
                thumb=ImageOps.fit(raw,(210,126),Image.Resampling.LANCZOS)
                photo=ImageTk.PhotoImage(thumb)
                self.scene_photos.append(photo)
                image_id=canvas.create_image(tx,rail_y,image=photo,anchor='nw',tags=tag)
            else:
                image_id=self.text(tx+80,rail_y+32,item.title[:1],32,ICE,'bold',tags=tag)
            label=self.text(tx,rail_y+137,item.title[:29],10,ICE if active else DIM,'bold',tags=tag)
            canvas.tag_bind(tag,'<Button-1>',lambda e,g=item:self.guarded_action('select-game',lambda:self.select(g),canvas))
            self.hover(tag,lambda b=border:canvas.itemconfigure(b,outline=ICE),
                       lambda b=border,a=active:canvas.itemconfigure(b,outline=ICE if a else '#28414e'))
            self.card_widgets[item.id]=border
            tile_items.append([border,image_id,label])
        for item in canvas.find_all():
            if canvas.type(item)=='text':
                self.item_colors[item]=canvas.itemcget(item,'fill')
        if entrance:
            self.reveal_items([eyebrow,title],'headline',0,14)
            if canvas.itemcget(desc,'state')!='hidden':
                self.reveal_items([desc],'description',70,10)
            self.reveal_items(actions,'actions',120,8)
            self.reveal_items(extras,'details',180,6)
            for i,items in enumerate(tile_items):
                self.reveal_items(items,'tile-'+str(i),210+min(i,9)*40,10)
        def background():
            image=self.make_background(game,width,height)
            # Blend arithmetic stays off Tk's event thread.
            previous=initial
            frames=[Image.blend(previous,image,i/10) for i in range(1,11)] if entrance and not self.reduced_motion else []
            def finish():
                if self.valid_scene(canvas,generation):
                    self._backdrop_frames=frames
                    self.set_background(image,animate=bool(frames))
            self.post('call',finish)
        threading.Thread(target=background,daemon=True,name='Nexus-backdrop').start()

    def copy_digest(self):
        if self.digest:
            self.clipboard_clear()
            self.clipboard_append(self.digest)
            self.status_text.set('Full SHA-256 copied to clipboard.')

    def select(self, game):
        self.selected = game
        if self.current_page == 'library' and self.scene:
            self.render_scene(entrance=True)

    def navigate(self, step):
        if self.popup_active() or time.monotonic()-self._last_game_step < .12:
            return
        self._last_game_step = time.monotonic()
        super().navigate(step)

    def play(self, game):
        if self.popup_active():
            self.popup_active().lift()
            return
        if self.busy:
            self.status_text.set('An operation is running. Wait for it to finish before launching the game.')
            return
        dialog = self.dialog('Remember to save', 620, 350)
        ctk.CTkLabel(dialog, text='Keep your progress.', font=('Segoe UI', 26, 'bold'),
                     text_color=TEXT).pack(padx=28, pady=(28, 15))
        ctk.CTkLabel(dialog, text='Remember to save in the game before quitting.\nNexus cannot save progress left in memory\nafter the game closes.',
                     text_color=DIM, font=('Segoe UI', 14), justify='left', wraplength=550).pack(padx=28, pady=(0, 24))
        def proceed():
            dialog.destroy()
            super(CinematicNexus, self).play(game)
        self._button(dialog, 'Got it — launch game', proceed, primary=True, width=460).pack(pady=7)
        self._button(dialog, 'Cancel', dialog.destroy, width=460).pack(pady=7)

    def dialog(self, title, width=580, height=400):
        window = AnimatedDialog(self, title, width, height)
        self._active_dialog = window
        return window
