"""Native catalog cards and game details, backed by the publisher's JSON."""
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import urllib.request

import customtkinter as ctk
from PIL import Image, ImageOps

from nexus_repacks import catalog

INK = '#080f16'
PANEL = '#10212c'
TEXT = '#effbff'
DIM = '#9bb7c5'
ICE = '#adefff'


class CatalogView(ctk.CTkFrame):
    def __init__(self, owner):
        super().__init__(owner.content, fg_color=INK, corner_radius=0)
        self.owner = owner
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='Catalog-art')
        self.closed = False
        self.art_cache = {}
        self.art_pending = {}
        self.games = []
        self.selected = None
        self.columns = 3
        self.download_button = None
        self.detail_action = None
        self.last_action_state = None
        self.pack(fill='both', expand=True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', pady=(4, 14))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text='Catalog', font=('Segoe UI', 28, 'bold'), text_color=TEXT).grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(header, text='Find your next adventure. Download it in one click.', text_color=DIM,
                     font=('Segoe UI', 12)).grid(row=1, column=0, sticky='w')
        owner._button(header, '↻  Reload', self.reload, width=115).grid(row=0, column=1, rowspan=2, padx=(12, 0))
        self.search = ctk.CTkEntry(self, placeholder_text='Search games, genres…', height=38,
                                  fg_color=PANEL, border_color='#294754', corner_radius=12)
        self.search.grid(row=1, column=0, sticky='ew', pady=(0, 14))
        self.search.bind('<KeyRelease>', lambda event: self.show_grid())
        self.body = ctk.CTkScrollableFrame(self, fg_color=INK, corner_radius=0,
                                          scrollbar_button_color='#294754')
        self.body.grid(row=2, column=0, sticky='nsew')
        self.body.grid_columnconfigure(0, weight=1)
        self.grid_host = ctk.CTkFrame(self.body, fg_color='transparent')
        self.grid_host.pack(fill='both', expand=True)
        self.reload()

    def destroy(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    def reload(self):
        self.art_cache.clear()
        self.path = catalog.catalog_path(self.owner.root_path)
        try:
            self.games = catalog.load_catalog(self.path)
        except (OSError, ValueError, TypeError) as exc:
            self.games = []
            self.owner.status_text.set('Catalog could not be loaded: ' + str(exc))
            self.error = str(exc)
        else:
            self.error = ''
            self.owner.status_text.set(f'Catalog · {len(self.games)} game(s)')
        self.show_grid()

    def clear_body(self):
        self.download_button = None
        if self.detail_action is not None:
            self.detail_action.destroy()
            self.detail_action = None
        self.last_action_state = None
        for child in self.grid_host.winfo_children():
            child.destroy()
        for index in range(self.columns):
            self.grid_host.grid_columnconfigure(index, weight=0, uniform='', minsize=0)
        self.body._parent_canvas.yview_moveto(0)

    def show_grid(self):
        self.selected = None
        self.clear_body()
        query = self.search.get().strip().casefold()
        games = [game for game in self.games if query in (game.title + ' ' + game.genre).casefold()]
        if self.error or not games:
            self.grid_host.grid_columnconfigure(0, weight=1)
            card = ctk.CTkFrame(self.grid_host, fg_color=PANEL, corner_radius=20)
            card.grid(row=0, column=0, sticky='ew', padx=4, pady=8)
            heading = 'Catalog unavailable' if self.error else 'No matching games' if query else 'New adventures are on their way'
            text = ('Please check the catalog file and reload.\n' + self.error if self.error else
                    'Try another title or genre.' if query else 'Games added to this collection will appear here.')
            ctk.CTkLabel(card, text='◇', text_color=ICE, font=('Segoe UI', 54)).pack(pady=(36, 8))
            ctk.CTkLabel(card, text=heading, font=('Segoe UI', 23, 'bold'), text_color=TEXT).pack(padx=24, pady=8)
            ctk.CTkLabel(card, text=text, wraplength=640, justify='center', text_color=DIM).pack(padx=24, pady=(0, 40))
            return
        self.columns = 3
        for column in range(self.columns):
            self.grid_host.grid_columnconfigure(column, weight=1, uniform='catalog-cards')
        for index, game in enumerate(games):
            card = ctk.CTkFrame(self.grid_host, fg_color=PANEL, corner_radius=16, border_width=1,
                               border_color='#294754')
            card.grid(row=index // self.columns, column=index % self.columns, sticky='nsew', padx=6, pady=8)
            art = ctk.CTkLabel(card, text=game.title[:1].upper(), height=130, text_color=ICE,
                               fg_color='#173541', corner_radius=12, font=('Segoe UI', 45, 'bold'))
            art.pack(fill='x', padx=8, pady=(8, 10))
            self.image(art, game.image or game.icon, (224, 126))
            title = ctk.CTkLabel(card, text=game.title, text_color=TEXT, font=('Segoe UI', 15, 'bold'),
                                 wraplength=200, anchor='w', justify='left')
            title.pack(fill='x', padx=14)
            subtitle = ' · '.join(filter(None, (game.genre, game.size))) or 'PC game'
            ctk.CTkLabel(card, text=subtitle, text_color=DIM, font=('Segoe UI', 10),
                         wraplength=200, anchor='w').pack(fill='x', padx=14, pady=(2, 9))
            self.owner._button(card, 'View game  →', lambda selected=game: self.show_detail(selected),
                               width=120).pack(fill='x', padx=12, pady=(0, 12))
            for widget in (card, art, title):
                widget.bind('<Button-1>', lambda event, selected=game: self.show_detail(selected))

    def show_detail(self, game):
        self.clear_body()
        self.selected = game
        self.grid_host.grid_columnconfigure(0, weight=1)
        self.owner._button(self.grid_host, '←  All games', self.show_grid, width=130).grid(row=0, column=0, sticky='w', padx=4, pady=(4, 14))
        card = ctk.CTkFrame(self.grid_host, fg_color=PANEL, corner_radius=20, border_width=1, border_color='#294754')
        card.grid(row=1, column=0, sticky='ew', padx=4)
        card.grid_columnconfigure(0, weight=1)
        cover = ctk.CTkLabel(card, text=game.title[:1].upper(), height=220, fg_color='#173541',
                             corner_radius=16, text_color=ICE, font=('Segoe UI', 78, 'bold'))
        cover.grid(row=0, column=0, sticky='ew', padx=12, pady=(12, 16))
        self.image(cover, game.image or game.icon, (650, 220))
        heading = ctk.CTkFrame(card, fg_color='transparent')
        heading.grid(row=1, column=0, sticky='ew', padx=24)
        heading.grid_columnconfigure(1, weight=1)
        icon = ctk.CTkLabel(heading, text=game.title[:1], width=48, height=48, fg_color='#173541',
                            corner_radius=10, text_color=ICE, font=('Segoe UI', 24, 'bold'))
        icon.grid(row=0, column=0, rowspan=2, padx=(0, 14))
        self.image(icon, game.icon or game.image, (48, 48))
        ctk.CTkLabel(heading, text=game.title, wraplength=580, anchor='w', justify='left',
                     text_color=TEXT, font=('Segoe UI', 25, 'bold')).grid(row=0, column=1, sticky='w')
        ctk.CTkLabel(heading, text=' · '.join(filter(None, (game.genre, game.size, 'Windows PC'))),
                     text_color=ICE, font=('Segoe UI', 11)).grid(row=1, column=1, sticky='w')
        description = ctk.CTkTextbox(card, height=150, fg_color='transparent', text_color=DIM,
                                     wrap='word', font=('Segoe UI', 13), activate_scrollbars=True)
        description.grid(row=2, column=0, sticky='ew', padx=20, pady=(16, 20))
        description.insert('1.0', game.description)
        description.configure(state='disabled')
        self.detail_description = description
        action = ctk.CTkFrame(self, fg_color='#142b38', corner_radius=14)
        self.detail_action = action
        action.grid(row=3, column=0, sticky='ew', pady=(12, 0))
        action.grid_columnconfigure(0, weight=1)
        self.action_note = ctk.CTkLabel(action, text='', text_color=DIM, font=('Segoe UI', 11),
                                       wraplength=400, anchor='w', justify='left')
        self.action_note.grid(row=0, column=0, sticky='ew', padx=16, pady=16)
        self.download_button = self.owner._button(action, '↓  Download', lambda: self.owner.download_catalog_game(game),
                                                   primary=True, width=170)
        self.download_button.grid(row=0, column=1, padx=16, pady=16)
        self.update_state()

    def update_state(self):
        if not self.selected or not self.download_button:
            return
        game = self.selected
        stamp = (game.id, game.enabled, self.owner.busy)
        if stamp == self.last_action_state:
            return
        self.last_action_state = stamp
        available = game.enabled and not self.owner.busy
        text = ('Download not available yet.' if not game.enabled else
                'Another operation is running. Your current transfer is preserved.' if self.owner.busy else
                'Download files now. Extract and scan them before playing.')
        if self.action_note.cget('text') != text:
            self.action_note.configure(text=text)
        self.download_button.configure(state='normal' if available else 'disabled',
                                       text='↓  Download' if game.enabled else 'Unavailable')

    def image(self, widget, value, size):
        if not value:
            return
        key = (str(self.path.parent), value)
        def apply(source):
            if self.closed or not widget.winfo_exists() or source is None:
                return
            image = ctk.CTkImage(light_image=ImageOps.fit(source, size), dark_image=ImageOps.fit(source, size), size=size)
            widget.configure(image=image, text='')
            widget.catalog_image = image
        if key in self.art_cache:
            apply(self.art_cache[key])
            return
        if key in self.art_pending:
            self.art_pending[key].append(apply)
            return
        self.art_pending[key] = [apply]
        directory = self.path.parent
        def worker():
            image = None
            try:
                if value.startswith(('https://', 'http://')):
                    request = urllib.request.Request(value, headers={'User-Agent': 'NexusRepacks-Catalog/1'})
                    with urllib.request.urlopen(request, timeout=8) as response:
                        if not catalog.web_url(response.url):
                            raise ValueError('Unsupported image redirect')
                        content = response.read(8 * 1024 * 1024 + 1)
                else:
                    with catalog.local_art(directory, value).open('rb') as source:
                        content = source.read(8 * 1024 * 1024 + 1)
                if len(content) > 8 * 1024 * 1024:
                    raise ValueError('Image too large')
                with Image.open(io.BytesIO(content)) as source:
                    if source.width * source.height > 20_000_000:
                        raise ValueError('Image dimensions too large')
                    source.thumbnail((1300, 650))
                    image = source.convert('RGB').copy()
            except Exception:
                pass  # Keep the initial placeholder when artwork is unavailable.
            def finish():
                if self.closed:
                    return
                self.art_cache[key] = image
                for callback in self.art_pending.pop(key, []):
                    callback(image)
            if not self.closed:
                self.owner.post('call', finish)
        self.pool.submit(worker)
