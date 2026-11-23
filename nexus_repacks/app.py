from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import traceback
import time
import urllib.request
import urllib.parse
import uuid
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from nexus_repacks import library
from nexus_repacks.downloads import Download, extract_zip, clean_line, parse_progress
from nexus_repacks.library import Game, STATE, atomic_json
from nexus_repacks.security import Scanner, sha256, snapshot_unchanged
from nexus_repacks.platform_launch import launch_executable, launch_batch
from nexus_repacks.scan_cache import load_verified, save_verified, verified_files_unchanged
from nexus_repacks.link_resolver import LinkResolver, ResolutionCancelled

BG = '#080d1c'
PANEL = '#111a2c'
MUTED = '#9baac3'
BLUE = '#587dff'
WHITE = '#f4f7ff'
GREEN = '#68ddba'
RED = '#ff718a'
AMBER = '#f4c775'
APP_VERSION = '2.4.1'


class Nexus(ctk.CTk):
    def report_callback_exception(self, exception, value, tb):
        with (STATE / 'ui-errors.log').open('a', encoding='utf-8') as log:
            traceback.print_exception(exception, value, tb, file=log)
        if hasattr(self, 'status_text'):
            self.status_text.set('An interface error was logged. Reopen this screen.')

    def __init__(self, smoke=False):
        super().__init__()
        ctk.set_appearance_mode('dark')
        self.title('Nexus Repacks · ' + APP_VERSION)
        self.geometry('1440x900')
        self.minsize(1120, 740)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(str(library.asset_path('assets/nexus.ico')))
        except Exception:
            pass
        self.events = queue.Queue()
        self.games = [g for g in library.load_library() if g.source == 'REPACKS']
        self.settings = library.read_json(STATE / 'settings.json', {})
        self.root_path = Path(self.settings.get('root', str(library.DEFAULT_ROOT)))
        self.selected = None
        self.results = {}
        self._unscanned_launches = set()
        self._active_scan_game_id = None
        self._skip_pending_launch = False
        self._update_notice = None
        self._update_restart_requested = False
        self.external_blocks = library.read_json(STATE / 'native-blocks.json', {})
        self.images = {}
        self.source = 'ALL'
        self.busy = False
        self.download = None
        self.download_lines = []
        self.download_form = ('', '')
        self.transfer = {'phase': 'idle'}
        self._resume_download = None
        self._download_stop_reason = ''
        self.cancel_scan = threading.Event()
        self.current_page = 'library'
        self._animation = None
        self._fullscreen = False
        self.metadata_pending = set()
        self._tray = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self.page_host = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.page_host.grid(row=1, column=0, sticky='nsew', padx=38)
        self.content = ctk.CTkFrame(self.page_host, fg_color=BG, corner_radius=0)
        self.content.place(x=0, y=0, relwidth=1, relheight=1)
        self.status_text = ctk.StringVar(value='Ready · no game is launched automatically')
        self.footer_bar = ctk.CTkFrame(self, fg_color='transparent', corner_radius=0)
        self.footer_bar.grid(row=2, column=0, padx=42, pady=(8, 16), sticky='ew')
        self.footer = ctk.CTkLabel(self.footer_bar, textvariable=self.status_text, text_color=MUTED, anchor='w', font=('Segoe UI', 12))
        self.footer.pack(side='left', fill='x', expand=True)
        from nexus_repacks.updater import AutoUpdater
        self.updater = AutoUpdater(self, APP_VERSION)
        self.update_button = ctk.CTkButton(self.footer_bar, text='Nexus ' + APP_VERSION + ' · updates',
            command=self.show_update_or_check, width=240, height=28, fg_color='#142137',
            hover_color='#253b5b', font=('Segoe UI', 10))
        self.update_button.pack(side='right', padx=(10, 0))
        self.bind('<F11>', self.toggle_fullscreen)
        self.bind('<Escape>', lambda e: self.leave_fullscreen())
        self.bind('<Left>', lambda e: self.navigate(-1))
        self.bind('<Right>', lambda e: self.navigate(1))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.show_library()
        self.after(80, self.drain)
        if not smoke:
            self.after(200, lambda: self.state('zoomed'))
            self.after(400, self.refresh)
            from nexus_repacks.updater import INITIAL_CHECK_MS
            self.after(INITIAL_CHECK_MS, self.check_updates)

    def check_updates(self):
        from nexus_repacks.updater import CHECK_INTERVAL_MS
        self.updater.check()
        self.after(CHECK_INTERVAL_MS, self.check_updates)

    def show_update_or_check(self):
        if self._update_notice:
            self._update_notice.show()
        elif self.updater.pending:
            self.on_update_event('ready', self.updater.pending[1], 1.)
        else:
            self.updater.check()

    def on_update_event(self, stage, manifest, ratio=None, error=''):
        if self._update_restart_requested:
            return
        from nexus_repacks.update_notice import UpdateNotice
        if not self._update_notice:
            self._update_notice = UpdateNotice(self, manifest)
        self._update_notice.update(stage, manifest, ratio, error)

    def restart_for_update(self):
        if not self.updater.pending or self._update_restart_requested:
            return
        self._update_restart_requested = True
        self._skip_pending_launch = False
        if self.busy:
            phase = self.transfer.get('phase')
            if phase in ('preparing', 'downloading'):
                self.pause_download()
            elif phase == 'scanning':
                self.cancel_download()
            else:
                self.cancel_scan.set()
        def finish():
            if self.busy or getattr(self, '_launch_in_progress', False):
                if self._update_notice:
                    self._update_notice.restarting('Stopping the current operation. Downloaded files are kept…')
                self.after(80, finish)
                return
            if self._update_notice:
                self._update_notice.restarting('Installing the verified update and restarting Nexus…')
            try:
                if self.transfer.get('phase') == 'paused' and self._resume_download:
                    atomic_json(STATE / 'updates' / 'resume.json', {
                        'root': str(self.root_path.resolve()), 'download': list(self._resume_download)})
                library.save_library(self.games)
                self.updater.on_close(restart=True)
            except OSError as exc:
                self.updater.stopped.clear()
                self._update_restart_requested = False
                self.on_update_event('error', self.updater.pending[1], error=str(exc))
                return
            if self._tray:
                self._tray.stop()
            self.destroy()
        finish()

    def restore_update_session(self):
        path = STATE / 'updates' / 'resume.json'
        data = library.read_json(path, {})
        path.unlink(missing_ok=True)
        values = data.get('download', []) if isinstance(data, dict) else []
        if (not isinstance(values, list) or len(values) != 4 or
                not all(isinstance(value, str) and len(value) <= 16384 for value in values) or
                data.get('root') != str(self.root_path.resolve())):
            return False
        source, name, referrer, output = values
        if not self.valid_download_name(name) or output and not self.valid_download_name(output):
            return False
        self.download_form = (source, name)
        self._resume_download = tuple(values)
        self.transfer = {'phase': 'paused', 'name': name,
                         'destination': str(self.root_path / 'downloads' / name)}
        self.show_downloads()
        self.status_text.set('Transfer paused for the update · click Resume to continue')
        return True

    def _button(self, parent, text, command, primary=False, **kw):
        return ctk.CTkButton(parent, text=text, command=command, height=42,
                             fg_color=WHITE if primary else '#1b2842',
                             text_color=BG if primary else WHITE,
                             hover_color='#cad8ff' if primary else '#2b3f63',
                             corner_radius=24, font=('Segoe UI', 13, 'bold'), **kw)

    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=BG, height=92, corner_radius=0)
        bar.grid(row=0, column=0, sticky='ew', padx=40, pady=(20, 10))
        bar.grid_columnconfigure(4, weight=1)
        ctk.CTkLabel(bar, text='N', width=48, height=48, corner_radius=14, fg_color=BLUE,
                     font=('Segoe UI', 30, 'bold'), text_color=WHITE).grid(row=0, column=0, padx=(0, 14))
        brand = ctk.CTkFrame(bar, fg_color='transparent')
        brand.grid(row=0, column=1, padx=(0, 44))
        ctk.CTkLabel(brand, text='NEXUS', font=('Segoe UI', 20, 'bold'), text_color=WHITE, anchor='w').pack(anchor='w')
        ctk.CTkLabel(brand, text='R E P A C K S', font=('Segoe UI', 10), text_color=MUTED, anchor='w').pack(anchor='w')
        self._button(bar, 'Library', self.show_library, width=126).grid(row=0, column=2, padx=5)
        self._button(bar, 'Downloads', self.show_downloads, width=158).grid(row=0, column=3, padx=5)
        self._button(bar, 'Protection', self.show_protection, width=118).grid(row=0, column=4, sticky='w', padx=5)
        self._button(bar, '＋ Import', self.import_menu, width=124).grid(row=0, column=5, padx=5)
        self._button(bar, '⛶  F11', self.toggle_fullscreen, width=82).grid(row=0, column=6, padx=(12, 0))

    def clear(self):
        source = getattr(self, 'download_source', None)
        if source is not None and source.winfo_exists():
            self.download_form = (source.get(), self.download_name.get())
        if self._animation:
            self.after_cancel(self._animation)
            self._animation = None
        for child in self.content.winfo_children():
            child.destroy()

    def post(self, kind, *args):
        self.events.put((kind, args))

    def drain(self):
        count = 0
        while count < 100:
            try:
                kind, args = self.events.get_nowait()
            except queue.Empty:
                break
            count += 1
            if kind == 'status':
                self.status_text.set(args[0])
            elif kind == 'call':
                args[0]()
            elif kind == 'error':
                self.busy = False
                if self.transfer.get('phase') in ('preparing', 'downloading', 'scanning'):
                    self.transfer['phase'] = 'error'
                self.status_text.set(args[0])
                messagebox.showerror('Nexus Repacks', args[0], parent=self)
            elif kind == 'log':
                line = clean_line(args[0])
                self.transfer.update(parse_progress(line))
                self.download_lines.append(line)
                self.download_lines = self.download_lines[-600:]
                if self.current_page == 'downloads' and hasattr(self, 'download_log'):
                    self.download_log.configure(state='normal')
                    self.download_log.insert('end', line + '\n')
                    line_count = int(self.download_log.index('end-1c').split('.')[0])
                    if line_count > 650:
                        self.download_log.delete('1.0', f'{line_count-600}.0')
                    self.download_log.see('end')
                    self.download_log.configure(state='disabled')
            elif kind == 'transfer':
                self.transfer.update(args[0])
                if args[0].get('phase') in ('scanning', 'completed') and self.transfer.get('total'):
                    self.transfer['done'] = self.transfer['total']
        if self.current_page == 'downloads' and getattr(self, 'download_view', None):
            self.download_view.update_transfer()
        if self.current_page == 'catalog' and getattr(self, 'catalog_view', None):
            self.catalog_view.update_state()
        self.after(60, self.drain)

    def work(self, function):
        if getattr(self, '_update_notice', None):
            self._update_notice.show()
            return False
        if self.busy:
            self.status_text.set('An operation is running in the background.')
            return False
        self.busy = True
        self.cancel_scan.clear()
        def run():
            try:
                function()
            except Exception as exc:
                self.post('error', f'{type(exc).__name__} : {exc}')
            finally:
                self.post('call', lambda: setattr(self, 'busy', False))
        threading.Thread(target=run, daemon=True, name='Nexus-worker').start()
        return True

    def refresh(self):
        def run():
            self.post('status', 'Looking for your repacks…')
            found = library.discover(self.root_path / 'games')
            def finish():
                old = {g.id: g for g in self.games}
                merged = {g.id: g for g in self.games if g.source == 'REPACKS' and Path(g.launcher).exists()}
                for g in found:
                    if g.id in old:
                        for key in ('description', 'image', 'metadata_url'):
                            setattr(g, key, getattr(old[g.id], key))
                    merged[g.id] = g
                self.games = sorted(merged.values(), key=lambda g: g.title.casefold())
                for game in self.games:
                    cached = load_verified(STATE / 'verified' / (game.id + '.bin'), game)
                    if cached:
                        self.results.setdefault(game.id, cached)
                library.save_library(self.games)
                if self.current_page == 'library':
                    self.show_library()
                self.status_text.set(f'{len(self.games)} games · arrow keys to browse · F11 fullscreen')
                for game in self.games:
                    if not game.description:
                        self.metadata_background(game)
            self.post('call', finish)
        self.work(run)

    def visible_games(self):
        return [g for g in self.games if self.source == 'ALL' or g.source == self.source]

    def show_library(self):
        self.current_page = 'library'
        self.clear()
        filters = ctk.CTkFrame(self.content, fg_color='transparent')
        filters.pack(fill='x', pady=(8, 18))
        ctk.CTkLabel(filters, text='YOUR GAMES. YOUR WORLD.', text_color=MUTED, font=('Segoe UI', 12, 'bold')).pack(side='left', padx=(0, 24))
        for source in ('ALL', 'REPACKS', 'EPIC GAMES', 'MICROSOFT'):
            button = self._button(filters, source, lambda s=source: self.set_source(s), width=110)
            if source == self.source:
                button.configure(fg_color=BLUE)
            button.pack(side='left', padx=4)
        self._button(filters, '↻ Refresh', self.refresh, width=114).pack(side='right')
        self.cards = ctk.CTkScrollableFrame(self.content, orientation='horizontal', height=178, fg_color='transparent', scrollbar_button_color='#263856')
        self.cards.pack(fill='x', pady=(0, 14))
        self.hero = ctk.CTkFrame(self.content, fg_color=PANEL, corner_radius=26)
        self.hero.pack(fill='both', expand=True)
        self.hero.grid_columnconfigure(0, weight=1)
        self.hero.grid_rowconfigure(0, weight=1)
        self.card_widgets = {}
        games = self.visible_games()
        for index, game in enumerate(games):
            card = ctk.CTkFrame(self.cards, width=154, height=156, fg_color='#19243a', corner_radius=16, border_width=2, border_color='#26334c')
            card.grid(row=0, column=index, padx=7, pady=4)
            card.grid_propagate(False)
            image = self.game_image(game, 92)
            art = ctk.CTkLabel(card, image=image, text='' if image else game.title[:1].upper(), font=('Segoe UI', 46, 'bold'), width=100, height=100, text_color='#9eb8ff')
            art.pack(pady=(9, 0))
            label = ctk.CTkLabel(card, text=game.title[:23], font=('Segoe UI', 12, 'bold'), text_color=WHITE, width=140)
            label.pack()
            for target in (card, art, label):
                target.bind('<Button-1>', lambda e, g=game: self.select(g))
            self.card_widgets[game.id] = card
        if not games:
            ctk.CTkLabel(self.hero, text='Your next adventure starts here.', font=('Segoe UI', 32, 'bold'), text_color=WHITE).pack(pady=(85, 12))
            ctk.CTkLabel(self.hero, text='Import a game folder, a Microsoft game or start a download.', text_color=MUTED).pack(pady=8)
            self._button(self.hero, 'Import a game', self.import_menu, primary=True, width=210).pack(pady=24)
        else:
            selected = next((g for g in games if self.selected and g.id == self.selected.id), games[0])
            self.select(selected)

    def set_source(self, source):
        self.source = source
        self.show_library()

    def game_image(self, game, size):
        key = (game.id, game.image, size)
        if key in self.images:
            return self.images[key]
        path = game.image
        if not path or not Path(path).is_file():
            path = library.local_image(game) if game.root else ''
            if path:
                game.image = path
        try:
            if path:
                with Image.open(path) as raw:
                    raw.load()
                    image = ImageOps.contain(raw.convert('RGBA'), (size, size), Image.Resampling.LANCZOS)
                result = ctk.CTkImage(image, image, size=(image.width, image.height))
                self.images[key] = result
                return result
        except Exception:
            pass
        return None

    def select(self, game):
        self.selected = game
        for ident, card in self.card_widgets.items():
            card.configure(border_color='#c4d8ff' if ident == game.id else '#26334c', fg_color='#263a60' if ident == game.id else '#19243a')
        for widget in self.hero.winfo_children():
            widget.destroy()
        info = ctk.CTkFrame(self.hero, fg_color='transparent')
        info.grid(row=0, column=0, sticky='w', padx=38, pady=30)
        ctk.CTkLabel(info, text=f'{game.source}     /     PERSONAL LIBRARY', text_color='#88a9ff', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 16))
        wrap = max(410, min(760, self.winfo_width() - 660))
        self.hero_title = ctk.CTkLabel(info, text=game.title, font=('Segoe UI', 44, 'bold'), text_color=WHITE, anchor='w', wraplength=wrap, justify='left')
        self.hero_title.pack(anchor='w', pady=(0, 14))
        description = game.description or 'Ready for your next session. Scan the folder before playing; add game details or customize your library.'
        ctk.CTkLabel(info, text=description, font=('Segoe UI', 15), text_color=MUTED, wraplength=wrap, justify='left').pack(anchor='w', pady=(0, 14))
        result = self.results.get(game.id)
        verdict = result.status if result else ('WINDOWS LAUNCH · NOT SCANNED' if game.source == 'MICROSOFT' else 'NOT SCANNED YET')
        color = (RED if result and any(f.severity == 'danger' for f in result.findings) else AMBER if result and result.blocked else GREEN if result else MUTED)
        ctk.CTkLabel(info, text='●  ' + verdict, text_color=color, font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(0, 6))
        digest = ''
        if result:
            try:
                digest = result.hashes.get(str(Path(game.launcher).relative_to(Path(game.root))), '')
            except ValueError:
                pass
        self.digest = digest
        ctk.CTkLabel(info, text='SHA-256  ' + (digest if digest else 'available after scanning'), text_color=MUTED, font=('Consolas', 11), wraplength=wrap, justify='left').pack(anchor='w', pady=(0, 12))
        if game.metadata_url:
            source = ctk.CTkLabel(info, text='Source: Wikipedia ↗', text_color='#88a9ff', font=('Segoe UI', 11), cursor='hand2')
            source.pack(anchor='w')
            source.bind('<Button-1>', lambda e, url=game.metadata_url: webbrowser.open(url))
        buttons = ctk.CTkFrame(info, fg_color='transparent')
        buttons.pack(anchor='w', pady=(4, 12))
        self._button(buttons, '▶  Play' if game.source == 'MICROSOFT' else '▶  Scan and play', lambda g=game: self.play(g), primary=True, width=196).pack(side='left', padx=(0, 8))
        self._button(buttons, 'Scan', lambda g=game: self.scan_game(g), width=105).pack(side='left', padx=4)
        self._button(buttons, '•••', self.game_menu, width=52).pack(side='left', padx=4)
        ctk.CTkLabel(info, text='Static inspection reduces risk. It does not guarantee the game is safe.', text_color='#7c8aa3', font=('Segoe UI', 11), wraplength=640, justify='left').pack(anchor='w', pady=(2, 0))
        image = self.game_image(game, 316)
        art = ctk.CTkFrame(self.hero, width=360, height=394, fg_color='#192e50', corner_radius=28, border_width=1, border_color='#314e7d')
        art.grid(row=0, column=1, padx=(0, 42), pady=28)
        art.grid_propagate(False)
        ctk.CTkLabel(art, text='' if image else game.title[:1].upper(), image=image, text_color='#a8c6ff', font=('Segoe UI', 130, 'bold')).place(relx=0.5, rely=0.47, anchor='center')
        ctk.CTkLabel(art, text='N E X U S   /   P L A Y', text_color='#86a6db', font=('Segoe UI', 11)).place(relx=0.5, rely=0.9, anchor='center')
        if self._animation:
            self.after_cancel(self._animation)
        def fade(frame=0):
            if self.current_page != 'library' or not self.hero_title.winfo_exists():
                return
            t = min(1, frame / 8)
            color = '#' + ''.join(f'{round(a + (b-a)*t):02x}' for a, b in zip((115, 145, 214), (244, 247, 255)))
            self.hero_title.configure(text_color=color)
            self._animation = self.after(16, fade, frame + 1) if frame < 8 else None
        fade()

    def navigate(self, step):
        if self.current_page != 'library' or isinstance(self.focus_get(), (ctk.CTkEntry,)):
            return
        games = self.visible_games()
        if not games:
            return
        index = next((i for i, g in enumerate(games) if self.selected and g.id == self.selected.id), 0)
        self.select(games[(index + step) % len(games)])

    def scan_game(self, game, launch=False):
        if self.busy:
            self.status_text.set('Wait for the current operation to finish.')
            return
        if game.source == 'MICROSOFT':
            messagebox.showinfo('Microsoft application', 'Windows launches this app. This engine cannot inspect protected WindowsApps packages.', parent=self)
            return
        def run():
            scanner = Scanner(progress=lambda t: self.post('status', t), cancel=self.cancel_scan.is_set, inspect_archives=False)
            result = scanner.scan(Path(game.root))
            if self.cancel_scan.is_set():
                self.post('status', 'Scan cancelled · game remains unverified')
                return
            # Hash the selected target even when its extension is unusual.
            launcher = Path(game.launcher).resolve(strict=True)
            if not launcher.is_relative_to(Path(game.root).resolve()):
                raise ValueError('The target is outside the game folder.')
            relative = str(launcher.relative_to(Path(game.root).resolve()))
            digest = result.hashes.get(relative) or sha256(launcher, cancel=self.cancel_scan.is_set)
            if self.cancel_scan.is_set():
                self.post('status', 'Scan cancelled · game remains unverified')
                return
            result.hashes[relative] = digest
            atomic_json(STATE / 'reports' / (game.id + '.json'), result.to_dict())
            cache_path = STATE / 'verified' / (game.id + '.bin')
            cache_path.unlink(missing_ok=True)
            if not result.blocked:
                save_verified(cache_path, game, result)
            def finish():
                if self.cancel_scan.is_set():
                    self.status_text.set('Scan cancelled · game remains unverified')
                    return
                self._unscanned_launches.discard(game.id)
                self.results[game.id] = result
                if self.current_page == 'library' and self.selected and self.selected.id == game.id:
                    self.select(game)
                if result.blocked:
                    self.status_text.set(f'{game.title} · {result.status} · see Protection')
                    self.show_protection(game)
                elif launch:
                    self._launch_verified(game, result, digest)
                else:
                    self.status_text.set(f'{game.title} · no indicators detected · report saved')
            self.post('call', finish)
        def tracked_run():
            try:
                run()
            except InterruptedError:
                self.post('status', 'Scan cancelled · game remains unverified')
            finally:
                self.post('call', lambda: setattr(self, '_active_scan_game_id', None))
        self._active_scan_game_id = game.id
        if not self.work(tracked_run):
            self._active_scan_game_id = None

    def skip_scan_and_play(self, game):
        if getattr(self, '_update_notice', None):
            self._update_notice.show()
            return
        if game.source != 'REPACKS':
            self.status_text.set('This option is available for local repacks.')
            return
        if self._skip_pending_launch or getattr(self, '_launch_in_progress', False):
            self.status_text.set('A launch is already being prepared.')
            return
        previous = getattr(self, '_skip_dialog', None)
        if previous and previous.winfo_exists() and not getattr(previous, '_closing', False):
            previous.lift()
            return
        if self.busy and self._active_scan_game_id != game.id:
            self.status_text.set('Another operation is running. Finish or cancel it before playing.')
            return
        dialog = self.dialog('Play without scanning?', 680, 560)
        self._skip_dialog = dialog
        ctk.CTkLabel(dialog, text='Play without scanning?', text_color=AMBER,
                     font=('Segoe UI', 26, 'bold')).pack(anchor='w', padx=28, pady=(26, 12))
        ctk.CTkLabel(dialog, text=game.title[:160], text_color=WHITE, font=('Segoe UI', 18, 'bold'),
                     wraplength=620, justify='left').pack(anchor='w', padx=28, pady=(0, 12))
        note = ('The game will launch without scanning or file verification.\n'
                'This is a one-time choice. It does not mark the game as safe.\n'
                'Only continue if you trust its source.\n\n'
                'Remember to save inside the game before quitting.')
        result = self.results.get(game.id)
        if result and result.blocked:
            note += '\n\nPrevious scan: ' + result.status + '. See Protection for details.'
        if game.id in self.external_blocks:
            note += '\n\nA previous Windows scan reported a detection or error.'
        ctk.CTkLabel(dialog, text=note, text_color=MUTED, font=('Segoe UI', 13),
                     wraplength=620, justify='left').pack(anchor='w', padx=28, pady=(0, 16))
        accepted = False
        def approve():
            nonlocal accepted
            if accepted:
                return
            accepted = True
            dialog.destroy()
            self._skip_pending_launch = True
            def launch_when_ready():
                if not self._skip_pending_launch:
                    return
                if self.busy:
                    same_scan = self._active_scan_game_id == game.id
                    scan_stopping = self._active_scan_game_id is None and self.cancel_scan.is_set()
                    if same_scan or scan_stopping:
                        self.cancel_scan.set()
                        self.status_text.set('Stopping the scan before launching without verification…')
                        self.after(60, launch_when_ready)
                    else:
                        self._skip_pending_launch = False
                        self.status_text.set('Another operation is running. Please try again when it finishes.')
                    return
                self._skip_pending_launch = False
                self._launch_unscanned(game)
            launch_when_ready()
        self._button(dialog, 'I understand — play without scanning', approve, primary=True,
                     width=620).pack(padx=28, pady=6)
        self._button(dialog, 'Cancel', dialog.destroy, width=620).pack(padx=28, pady=(6, 22))

    def _launch_unscanned(self, game):
        if self.busy or getattr(self, '_launch_in_progress', False):
            return
        self._launch_in_progress = True
        def run():
            try:
                root = Path(game.root).resolve(strict=True)
                target = Path(game.launcher).resolve(strict=True)
                if not root.is_dir() or not target.is_file() or not target.is_relative_to(root):
                    raise ValueError('The target must be a file inside the game folder.')
                if target.suffix.lower() == '.exe':
                    launch_executable(target)
                elif target.suffix.lower() in ('.bat', '.cmd'):
                    launch_batch(target)
                else:
                    raise ValueError('Only EXE, BAT and CMD files can be launched.')
                def finish():
                    self._unscanned_launches.add(game.id)
                    if self.current_page == 'library' and self.selected and self.selected.id == game.id:
                        self.select(game)
                    self.status_text.set('Launched without scan · ' + game.title + ' · NOT VERIFIED')
                    self.hide_to_tray()
                self.post('call', finish)
            except Exception as exc:
                self.post('error', str(exc))
            finally:
                self._launch_in_progress = False
        threading.Thread(target=run, daemon=True, name='Nexus-unverified-launch').start()

    def _launch_verified(self, game, result, digest):
        if getattr(self, '_launch_in_progress', False):
            return
        self._launch_in_progress = True
        # Worker thread performs revalidation; keep all slow I/O away from the UI.
        def run():
            try:
                if not verified_files_unchanged(result) or sha256(Path(game.launcher)) != digest:
                    raise ValueError('Program files have changed. Run a manual scan from Protection.')
                target = Path(game.launcher)
                if target.suffix.lower() == '.exe':
                    launch_executable(target)
                elif target.suffix.lower() in ('.bat', '.cmd'):
                    launch_batch(target)
                else:
                    raise ValueError('Only EXE, BAT and CMD files can be launched.')
                self.post('call', lambda: self.hide_to_tray())
                self.post('status', 'Launched · ' + game.title)
            except Exception as exc:
                self.post('error', str(exc))
            finally:
                self._launch_in_progress = False
        threading.Thread(target=run, daemon=True, name='Nexus-launch').start()

    def play(self, game):
        if getattr(self, '_update_notice', None):
            self._update_notice.show()
            return
        if self.busy:
            self.status_text.set('Wait for the current operation to finish.')
            return
        if game.id in self.external_blocks:
            messagebox.showerror('Launch blocked', 'A Windows scan reported a detection or error for this game. Resolve it, then run Windows Scan again before playing.', parent=self)
            self.show_protection(game)
            return
        if game.source == 'MICROSOFT':
            if not re.fullmatch(r'[A-Za-z0-9._-]+![A-Za-z0-9._-]+', game.platform_id):
                messagebox.showerror('Invalid target', 'Invalid Microsoft identifier.', parent=self)
                return
            subprocess.Popen(['explorer.exe', 'shell:AppsFolder\\' + game.platform_id], shell=False)
            self.status_text.set('Launch request sent to Windows · ' + game.title)
        else:
            result = self.results.get(game.id) or load_verified(STATE / 'verified' / (game.id + '.bin'), game)
            if result and not result.blocked:
                def reuse():
                    try:
                        relative = str(Path(game.launcher).relative_to(game.root))
                        digest = result.hashes.get(relative)
                        unchanged = bool(digest) and verified_files_unchanged(result) and sha256(Path(game.launcher)) == digest
                    except (OSError, ValueError):
                        unchanged = False
                    def finish():
                        if unchanged:
                            self.results[game.id] = result
                            self._launch_verified(game, result, digest)
                        else:
                            self.status_text.set('Program changed · manual verification required. No automatic rescan started.')
                            self.show_protection(game)
                    self.post('call', finish)
                self.work(reuse)
            else:
                self.scan_game(game, launch=True)

    def game_menu(self):
        game = self.selected
        if not game:
            return
        dialog = self.dialog('Customize · ' + game.title, 540, 520)
        for text, command in [
            ('Open folder', lambda: os.startfile(game.root) if game.root else None),
            ('Choose another launcher', lambda: self.change_launcher(game)),
            ('Choose an image', lambda: self.choose_image(game)),
            ('Find a description online', lambda: self.fetch_metadata(game)),
            ('Edit description', lambda: self.edit_description(game)),
            ('Copy full SHA-256', self.copy_hash),
            ('View report', lambda: self.show_protection(game)),
            ('Quarantine folder', lambda: self.quarantine(game)),
        ]:
            self._button(dialog, text, lambda c=command: (dialog.destroy(), c()), width=460).pack(pady=6, padx=24)

    def copy_hash(self):
        if self.digest:
            self.clipboard_clear()
            self.clipboard_append(self.digest)
            self.status_text.set('Full SHA-256 copied.')
        else:
            self.status_text.set('Scan the game to get its SHA-256.')

    def change_launcher(self, game):
        if game.source == 'MICROSOFT':
            return
        path = filedialog.askopenfilename(parent=self, initialdir=game.root, filetypes=[('Launchers', '*.exe *.bat *.cmd')])
        if path:
            target = Path(path).resolve()
            if not target.is_relative_to(Path(game.root).resolve()):
                messagebox.showerror('Nexus', 'Choose a launcher inside the game folder.', parent=self)
                return
            game.launcher = str(target)
            self.results.pop(game.id, None)
            library.save_library(self.games)
            self.show_library()

    def choose_image(self, game):
        path = filedialog.askopenfilename(parent=self, filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.ico')])
        if path:
            game.image = path
            library.save_library(self.games)
            self.show_library()

    def edit_description(self, game):
        dialog = self.dialog('Description', 620, 340)
        text = ctk.CTkTextbox(dialog, width=560, height=220)
        text.pack(padx=20, pady=15)
        text.insert('1.0', game.description)
        def save():
            game.description = text.get('1.0', 'end').strip()
            library.save_library(self.games)
            dialog.destroy()
            self.show_library()
        self._button(dialog, 'Save', save, primary=True).pack()

    def fetch_metadata(self, game):
        def run():
            self.post('status', 'Finding game details · only the title is sent to Wikipedia…')
            data = library.metadata(game)
            image_path = ''
            url = data.pop('image_url', '')
            if url.startswith('//'):
                url = 'https:' + url
            if url.startswith('https://upload.wikimedia.org/'):
                req = urllib.request.Request(url, headers={'User-Agent': 'NexusRepacks/1.0'})
                with urllib.request.urlopen(req, timeout=12) as response:
                    image = response.read(8 * 1024 * 1024 + 1)
                if len(image) <= 8 * 1024 * 1024:
                    path = STATE / 'images' / (game.id + '.jpg')
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(image)
                    image_path = str(path)
            def finish():
                game.description = data.get('description', '')
                game.metadata_url = data.get('metadata_url', '')
                if image_path:
                    game.image = image_path
                library.save_library(self.games)
                self.show_library()
                self.status_text.set('Wikipedia details added · check the title matches')
            self.post('call', finish)
        self.work(run)

    def metadata_background(self, game):
        """Fetch only public title metadata; failures never delay or approve launch."""
        if game.id in self.metadata_pending:
            return
        self.metadata_pending.add(game.id)
        def run():
            try:
                data = library.metadata(game)
                def finish():
                    self.metadata_pending.discard(game.id)
                    if not any(g.id == game.id for g in self.games) or game.description:
                        return
                    game.description = data.get('description', '')
                    game.metadata_url = data.get('metadata_url', '')
                    library.save_library(self.games)
                    if self.current_page == 'library' and self.selected and self.selected.id == game.id:
                        self.select(game)
                self.post('call', finish)
            except Exception:
                self.post('call', lambda: self.metadata_pending.discard(game.id))
        threading.Thread(target=run, daemon=True, name='Nexus-metadata').start()

    def quarantine(self, game):
        if self.busy:
            return
        root = Path(game.root).resolve()
        allowed = (self.root_path / 'games').resolve()
        if game.source != 'REPACKS' or root == allowed or not root.is_relative_to(allowed):
            messagebox.showinfo('Quarantine', 'Quarantine is limited to folders in REPACKS/games. No Epic or Microsoft folders will be moved.', parent=self)
            return
        if not messagebox.askyesno('Quarantine', f'Move the folder for {game.title} to quarantine? You can restore it from the quarantine folder.', parent=self):
            return
        def run():
            destination = STATE / 'quarantine' / uuid.uuid4().hex
            destination.parent.mkdir(exist_ok=True)
            atomic_json(destination.with_suffix('.json'), {'original': str(root), 'game': game.__dict__, 'time': time.time()})
            shutil.move(str(root), str(destination))
            def finish():
                self.games = [g for g in self.games if g.id != game.id]
                library.save_library(self.games)
                self.show_library()
                self.status_text.set('Folder quarantined · nothing permanently deleted')
            self.post('call', finish)
        self.work(run)

    def dialog(self, title, width=580, height=400):
        window = ctk.CTkToplevel(self)
        window.title(title)
        window.geometry(f'{width}x{height}')
        window.configure(fg_color=BG)
        window.transient(self)
        window.after(100, window.lift)
        return window

    def import_menu(self):
        dialog = self.dialog('Add to Nexus', 540, 420)
        ctk.CTkLabel(dialog, text='Expand your universe.', font=('Segoe UI', 28, 'bold')).pack(pady=(28, 22))
        for text, command in [
            ('Import a game folder', self.import_folder),
            ('Find my repacks', self.refresh),
            ('Change REPACKS folder', self.change_root),
        ]:
            self._button(dialog, text, lambda c=command: (dialog.destroy(), c()), width=430).pack(pady=9)

    def import_folder(self):
        path = filedialog.askdirectory(parent=self, title='Folder containing the game')
        if not path:
            return
        def run():
            found = library.candidates(Path(path))
            if not found:
                raise ValueError('No EXE, Run Me or Run found in this folder.')
            game = Game.local(path, found[0])
            def finish():
                self.games = [g for g in self.games if g.id != game.id] + [game]
                library.save_library(self.games)
                self.selected = game
                self.source = 'ALL'
                self.show_library()
                self.metadata_background(game)
                self.status_text.set('Imported · ' + game.title + ' · scan required before launch')
            self.post('call', finish)
        self.work(run)

    def import_microsoft(self):
        def run():
            apps = library.windows_apps()
            self.post('call', lambda: self.microsoft_picker(apps))
        self.work(run)

    def microsoft_picker(self, apps):
        dialog = self.dialog('Choose an installed Microsoft / Xbox game', 680, 590)
        search = ctk.CTkEntry(dialog, placeholder_text='Search installed games…', width=610, height=42)
        search.pack(padx=25, pady=15)
        frame = ctk.CTkScrollableFrame(dialog, fg_color=PANEL)
        frame.pack(fill='both', expand=True, padx=25, pady=(0, 20))
        def populate(*args):
            for child in frame.winfo_children():
                child.destroy()
            for app in apps:
                if search.get().casefold() not in app['Name'].casefold():
                    continue
                def choose(a=app):
                    ident = hashlib.sha256(a['AppID'].encode()).hexdigest()[:20]
                    game = Game(ident, a['Name'], '', '', 'MICROSOFT', platform_id=a['AppID'])
                    self.games = [g for g in self.games if g.id != ident] + [game]
                    library.save_library(self.games)
                    self.selected = game
                    self.source = 'ALL'
                    dialog.destroy()
                    self.show_library()
                    self.metadata_background(game)
                self._button(frame, app['Name'], choose, width=550).pack(pady=5)
        search.bind('<KeyRelease>', populate)
        populate()

    def change_root(self):
        path = filedialog.askdirectory(parent=self, title='REPACKS folder')
        if path:
            self.root_path = Path(path).resolve()
            self.settings['root'] = str(self.root_path)
            atomic_json(STATE / 'settings.json', self.settings)
            self.refresh()

    def show_downloads(self):
        self.current_page = 'downloads'
        self.clear()
        from nexus_repacks.download_view import DownloadView
        self.download_view = DownloadView(self)

    def choose_torrent(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('Torrent', '*.torrent')])
        if path:
            self.download_source.delete(0, 'end')
            self.download_source.insert(0, path)
            self.download_name.delete(0, 'end')
            self.download_name.insert(0, Path(path).stem)

    def show_catalog(self):
        self.current_page = 'catalog'
        self.clear()
        from nexus_repacks.catalog_view import CatalogView
        self.catalog_view = CatalogView(self)

    def download_catalog_game(self, game):
        if self.busy:
            self.status_text.set('An operation is already running. Your current transfer is preserved.')
            return
        if not game.enabled:
            self.status_text.set('This game is not available for download yet.')
            return
        self.begin_download(game.download_url, game.folder, game.referrer, game.filename)
        if self.transfer.get('phase') == 'preparing' and self.transfer.get('name') == game.folder:
            self.show_downloads()

    def start_download(self):
        if self.busy:
            self.status_text.set('An operation is already running.')
            return
        source = self.download_source.get().strip()
        name = self.download_name.get().strip()
        self.download_form = (source, name)
        if not source:
            self.status_text.set('Paste a web page address, direct link or magnet link.')
            return
        self.inspect_download_source(source, name)

    def inspect_download_source(self, source, name='', referrer=''):
        def run():
            self.post('status', 'Inspecting link · reading only the page and headers…')
            try:
                resolution = LinkResolver(cancel=self.cancel_scan.is_set).resolve(source, referrer)
            except ResolutionCancelled:
                self.post('status', 'Link search cancelled.')
                return
            self.post('call', lambda: self.show_download_resolution(resolution, name))
        self.work(run)

    def show_download_resolution(self, resolution, name=''):
        if resolution.direct:
            self.confirm_download(resolution.candidates[0], name or resolution.title)
            return
        dialog = self.dialog('Download links found', 860, 660)
        ctk.CTkLabel(dialog, text=resolution.title[:90] or 'Choose a link', font=('Segoe UI', 23, 'bold'),
                     wraplength=790, justify='left').pack(padx=25, pady=(24, 8), anchor='w')
        host = urllib.parse.urlsplit(resolution.final_url).hostname or ''
        ctk.CTkLabel(dialog, text=f'{len(resolution.candidates)} link(s) found on {host}\nChoose a link to verify. No file has been downloaded yet.',
                     text_color=MUTED, justify='left', wraplength=790).pack(padx=25, pady=(0, 15), anchor='w')
        links = ctk.CTkScrollableFrame(dialog, height=365, fg_color=PANEL)
        links.pack(fill='both', expand=True, padx=25, pady=(0, 14))
        if not resolution.candidates:
            ctk.CTkLabel(links, text=resolution.note, text_color=MUTED, wraplength=730, justify='left').pack(padx=16, pady=20)
        for candidate in resolution.candidates:
            row = ctk.CTkFrame(links, fg_color='#18243a', corner_radius=12)
            row.pack(fill='x', padx=6, pady=5)
            ctk.CTkLabel(row, text=candidate.label[:100], text_color=WHITE, wraplength=570, justify='left', anchor='w').pack(fill='x', padx=14, pady=(10, 3))
            ctk.CTkLabel(row, text=f'{candidate.host}  ·  {candidate.kind}', text_color=MUTED, anchor='w').pack(fill='x', padx=14, pady=(0, 5))
            def inspect(c=candidate):
                dialog.destroy()
                self.inspect_download_source(c.url, name or resolution.title, c.source_page)
            self._button(row, 'Verify this link →', inspect, width=170).pack(anchor='e', padx=12, pady=(0, 10))
        self._button(dialog, 'Open page in browser', lambda: webbrowser.open(resolution.final_url), width=790).pack(padx=25, pady=5)
        self._button(dialog, 'Cancel', dialog.destroy, width=790).pack(padx=25, pady=(5, 20))

    def confirm_download(self, candidate, name=''):
        dialog = self.dialog('Confirm download', 820, 630)
        ctk.CTkLabel(dialog, text='Check the file before downloading.', font=('Segoe UI', 24, 'bold'), wraplength=750).pack(padx=26, pady=(26, 16), anchor='w')
        size = 'size not provided by server' if candidate.size is None else f'{candidate.size / (1024**3):.2f} GiB' if candidate.size >= 1024**3 else f'{candidate.size / (1024**2):.1f} MiB' if candidate.size >= 1024**2 else f'{candidate.size:,} bytes'
        ctk.CTkLabel(dialog, text=f'Host: {candidate.host}\nFile: {candidate.filename or candidate.label}\nSize: {size}', text_color=MUTED,
                     justify='left', wraplength=750).pack(padx=26, pady=(0, 12), anchor='w')
        url = ctk.CTkTextbox(dialog, height=90, width=760, fg_color=PANEL, font=('Consolas', 11), wrap='word')
        url.pack(padx=26, pady=(0, 14), fill='x')
        url.insert('1.0', candidate.url)
        url.configure(state='disabled')
        proposed = Path(candidate.filename).stem if candidate.filename else name
        proposed = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', name or proposed).strip(' .')[:100]
        folder = ctk.CTkEntry(dialog, height=42, width=760, placeholder_text='Folder name in REPACKS/downloads')
        folder.pack(padx=26, pady=(0, 10), fill='x')
        folder.insert(0, proposed)
        ctk.CTkLabel(dialog, text='The download starts only after you click below.\nThe file will then be scanned; no program will be launched.',
                     text_color=MUTED, justify='left', wraplength=750).pack(padx=26, pady=(0, 16), anchor='w')
        def approve():
            selected_name = folder.get().strip()
            if not self.valid_download_name(selected_name):
                messagebox.showerror('Invalid folder', 'Choose a simple folder name without reserved Windows characters.', parent=dialog)
                return
            output = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', candidate.filename).strip(' .') if candidate.kind == 'file' else ''
            if output and not self.valid_download_name(output):
                output = 'download' + Path(output).suffix
            dialog.destroy()
            self.begin_download(candidate.url, selected_name, candidate.source_page if candidate.kind == 'file' else '', output)
        self._button(dialog, 'Confirm and download', approve, primary=True, width=760).pack(padx=26, pady=6)
        self._button(dialog, 'Cancel', dialog.destroy, width=760).pack(padx=26, pady=(6, 18))

    @staticmethod
    def valid_download_name(name):
        return bool(name and name not in ('.', '..') and not any(c in name for c in '<>:"/\\|?*\r\n\x00') and name[-1:] not in (' ', '.') and
                    name.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))})

    def begin_download(self, source, name, referrer='', output_name=''):
        if self.busy:
            return
        self.download_form = (source, name)
        if not self.valid_download_name(name):
            messagebox.showerror('Download', 'Enter a simple folder name for this download.', parent=self)
            return
        destination = (self.root_path / 'downloads' / name).resolve()
        if not destination.is_relative_to((self.root_path / 'downloads').resolve()):
            return
        self._resume_download = (source, name, referrer, output_name)
        self._download_stop_reason = ''
        self.download = None
        self.transfer = {'phase': 'preparing', 'name': name, 'destination': str(destination)}
        def run():
            job = Download(source, destination, lambda line: self.post('log', line), referrer=referrer, output_name=output_name)
            self.download = job
            if self.cancel_scan.is_set():
                job.cancel()
            else:
                self.post('transfer', {'phase': 'downloading'})
                self.post('status', 'Downloading · track progress in Downloads')
            code = job.run()
            if job.cancelled or self.cancel_scan.is_set():
                self.finish_download_stop()
                return
            if code != 0:
                raise RuntimeError(f'aria2 exited with code {code}. Check the log and resume using the same link.')
            self.post('status', 'Download complete · scanning files…')
            self.post('transfer', {'phase': 'scanning', 'ratio': 1.0, 'speed': '—', 'eta': '—', 'connections': '0', 'seeders': '0'})
            result = Scanner(progress=lambda s: self.post('status', s), cancel=self.cancel_scan.is_set).scan(destination)
            if self.cancel_scan.is_set():
                self.finish_download_stop()
                return
            atomic_json(STATE / 'reports' / ('download-' + hashlib.sha256(str(destination).encode()).hexdigest()[:16] + '.json'), result.to_dict())
            self.post('log', '\n' + result.status)
            for finding in result.findings:
                self.post('log', finding.severity.upper() + ' · ' + finding.message + ' · ' + finding.path)
            self.post('status', 'Download complete · ' + result.status + ' · extract the ZIP, then scan the game before launching')
            self.post('transfer', {'phase': 'completed', 'ratio': 1.0})
        self.work(run)

    def pause_download(self):
        if self.transfer.get('phase') in ('preparing', 'downloading'):
            self.stop_download('paused')

    def cancel_download(self):
        if self.transfer.get('phase') == 'paused':
            self.transfer.update(phase='cancelled', speed='—', eta='—', connections='0', seeders='0')
            self.status_text.set('Download cancelled · partial files kept')
        elif self.transfer.get('phase') in ('preparing', 'downloading', 'scanning'):
            self.stop_download('cancelled')

    def stop_download(self, reason):
        self._download_stop_reason = reason
        self.transfer['phase'] = 'stopping'
        self.cancel_scan.set()
        if self.download:
            self.download.cancel()

    def finish_download_stop(self):
        phase = self._download_stop_reason or 'cancelled'
        self.post('transfer', {'phase': phase, 'speed': '—', 'eta': '—', 'connections': '0', 'seeders': '0'})
        self.post('status', ('Download paused' if phase == 'paused' else 'Download cancelled') + ' · partial files kept')

    def resume_download(self):
        if not self.busy and self.transfer.get('phase') == 'paused' and self._resume_download:
            self.begin_download(*self._resume_download)

    def extract_dialog(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self, initialdir=str(self.root_path / 'downloads'), filetypes=[('ZIP', '*.zip')])
        if not path:
            return
        name = re.sub(r'[<>:"/\\|?*]', '_', Path(path).stem).strip(' .')
        destination = self.root_path / 'games' / (name or ('jeu-' + uuid.uuid4().hex[:8]))
        def run():
            # Extraction does not execute files. The resulting directory is scanned before launch.
            extract_zip(Path(path), destination, progress=lambda t: self.post('status', t))
            result = Scanner(progress=lambda s: self.post('status', s), inspect_archives=False).scan(destination)
            game_candidates = library.candidates(destination)
            def finish():
                if game_candidates:
                    game = Game.local(destination, game_candidates[0])
                    self.games = [g for g in self.games if g.id != game.id] + [game]
                    self.results[game.id] = result
                    atomic_json(STATE / 'reports' / (game.id + '.json'), result.to_dict())
                    library.save_library(self.games)
                    self.selected = game
                    self.show_library()
                self.status_text.set('Extraction complete · ' + result.status)
            self.post('call', finish)
        self.work(run)

    def show_protection(self, game=None):
        self.current_page = 'protection'
        self.clear()
        ctk.CTkLabel(self.content, text='Check before you play.', font=('Segoe UI', 36, 'bold')).pack(anchor='w', pady=(12, 8))
        ctk.CTkLabel(self.content, text='Known signatures · Ren’Py scripts · hidden payloads · proxy DLLs · sensitive scripts', text_color='#88a9ff', font=('Segoe UI', 13)).pack(anchor='w', pady=(0, 18))
        note = 'Local protection when launching from Nexus. No system monitoring driver. No guarantee against every threat.\nIncomplete or suspicious results block normal launch. Manual launch requires confirmation; files are never sent to a scanning service.'
        ctk.CTkLabel(self.content, text=note, justify='left', text_color=MUTED, wraplength=1100).pack(anchor='w', pady=(0, 18))
        buttons = ctk.CTkFrame(self.content, fg_color='transparent')
        buttons.pack(fill='x', pady=(0, 15))
        game = game or self.selected
        if game:
            self._button(buttons, 'Scan · ' + game.title[:30], lambda g=game: self.scan_game(g), primary=True, width=310).pack(side='left', padx=(0, 8))
            if game.root:
                self._button(buttons, 'Windows scan', lambda g=game: self.defender_scan(g), width=130).pack(side='left', padx=4)
        self._button(buttons, 'Reports', self.open_reports, width=115).pack(side='left', padx=4)
        self._button(buttons, 'Quarantine', self.open_quarantine, width=130).pack(side='left', padx=4)
        self._button(buttons, 'Cancel scan', self.cancel_scan.set, width=160).pack(side='right', padx=4)
        if game and game.source == 'REPACKS':
            manual = ctk.CTkFrame(self.content, fg_color='transparent')
            manual.pack(fill='x', pady=(0, 12))
            self._button(manual, 'Skip scan and play…', lambda: self.skip_scan_and_play(game), width=220).pack(side='left')
            ctk.CTkLabel(manual, text='Manual override · confirmation required', text_color=AMBER,
                         font=('Segoe UI', 11)).pack(side='left', padx=12)
        report = ctk.CTkTextbox(self.content, fg_color=PANEL, font=('Consolas', 12), text_color='#c7d4ea', corner_radius=20)
        report.pack(fill='both', expand=True)
        data = self.results.get(game.id).to_dict() if game and game.id in self.results else library.read_json(STATE / 'reports' / (game.id + '.json'), {}) if game else {}
        if data:
            report.insert('end', f"{game.title}\n{data.get('status', 'Report')}\n{data.get('files', 0)} files inventoried\n\n")
            for finding in data.get('findings', []):
                report.insert('end', f"[{finding['severity'].upper()}] {finding['message']}\n  {finding['path']}\n\n")
            report.insert('end', '\nSHA-256 OF ACTIVE FILES\n\n')
            for path, digest in data.get('hashes', {}).items():
                report.insert('end', f'{digest}  {path}\n')
        else:
            report.insert('end', 'No report for this game. Run a scan.\n\nNames such as setup.py / Setup.exe and file size are clues, not proof.\nRAR/7z, encrypted or oversized archives must be extracted and scanned.\nEXE/DLL content may be obfuscated: no indicators detected does not guarantee safety.')
        report.configure(state='disabled')

    def open_reports(self):
        path = STATE / 'reports'
        path.mkdir(exist_ok=True)
        os.startfile(str(path))

    def defender_scan(self, game):
        def run():
            self.post('status', 'Checking Microsoft Defender availability…')
            state = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', '(Get-MpComputerStatus).AntivirusEnabled'],
                                   capture_output=True, timeout=20, creationflags=0x08000000)
            if state.stdout.decode(errors='replace').strip().lower() != 'true':
                raise RuntimeError('Microsoft Defender is inactive. Complete your Malwarebytes scan; Nexus does not change antivirus settings.')
            root = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'Microsoft/Windows Defender/Platform'
            paths = sorted(root.glob('*/MpCmdRun.exe'), reverse=True)
            paths.append(Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Windows Defender/MpCmdRun.exe')
            engine = next((p for p in paths if p.is_file()), None)
            if not engine:
                raise RuntimeError('Microsoft Defender engine not found.')
            self.post('status', 'Windows scan in progress · no automatic remediation requested…')
            scan = subprocess.run([str(engine), '-Scan', '-ScanType', '3', '-File', game.root, '-DisableRemediation'],
                                  capture_output=True, creationflags=0x08000000)
            text = scan.stdout.decode('utf-8', errors='replace') + scan.stderr.decode('utf-8', errors='replace')
            report = STATE / 'reports' / (game.id + '-defender.txt')
            report.parent.mkdir(exist_ok=True)
            report.write_text(f'Exit code: {scan.returncode}\n\n{text}', encoding='utf-8')
            if scan.returncode != 0:
                def block():
                    self.external_blocks[game.id] = {'code': scan.returncode, 'time': time.time()}
                    atomic_json(STATE / 'native-blocks.json', self.external_blocks)
                self.post('call', block)
                self.post('error', f'Windows scan: detection or error (code {scan.returncode}). Check the report and Windows Security. Launch blocked.')
            else:
                def unblock():
                    self.external_blocks.pop(game.id, None)
                    atomic_json(STATE / 'native-blocks.json', self.external_blocks)
                self.post('call', unblock)
                self.post('status', 'Windows scan complete · no threats reported by this command · report saved')
        self.work(run)

    def open_quarantine(self):
        path = STATE / 'quarantine'
        path.mkdir(exist_ok=True)
        os.startfile(str(path))

    def toggle_fullscreen(self, event=None):
        self._fullscreen = not self._fullscreen
        self.attributes('-fullscreen', self._fullscreen)

    def leave_fullscreen(self):
        self._fullscreen = False
        self.attributes('-fullscreen', False)

    def close(self):
        if self.busy and not messagebox.askyesno('Quit Nexus', 'An operation is running. Quit and interrupt it?', parent=self):
            return
        self.cancel_scan.set()
        self._skip_pending_launch = False
        if self.download:
            self.download.cancel()
        if self._tray:
            self._tray.stop()
        library.save_library(self.games)
        try:
            self.updater.on_close()
        except OSError as exc:
            (STATE / 'update-check.log').write_text(str(exc), encoding='utf-8')
        self.destroy()

    def hide_to_tray(self):
        try:
            if self._tray is None:
                import pystray
                image = Image.open(library.asset_path('assets/nexus.ico')).convert('RGBA')
                self._tray = pystray.Icon('NexusRepacks', image, 'Nexus Repacks', menu=pystray.Menu(
                    pystray.MenuItem('Open Nexus Repacks', lambda icon, item: self.post('call', self.restore_from_tray), default=True),
                    pystray.MenuItem('Quit', lambda icon, item: self.post('call', self.close))))
                self._tray.run_detached()
            self._tray.visible = True
            self.withdraw()
        except Exception as exc:
            self.status_text.set(f'Game launched · notification area unavailable: {exc}')

    def restore_from_tray(self):
        self.deiconify()
        self.state('zoomed')
        self.lift()
        self.focus_force()
        if self._tray:
            self._tray.visible = False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--updated', action='store_true', help='Restore a transfer paused for an application update')
    parser.add_argument('--page', choices=('library', 'catalog', 'downloads', 'protection'), default='library',
                        help='Open a specific application page')
    parser.add_argument('--scan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preview', type=Path, help='Capture only the Nexus window and exit, without launching any game')
    args = parser.parse_args()
    if args.scan:
        result = Scanner(progress=lambda s: print(s, flush=True)).scan(args.scan)
        if args.output:
            atomic_json(args.output, result.to_dict())
        print(result.status)
        return 2 if result.blocked else 0
    from nexus_repacks.cinematic import CinematicNexus
    app = CinematicNexus(smoke=args.smoke_test)
    if args.page != 'library':
        getattr(app, 'show_' + args.page)()
    if args.updated:
        app.restore_update_session()
    if args.smoke_test:
        # Start after subclass construction: frozen startup can take >250 ms.
        app.after(800, app.destroy)
    if args.preview:
        from PIL import ImageGrab
        app.games = library.discover(app.root_path / 'games')
        app.show_library()
        def capture():
            app.update_idletasks()
            box = (app.winfo_rootx(), app.winfo_rooty(), app.winfo_rootx() + app.winfo_width(), app.winfo_rooty() + app.winfo_height())
            args.preview.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(bbox=box).save(args.preview)
            app.destroy()
        app.after(2500, capture)
    app.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
