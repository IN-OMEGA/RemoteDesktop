"""Download dashboard. Transfer state belongs to the application, not this view."""
import os
import webbrowser
from pathlib import Path
import customtkinter as ctk
from nexus_repacks.motion import Motion

INK='#080f16'
PANEL='#10212c'
ACCENT='#adefff'
MUTED='#9bb7c5'


class DownloadView(ctk.CTkFrame):
    def destroy(self):
        # CTkFrame forwards bindings to its internal canvas; own our timer cleanup.
        self.motion.clear()
        super().destroy()

    def __init__(self, owner):
        super().__init__(owner.content,fg_color=INK,corner_radius=0)
        self.owner=owner
        self.motion=Motion(self)
        self.last=None
        self.shown_ratio=0
        self.details_open=False
        self.pack(fill='both',expand=True)
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(1,weight=1)
        title=ctk.CTkFrame(self,fg_color='transparent')
        title.grid(row=0,column=0,sticky='ew',pady=(4,16))
        ctk.CTkLabel(title,text='Downloads',font=('Segoe UI',28,'bold'),text_color='#effbff').pack(anchor='w')
        ctk.CTkLabel(title,text='A new adventure, one link away.',text_color=MUTED,font=('Segoe UI',12)).pack(anchor='w')
        self.body=ctk.CTkScrollableFrame(self,fg_color=INK,corner_radius=0,scrollbar_button_color='#294754')
        self.body.grid(row=1,column=0,sticky='nsew')
        self.body.grid_columnconfigure(0,weight=4,uniform='dashboard')
        self.body.grid_columnconfigure(1,weight=5,uniform='dashboard')
        form=ctk.CTkFrame(self.body,fg_color=PANEL,corner_radius=18,border_width=1,border_color='#294754')
        form.grid(row=0,column=0,sticky='nsew',padx=(0,14))
        form.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(form,text='NEW DOWNLOAD',text_color=ACCENT,font=('Segoe UI',10,'bold')).grid(row=0,column=0,sticky='w',padx=20,pady=(18,6))
        ctk.CTkLabel(form,text='Add your next game',text_color='#effbff',font=('Segoe UI',20,'bold')).grid(row=1,column=0,sticky='w',padx=20,pady=(0,12))
        ctk.CTkLabel(form,text='Download link',text_color=MUTED,font=('Segoe UI',11)).grid(row=2,column=0,sticky='w',padx=20)
        owner.download_source=ctk.CTkEntry(form,placeholder_text='https://… or magnet:…',height=38,fg_color=INK,border_color='#365563',corner_radius=10)
        owner.download_source.grid(row=3,column=0,sticky='ew',padx=20,pady=(3,10))
        if owner.download_form[0]:
            owner.download_source.insert(0,owner.download_form[0])
        self.inspect=owner._button(form,'Check link',owner.start_download,primary=True,width=150)
        ctk.CTkLabel(form,text='Folder name',text_color=MUTED,font=('Segoe UI',11)).grid(row=4,column=0,sticky='w',padx=20)
        owner.download_name=ctk.CTkEntry(form,placeholder_text='e.g. My next game',height=36,fg_color=INK,border_color='#294754',corner_radius=10)
        owner.download_name.grid(row=5,column=0,sticky='ew',padx=20,pady=(3,14))
        if owner.download_form[1]:
            owner.download_name.insert(0,owner.download_form[1])
        self.torrent=owner._button(form,'Choose a .torrent',owner.choose_torrent,width=150)
        self.inspect.grid(row=6,column=0,sticky='ew',padx=20,pady=(0,8))
        self.torrent.grid(row=7,column=0,sticky='ew',padx=20,pady=(0,8))
        ctk.CTkLabel(form,text='Web page · direct link · magnet · torrent\nConfirm the file before transferring.',text_color=MUTED,font=('Segoe UI',10),justify='left').grid(row=8,column=0,sticky='w',padx=20,pady=(4,18))
        card=ctk.CTkFrame(self.body,fg_color=PANEL,corner_radius=18,border_width=1,border_color='#294754')
        card.grid(row=0,column=1,sticky='nsew')
        card.grid_columnconfigure(0,weight=1)
        self.phase=ctk.CTkLabel(card,text='READY TO DOWNLOAD',text_color=ACCENT,font=('Segoe UI',10,'bold'))
        self.phase.grid(row=0,column=0,sticky='w',padx=20,pady=(15,4))
        self.name=ctk.CTkLabel(card,text='No active transfer',font=('Segoe UI',18,'bold'),anchor='w',wraplength=320,justify='left')
        self.name.grid(row=1,column=0,sticky='ew',padx=20)
        self.percent=ctk.CTkLabel(card,text='—',text_color=ACCENT,font=('Segoe UI',24,'bold'))
        self.percent.grid(row=2,column=0,sticky='w',padx=20,pady=(14,0))
        self.bar=ctk.CTkProgressBar(card,height=7,fg_color='#243f4b',progress_color=ACCENT,corner_radius=4)
        self.bar.grid(row=3,column=0,columnspan=2,sticky='ew',padx=20,pady=(10,8))
        self.bar.set(0)
        self.volume=ctk.CTkLabel(card,text='The download starts after your confirmation.',text_color=MUTED,font=('Segoe UI',11),anchor='w',wraplength=320,justify='left')
        self.volume.grid(row=4,column=0,columnspan=2,sticky='ew',padx=20)
        metrics=ctk.CTkFrame(card,fg_color='transparent')
        metrics.grid(row=5,column=0,columnspan=2,sticky='ew',padx=20,pady=(14,14))
        self.metrics={}
        for i,(key,label) in enumerate((('speed','SPEED'),('eta','TIME LEFT'),('connections','CONNECTIONS'),('seeders','SEEDERS'))):
            metrics.grid_columnconfigure(i%2,weight=1)
            cell=ctk.CTkFrame(metrics,fg_color='#142b38',corner_radius=10)
            cell.grid(row=i//2,column=i%2,sticky='ew',padx=(0,8) if i%2==0 else (0,0),pady=4)
            ctk.CTkLabel(cell,text=label,text_color=MUTED,font=('Segoe UI',8,'bold')).pack(anchor='w',padx=12,pady=(5,0))
            self.metrics[key]=ctk.CTkLabel(cell,text='—',font=('Segoe UI',15,'bold'),text_color='#effbff')
            self.metrics[key].pack(anchor='w',padx=12,pady=(0,5))
        controls=ctk.CTkFrame(card,fg_color='transparent')
        controls.grid(row=6,column=0,columnspan=2,sticky='ew',padx=16,pady=(0,14))
        controls.grid_columnconfigure((0,1),weight=1)
        self.pause=owner._button(controls,'Pause',owner.pause_download,width=95)
        self.pause.grid(row=0,column=0,sticky='ew',padx=4,pady=4)
        self.resume=owner._button(controls,'Resume',owner.resume_download,width=105)
        self.resume.grid(row=0,column=1,sticky='ew',padx=4,pady=4)
        self.cancel=owner._button(controls,'Cancel',owner.cancel_download,width=95)
        self.cancel.configure(text_color='#ffc2b7',border_color='#72514f')
        self.cancel.grid(row=1,column=0,sticky='ew',padx=4,pady=4)
        self.open=owner._button(controls,'Open folder',self.open_folder,width=140)
        self.open.grid(row=1,column=1,sticky='ew',padx=4,pady=4)
        sources=ctk.CTkFrame(self.body,fg_color=PANEL,corner_radius=16)
        sources.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(16,0))
        ctk.CTkLabel(sources,text='WHERE TO FIND REPACKS',text_color=ACCENT,font=('Segoe UI',10,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',padx=18,pady=(14,2))
        ctk.CTkLabel(sources,text='Open a site, find a game, then paste its link here.',text_color=MUTED,font=('Segoe UI',11)).grid(row=1,column=0,columnspan=3,sticky='w',padx=18,pady=(0,8))
        self.source_buttons=[]
        for column,(label,url) in enumerate((('Repack Games  ↗','https://repack-games.com/'),('AnkerGames  ↗','https://ankergames.net/games-list'),('FitGirl Repacks  ↗','https://fitgirl-repacks.site/'))):
            sources.grid_columnconfigure(column,weight=1)
            button=owner._button(sources,label,lambda address=url:webbrowser.open(address),width=130)
            button.grid(row=2,column=column,sticky='ew',padx=(12,6),pady=(0,8))
            self.source_buttons.append(button)
        ctk.CTkLabel(sources,text='External links · Large files can contain malicious code too.',text_color=MUTED,font=('Segoe UI',10)).grid(row=3,column=0,columnspan=3,sticky='w',padx=18,pady=(0,12))
        tools=ctk.CTkFrame(self.body,fg_color='transparent')
        tools.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(12,4))
        self.details=owner._button(tools,'Show log',self.toggle_details,width=160)
        self.details.pack(side='left')
        owner._button(tools,'Extract ZIP',owner.extract_dialog,width=140).pack(side='right')
        owner.download_log=ctk.CTkTextbox(self.body,height=140,fg_color='#0c1821',text_color=MUTED,font=('Consolas',10),corner_radius=12)
        owner.download_log.insert('end','\n'.join(owner.download_lines))
        owner.download_log.configure(state='disabled')
        self.update_transfer()

    def toggle_details(self):
        self.details_open=not self.details_open
        if self.details_open:
            self.owner.download_log.grid(row=3,column=0,columnspan=2,sticky='nsew',pady=(6,0))
            self.owner.download_log.see('end')
        else:
            self.owner.download_log.grid_remove()
        self.details.configure(text='Hide log' if self.details_open else 'Show log')

    def open_folder(self):
        folder=Path(self.owner.transfer.get('destination') or self.owner.root_path/'downloads')
        if folder.is_dir():
            os.startfile(str(folder))

    def update_transfer(self):
        data=self.owner.transfer
        stamp=(tuple(sorted(data.items())),self.owner.busy)
        if stamp==self.last:
            return
        self.last=stamp
        phase=data.get('phase','idle')
        titles={'idle':'READY TO DOWNLOAD','preparing':'CONNECTING','downloading':'DOWNLOADING',
                'stopping':'STOPPING…','paused':'PAUSED · READY TO RESUME','cancelled':'CANCELLED · PARTIAL FILES KEPT',
                'scanning':'TRANSFER COMPLETE · SCANNING','completed':'COMPLETE · SCANNED','error':'TRANSFER INTERRUPTED'}
        self.phase.configure(text=titles.get(phase,phase.upper()))
        name=Path(data.get('file','')).name or data.get('name') or 'No active transfer'
        self.name.configure(text=name[:76])
        ratio=data.get('ratio')
        self.percent.configure(text=f'{ratio*100:.1f} %' if ratio is not None else '—')
        if ratio is not None:
            start=self.shown_ratio
            def frame(t):
                self.shown_ratio=start+(ratio-start)*t
                self.bar.set(self.shown_ratio)
            self.motion.animate('progress',140 if getattr(self.owner,'reduced_motion',False) else 280,frame)
        else:
            self.motion.cancel('progress')
            self.shown_ratio=0
            self.bar.set(0)
        amount=f"{data.get('done','—')} / {data.get('total','size pending')}"
        if phase=='idle':
            amount='Check the link, then confirm the file to download.'
        elif phase in ('paused','cancelled'):
            amount+=' · Downloaded data kept on disk.'
        self.volume.configure(text=amount)
        for key,widget in self.metrics.items():
            value=data.get(key,'—')
            if key=='speed' and value!='—':
                value+='/s'
            widget.configure(text=value)
        active=phase in ('preparing','downloading')
        self.pause.configure(state='normal' if active else 'disabled')
        self.cancel.configure(state='normal' if phase in ('preparing','downloading','scanning','paused') else 'disabled')
        self.resume.configure(state='normal' if phase=='paused' and not self.owner.busy else 'disabled')
        self.inspect.configure(state='disabled' if self.owner.busy else 'normal')
        # File selection only stages the next source; it never starts a transfer.
        self.torrent.configure(state='normal')
