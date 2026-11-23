"""Nexus View's host dashboard. Valid codes connect while the host allows connections."""
import ctypes
import os
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import webbrowser
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw
import pystray
from host.display import display_info,lan_addresses

BG,SIDE,CARD,FIELD='#090d13','#0d131d','#111b28','#0a121e'
EDGE,TEXT,MUTED,ACCENT='#233248','#eaf1fa','#8d9eb5','#64d4f3'
BASE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))


class HostUI:
    def __init__(self,state,port,start_hidden=False):
        self.state,self.port=state,port
        self.root=None
        self.stop_callback=None
        self.current='overview'
        self.connection_requests=True
        self.last_metrics={}
        self.last_refresh=0
        self.addresses=lan_addresses()
        self.start_hidden=start_hidden
        self.tray=None
        self.tray_ready=threading.Event()
        self.tray_error=None
        self.tray_active=None
        self.closing=False

    async def approve(self,peer,profile):
        # The server validates the secret code before calling this gate.
        return self.connection_requests

    @staticmethod
    def label(parent,text='',size=13,color=TEXT,bold=False,**kw):
        return ctk.CTkLabel(parent,text=text,text_color=color,font=('Segoe UI',size,'bold' if bold else 'normal'),**kw)

    @staticmethod
    def button(parent,text,command,primary=False,**kw):
        return ctk.CTkButton(parent,text=text,command=command,height=38,corner_radius=7,
            fg_color=ACCENT if primary else '#1a293b',hover_color='#98e8fc' if primary else '#263c55',
            text_color='#061824' if primary else TEXT,font=('Segoe UI',12,'bold'),**kw)

    def card(self,page,title,description=''):
        outer=ctk.CTkFrame(self.pages[page],fg_color=CARD,border_color=EDGE,border_width=1,corner_radius=12)
        outer.pack(fill='x',padx=4,pady=(0,16))
        inner=ctk.CTkFrame(outer,fg_color='transparent');inner.pack(fill='x',padx=23,pady=21)
        self.label(inner,title,16,bold=True).pack(anchor='w')
        if description:self.label(inner,description,12,MUTED,wraplength=680,justify='left').pack(anchor='w',pady=(5,14))
        return inner

    def run(self):
        ctk.set_appearance_mode('dark')
        try:ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Nexus.View.Host.1')
        except OSError:pass
        root=self.root=ctk.CTk(fg_color=BG)
        root.title('Nexus View — PC hôte')
        root.geometry('1100x800');root.minsize(960,680)
        root.grid_columnconfigure(1,weight=1);root.grid_rowconfigure(0,weight=1)
        self.logo=Image.open(BASE/'assets'/'nexus-emblem.png').convert('RGBA')
        self.icon=ImageTk.PhotoImage(self.logo.resize((64,64)));root.iconphoto(True,self.icon)
        try:root.iconbitmap(str(BASE/'assets'/'nexus.ico'))
        except tk.TclError:pass
        self.brand=ctk.CTkImage(self.logo,self.logo,size=(40,45))
        self.hero_image=ctk.CTkImage(self.logo,self.logo,size=(128,144))
        side=ctk.CTkFrame(root,width=222,fg_color=SIDE,corner_radius=0)
        side.grid(row=0,column=0,sticky='nsew');side.grid_propagate(False)
        identity=ctk.CTkFrame(side,fg_color='transparent');identity.pack(fill='x',padx=22,pady=(30,36))
        ctk.CTkLabel(identity,text='',image=self.brand).pack(side='left',padx=(0,11))
        self.label(identity,'NEXUS',21,bold=True).pack(anchor='w')
        self.label(identity,'VIEW / DESKTOP HOST',9,MUTED).pack(anchor='w')
        self.label(side,'ESPACE DE TRAVAIL',10,'#61758e',True).pack(anchor='w',padx=24,pady=(0,12))
        self.navigation={}
        for key,title in [('overview','Vue d’ensemble'),('connection','Connexion'),('display','Image & performances'),('permissions','Autorisations')]:
            button=ctk.CTkButton(side,text=title,anchor='w',height=43,corner_radius=7,
                fg_color='transparent',hover_color='#172536',text_color=MUTED,font=('Segoe UI',12),
                command=lambda key=key:self.select(key))
            button.pack(fill='x',padx=13,pady=3);self.navigation[key]=button
        bottom=ctk.CTkFrame(side,fg_color='transparent');bottom.pack(side='bottom',fill='x',padx=21,pady=24)
        self.side_status=self.label(bottom,'●  Hôte en démarrage',11,ACCENT,True,wraplength=180,justify='left')
        self.side_status.pack(anchor='w',pady=(0,16))
        self.button(bottom,'Quitter Nexus View',self.quit).pack(fill='x',pady=(0,15))
        self.label(bottom,'Nexus View  /  0.4.3',10,'#61758e').pack(anchor='w')
        self.label(bottom,'Windows • H.264 • WebRTC / HTTPS',9,'#61758e').pack(anchor='w',pady=(4,0))
        main=ctk.CTkFrame(root,fg_color=BG,corner_radius=0);main.grid(row=0,column=1,sticky='nsew')
        main.grid_columnconfigure(0,weight=1);main.grid_rowconfigure(1,weight=1)
        head=ctk.CTkFrame(main,fg_color='transparent');head.grid(row=0,column=0,sticky='ew',padx=28,pady=(28,20))
        self.eyebrow=self.label(head,'',10,ACCENT,True);self.eyebrow.pack(anchor='w')
        title=ctk.CTkFrame(head,fg_color='transparent');title.pack(fill='x',pady=(10,5))
        self.heading=self.label(title,'',29,bold=True);self.heading.pack(side='left')
        self.status=ctk.CTkLabel(title,text='DÉMARRAGE',fg_color='#173044',text_color=ACCENT,
            corner_radius=7,height=28,font=('Segoe UI',10,'bold'))
        self.status.pack(side='right',padx=(8,0))
        self.subtitle=self.label(head,'',12,MUTED,wraplength=690,justify='left');self.subtitle.pack(anchor='w')
        container=ctk.CTkFrame(main,fg_color='transparent');container.grid(row=1,column=0,sticky='nsew',padx=(24,12))
        container.grid_columnconfigure(0,weight=1);container.grid_rowconfigure(0,weight=1)
        self.pages={key:ctk.CTkScrollableFrame(container,fg_color=BG,corner_radius=0) for key in self.navigation}
        for page in self.pages.values():page.grid(row=0,column=0,sticky='nsew')
        footer=ctk.CTkFrame(main,fg_color=SIDE,corner_radius=0,height=66)
        footer.grid(row=2,column=0,sticky='ew')
        self.label(footer,'Fermer réduit Nexus View dans la zone de notification.',10,MUTED).pack(side='left',padx=25,pady=23)
        self.disconnect_button=self.button(footer,'Déconnecter',self.disconnect,width=110)
        self.disconnect_button.pack(side='right',padx=(8,24),pady=14)
        self.button(footer,'Ouvrir le navigateur',lambda:webbrowser.open(f'http://localhost:{self.port}'),primary=True,width=155).pack(side='right',pady=14)
        self.control=tk.BooleanVar(value=self.state.control_enabled)
        self.requests=tk.BooleanVar(value=True)
        self.notice=tk.StringVar(value='')
        self._overview();self._connection();self._display();self._permissions()
        self.select('overview')
        self.start_tray()
        root.protocol('WM_DELETE_WINDOW',self.hide_to_tray)
        root.bind('<Unmap>',self.on_minimize,add='+')
        if self.start_hidden:root.after(200,self.hide_to_tray)
        root.after(150,self.poll);root.mainloop()

    def start_tray(self):
        self.idle_icon=self.logo.resize((64,64))
        self.active_icon=self.idle_icon.copy()
        ImageDraw.Draw(self.active_icon).ellipse((43,43,63,63),fill='#ef576e',outline='white',width=2)
        def dispatch(action):
            if not self.closing:self.root.after(0,action)
        self.tray=pystray.Icon('NexusView',self.idle_icon,'Nexus View — en attente',menu=pystray.Menu(
            pystray.MenuItem('Ouvrir Nexus View',lambda icon,item:dispatch(self.show_window),default=True),
            pystray.MenuItem('Copier le code',lambda icon,item:dispatch(lambda:self.copy(self.state.token,'Code copié.'))),
            pystray.MenuItem('Copier le lien Internet',lambda icon,item:dispatch(self.copy_public_url)),
            pystray.MenuItem('Nouveau lien Internet',lambda icon,item:dispatch(self.state.restart_public_tunnel)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Déconnecter',lambda icon,item:dispatch(self.disconnect)),
            pystray.MenuItem('Quitter Nexus View',lambda icon,item:dispatch(self.quit))))
        def worker():
            try:
                def ready(icon):
                    icon.visible=True;self.tray_ready.set()
                self.tray.run(setup=ready)
            except Exception as exc:
                self.tray_error=str(exc);self.state.error('Zone de notification : '+str(exc))
        threading.Thread(target=worker,name='NexusTray',daemon=True).start()

    def show_window(self):
        self.root.deiconify();self.root.state('normal');self.root.lift();self.root.focus_force()

    def hide_to_tray(self):
        if self.closing:return
        if self.tray_error:
            self.notice.set('Zone de notification indisponible : '+self.tray_error)
            return
        if not self.tray_ready.is_set():
            self.root.after(200,self.hide_to_tray)
            return
        self.root.withdraw()

    def on_minimize(self,event):
        if event.widget is self.root and self.root.state()=='iconic':
            self.root.after(0,self.hide_to_tray)

    def _overview(self):
        hero=self.card('overview','Votre PC, depuis un lien Internet privé.')
        artwork=ctk.CTkLabel(hero,text='',image=self.hero_image);artwork.pack(side='right',padx=(18,5))
        self.label(hero,'NEXUS VIEW',11,ACCENT,True).pack(anchor='w',pady=(10,4))
        self.label(hero,'Un bureau. Tous vos écrans.',23,bold=True).pack(anchor='w')
        self.label(hero,'Image native, encodage NVIDIA et contrôle explicite.\nUn code valide ouvre directement la session.',12,MUTED,justify='left').pack(anchor='w',pady=(10,20))
        self.button(hero,'Connecter un appareil  →',lambda:self.select('connection'),primary=True,width=190).pack(anchor='w')
        session=self.card('overview','Activité de la session','Un indicateur reste visible dès qu’un appareil reçoit votre bureau.')
        self.session_label=self.label(session,'Aucun appareil connecté',14,ACCENT,True);self.session_label.pack(anchor='w',pady=(0,15))
        row=ctk.CTkFrame(session,fg_color='transparent');row.pack(fill='x')
        self.stats={}
        for index,(key,title) in enumerate([('fps','CADENCE'),('encode','ENCODAGE'),('bitrate','DÉBIT')]):
            box=ctk.CTkFrame(row,fg_color=FIELD,corner_radius=8);box.grid(row=0,column=index,sticky='nsew',padx=(0,9 if index<2 else 0))
            row.grid_columnconfigure(index,weight=1)
            self.label(box,title,9,MUTED,True).pack(anchor='w',padx=15,pady=(12,4))
            self.stats[key]=self.label(box,'—',24,bold=True);self.stats[key].pack(anchor='w',padx=15,pady=(0,12))
        health=self.card('overview','Votre configuration')
        self.health=self.label(health,'Vérification du PC…',12,MUTED,justify='left',wraplength=680);self.health.pack(anchor='w',pady=(10,4))

    def _connection(self):
        pairing=self.card('connection','Connecter un navigateur','Un code valide ouvre la session automatiquement, sans confirmation sur ce PC.')
        self.label(pairing,'CODE DE CONNEXION',10,MUTED,True).pack(anchor='w')
        self.code_variable=tk.StringVar(value=self.state.token)
        code=ctk.CTkEntry(pairing,height=48,fg_color=FIELD,border_color=EDGE,text_color=TEXT,
            font=('Consolas',18),textvariable=self.code_variable)
        code.pack(fill='x',pady=(8,12));code.configure(state='readonly')
        actions=ctk.CTkFrame(pairing,fg_color='transparent');actions.pack(fill='x')
        self.button(actions,'Copier le code',lambda:self.copy(self.state.token,'Code copié.'),primary=True,width=145).pack(side='left')
        self.button(actions,'Générer un nouveau code',self.regenerate_code,width=200).pack(side='left',padx=(12,0))
        self.label(pairing,'Code conservé après redémarrage. Un nouveau code invalide l’ancien et déconnecte la session.',11,MUTED,wraplength=680,justify='left').pack(anchor='w',pady=(12,0))
        internet=self.card('connection','Lien Internet · Cloudflare Try','Un nouveau lien est créé à chaque relancement. Le code de connexion reste conservé.')
        self.public_url_variable=tk.StringVar(value=self.state.public_url)
        self.public_status_variable=tk.StringVar(value=self.state.public_status)
        entry=ctk.CTkEntry(internet,textvariable=self.public_url_variable,height=40,font=('Consolas',12));entry.pack(fill='x',pady=(0,8));entry.configure(state='readonly')
        self.label(internet,textvariable=self.public_status_variable,size=11,color=MUTED,wraplength=650,justify='left').pack(anchor='w')
        row=ctk.CTkFrame(internet,fg_color='transparent');row.pack(fill='x',pady=(12,0))
        self.button(row,'Copier le lien',self.copy_public_url,primary=True,width=145).pack(side='left')
        self.button(row,'Nouveau lien Internet',self.state.restart_public_tunnel,width=190).pack(side='left',padx=(12,0))
        mail=self.card('connection','À qui envoyer les nouveaux liens ?','Ajoutez une ou plusieurs adresses : une par ligne, ou séparées par des virgules ou points-virgules. Le lien et le code Nexus seront envoyés à chaque adresse enregistrée.')
        self.mail_status_variable=tk.StringVar(value=self.state.mail_status)
        self.mail_recipients=ctk.CTkTextbox(mail,height=105,fg_color=FIELD,border_color=EDGE,border_width=1,font=('Segoe UI',13))
        self.mail_recipients.pack(fill='x',pady=(0,8))
        if self.state.link_mailer:self.mail_recipients.insert('1.0','\n'.join(self.state.link_mailer.settings.recipients))
        self.label(mail,textvariable=self.mail_status_variable,size=11,color=MUTED,wraplength=650,justify='left').pack(anchor='w')
        mail_buttons=ctk.CTkFrame(mail,fg_color='transparent');mail_buttons.pack(fill='x',pady=(12,0))
        self.button(mail_buttons,'Enregistrer les destinataires',self.save_mail_recipients,primary=True,width=220).pack(side='left')
        self.button(mail_buttons,'Envoyer le lien actuel',self.state.resend_link_email,width=170).pack(side='left',padx=(12,0))
        network=self.card('connection','Adresses de ce PC','Sur un téléphone ou un autre ordinateur, utilisez une adresse réseau : localhost désigne toujours l’appareil sur lequel il est ouvert.')
        links=[('Sur ce PC',f'http://localhost:{self.port}')]
        if self.state.bind not in ('127.0.0.1','::1'):
            links.extend(('Réseau local',f'http://{ip}:{self.port}') for ip in self.addresses)
        for title,url in links:
            line=ctk.CTkFrame(network,fg_color=FIELD,corner_radius=7);line.pack(fill='x',pady=5)
            self.button(line,'Copier',lambda url=url:self.copy(url,'Adresse copiée.'),width=70).pack(side='right',padx=10,pady=10)
            self.label(line,title,10,MUTED).pack(anchor='w',padx=14,pady=(9,0))
            self.label(line,url,12).pack(anchor='w',padx=14,pady=(0,9))
        if not self.addresses:self.label(network,'Aucune adresse LAN détectée. Vérifiez votre connexion Wi-Fi/Ethernet.',12,'#efbf7c',wraplength=650).pack(anchor='w',pady=10)
        self.label(network,'Le code est obligatoire. Vous pouvez bloquer les nouvelles connexions dans Autorisations.',11,MUTED,wraplength=660,justify='left').pack(anchor='w',pady=(12,0))
        self.label(self.pages['connection'],'',12,ACCENT,textvariable=self.notice).pack(anchor='w',padx=10)

    def _display(self):
        display=self.card('display','Qualité native, sans faux agrandissement')
        self.display_label=self.label(display,'',20,bold=True);self.display_label.pack(anchor='w',pady=(10,4))
        self.label(display,'La vidéo ne peut pas contenir plus de détails que le bureau Windows capturé.',12,MUTED,wraplength=680,justify='left').pack(anchor='w',pady=(0,18))
        self.button(display,'Paramètres d’affichage Windows',lambda:os.startfile('ms-settings:display'),width=235).pack(anchor='w')
        quality=self.card('display','Profils Premium','Choisissez le profil et le débit dans le navigateur avant de démarrer la session.')
        for title,description in [('Premium Auto','Résolution native jusqu’à 4K • cible 120 FPS • plafond 60 Mb/s'),
                                  ('1080p qualité','25 Mb/s • NVENC P4 + AQ • cible 60 FPS'),
                                  ('1080p fluidité','40 Mb/s • NVENC P3 • cible 120 FPS'),
                                  ('4K native','Écran physique ou virtuel 3840 × 2160 requis • 60/120 FPS à mesurer')]:
            self.label(quality,title,13,bold=True).pack(anchor='w',pady=(10,2))
            self.label(quality,description,11,MUTED,wraplength=680,justify='left').pack(anchor='w',pady=(0,5))
        self.label(quality,'La cadence et le débit sont des cibles : les mesures en direct font foi.',11,'#efbf7c',wraplength=680).pack(anchor='w',pady=(14,0))
        diagnostic=self.card('display','Pipeline réel')
        self.pipeline=self.label(diagnostic,'En attente d’une session.',12,MUTED,wraplength=680,justify='left');self.pipeline.pack(anchor='w',pady=(8,0))

    def _permissions(self):
        permissions=self.card('permissions','Vous gardez les commandes','Un code valide ouvre automatiquement la session lorsque les connexions sont autorisées.')
        ctk.CTkSwitch(permissions,text='Autoriser les connexions par code',variable=self.requests,command=self.toggle_requests,
            progress_color=ACCENT,font=('Segoe UI',13)).pack(anchor='w',pady=(8,16))
        ctk.CTkSwitch(permissions,text='Autoriser clavier, souris et manette',variable=self.control,command=self.toggle,
            progress_color=ACCENT,font=('Segoe UI',13)).pack(anchor='w',pady=(0,15))
        self.label(permissions,'Désactiver les commandes laisse la vidéo active en lecture seule.\nLe navigateur doit également activer ses commandes.',12,MUTED,justify='left',wraplength=670).pack(anchor='w',pady=(5,10))
        self.button(permissions,'Terminer la session en cours',self.disconnect,width=235).pack(anchor='w',pady=(12,0))
        security=self.card('permissions','Protection du partage')
        self.label(security,'• Code conservé, remplaçable depuis Connexion\n• Connexion automatique avec un code valide\n• La nouvelle connexion remplace la précédente\n• WebRTC ou lien HTTPS Cloudflare Try\n• Échelle Windows restaurée à la déconnexion',12,MUTED,justify='left').pack(anchor='w',pady=(10,0))

    def select(self,key):
        self.current=key
        titles={'overview':('VUE D’ENSEMBLE','Votre espace distant','État du partage et activité de ce PC, en direct.'),
                'connection':('CONNEXION','Reliez vos appareils','Le navigateur contrôle. Ce PC partage son bureau.'),
                'display':('IMAGE & PERFORMANCES','Chaque détail compte.','Une qualité élevée, des mesures réelles et une résolution native.'),
                'permissions':('AUTORISATIONS','Votre PC. Vos règles.','Vous décidez qui se connecte et ce qui peut être contrôlé.')}
        eye,title,subtitle=titles[key]
        self.eyebrow.configure(text='NEXUS VIEW  /  '+eye);self.heading.configure(text=title);self.subtitle.configure(text=subtitle)
        for name,page in self.pages.items():
            if name==key:page.grid()
            else:page.grid_remove()
            self.navigation[name].configure(fg_color='#142c3b' if name==key else 'transparent',text_color=ACCENT if name==key else MUTED)

    def copy_public_url(self):
        if self.state.public_url:self.copy(self.state.public_url,'Lien Internet copié.')
        else:self.notice.set(self.state.public_status or 'Le lien Internet n’est pas encore disponible.')

    def save_mail_recipients(self):
        if not self.state.link_mailer:
            self.notice.set('Configurez mailto_email et mailto_key dans .env puis relancez Nexus.');return
        try:
            self.state.link_mailer.set_recipients(self.mail_recipients.get('1.0','end'))
            count=len(self.state.link_mailer.settings.recipients)
            self.state.mail_status=f'{count} destinataire(s) enregistré(s) · utilisés au prochain lien' if count else 'Aucun destinataire : l’envoi automatique est désactivé.'
        except (ValueError,OSError):self.notice.set('Une adresse est invalide ou l’enregistrement est impossible. La liste précédente est conservée.')

    def copy(self,text,note):
        self.root.clipboard_clear();self.root.clipboard_append(text);self.notice.set(note)

    def regenerate_code(self):
        try:code=self.state.regenerate_code()
        except Exception as exc:
            messagebox.showerror('Nexus View','Le code n’a pas été changé : '+str(exc),parent=self.root)
            return
        self.code_variable.set(code)
        self.notice.set('Nouveau code enregistré. L’ancien code ne fonctionne plus.')

    def toggle(self):
        self.state.control_enabled=self.control.get()
        if not self.control.get():self.state.release_input()

    def toggle_requests(self):
        self.connection_requests=self.requests.get()

    def disconnect(self):self.state.request_disconnect()

    def quit(self):
        self.closing=True
        self.connection_requests=False;self.disconnect()
        if self.stop_callback:self.stop_callback()
        if self.tray:self.tray.stop()
        self.root.destroy()

    def poll(self):
        import time
        active=self.state.active
        self.public_url_variable.set(self.state.public_url)
        self.public_status_variable.set(self.state.public_status)
        self.mail_status_variable.set(self.state.mail_status)
        if self.tray_ready.is_set() and active!=self.tray_active:
            self.tray_active=active
            self.tray.icon=self.active_icon if active else self.idle_icon
            self.tray.title='Nexus View — '+('PARTAGE ACTIF' if active else 'en attente')
        if active:
            text='CONTRÔLE ACTIF' if self.state.control_allowed else 'LECTURE SEULE'
            self.status.configure(text='  ● '+text+'  ',text_color='#ffb5bf',fg_color='#3a1d2b')
            self.side_status.configure(text='●  PARTAGE ACTIF',text_color='#ffb5bf')
            self.session_label.configure(text='Appareil connecté · '+self.state.peer,text_color='#ffb5bf')
        elif self.state.server_error:
            self.status.configure(text='  ERREUR SERVEUR  ',text_color='#ffb5bf',fg_color='#3a1d2b')
            self.session_label.configure(text=self.state.server_error,text_color='#ffb5bf')
        else:
            ready=self.state.server_ready
            text='EN ATTENTE' if ready else 'DÉMARRAGE'
            self.status.configure(text='  ● '+text+'  ',text_color=ACCENT,fg_color='#173044')
            self.side_status.configure(text='●  '+('Hôte disponible' if ready else 'Démarrage…'),text_color=ACCENT)
            self.session_label.configure(text='Aucun appareil connecté',text_color=ACCENT)
        self.disconnect_button.configure(state='normal' if active else 'disabled')
        if time.monotonic()-self.last_refresh>1:
            self.last_refresh=time.monotonic()
            m=self.state.metrics;d=display_info()
            frames=m['frames'];previous=self.last_metrics
            fps=max(0,(frames-previous.get('frames',frames))/max(.1,self.last_refresh-previous.get('at',self.last_refresh)))
            self.last_metrics={'frames':frames,'at':self.last_refresh}
            self.stats['fps'].configure(text=(f'{fps:.0f} FPS' if active else '—'))
            self.stats['encode'].configure(text=(f"{m['encode_ms']:.1f} ms" if active else '—'))
            self.stats['bitrate'].configure(text=(f"{m.get('target_bitrate',0)/1e6:.0f} Mb/s" if active else '—'))
            screen=f"{d['width']} × {d['height']} · {d['refresh_hz']} Hz"
            nvenc='NVENC disponible et testé' if self.state.nvenc['available'] else 'Encodage logiciel · NVENC indisponible'
            self.health.configure(text=f'Écran principal : {screen}\n{nvenc}\nRéseau : '+('LAN activé' if self.state.bind!='127.0.0.1' else 'Localhost uniquement'))
            self.display_label.configure(text=screen)
            self.pipeline.configure(text=('Conversion GPU NV12' if m.get('pixel_format')=='nv12' else 'Capture DXGI / conversion de repli')+
                f"\nEncodeur : {self.state.encoder} · profil H.264 {self.state.codec_profile}\nRésolution envoyée : {m.get('resolution','—')}\n"+
                (self.state.errors[-1]['message'] if self.state.errors else 'Aucune erreur signalée.'))
        self.root.after(150,self.poll)
