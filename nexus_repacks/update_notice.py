"""Visible, urgent update notice. All widget access happens on the Tk thread."""
import customtkinter as ctk


class UpdateNotice:
    def __init__(self, owner, manifest):
        self.owner = owner
        self.manifest = manifest
        self.overlay = ctk.CTkFrame(owner, fg_color='#070e16', corner_radius=0)
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.overlay.lift()
        self.window = ctk.CTkToplevel(owner, fg_color='#10212c')
        self.window.title('Update required')
        owner.update_idletasks()
        x = max(0, owner.winfo_rootx() + (owner.winfo_width() - 580) // 2)
        y = max(0, owner.winfo_rooty() + (owner.winfo_height() - 380) // 2)
        self.window.geometry(f'580x380+{x}+{y}')
        self.window.resizable(False, False)
        self.window.transient(owner)
        self.window.attributes('-topmost', True)
        self.window.protocol('WM_DELETE_WINDOW', self.show)
        self.window.bind('<Escape>', lambda event: 'break')
        ctk.CTkLabel(self.window, text='Update required', text_color='#adefff',
                     font=('Segoe UI', 27, 'bold')).pack(pady=(28, 6))
        self.version = ctk.CTkLabel(self.window, text='', text_color='#effbff', font=('Segoe UI', 14, 'bold'))
        self.version.pack(pady=(0, 10))
        ctk.CTkLabel(self.window, text='A newer version is available. The download starts automatically.',
                     text_color='#9bb7c5', wraplength=500, font=('Segoe UI', 12)).pack(padx=30)
        self.progress = ctk.CTkProgressBar(self.window, width=480, height=8, progress_color='#adefff', fg_color='#294754')
        self.progress.set(0)
        self.progress.pack(pady=(22, 8))
        self.status = ctk.CTkLabel(self.window, text='Downloading…', wraplength=500,
                                  text_color='#9bb7c5', font=('Segoe UI', 12))
        self.status.pack(padx=30)
        actions = ctk.CTkFrame(self.window, fg_color='transparent')
        actions.pack(pady=(20, 12))
        self.install = ctk.CTkButton(actions, text='Downloading…', width=260, height=44, state='disabled',
                                     fg_color='#adefff', text_color='#080f16', hover_color='#d7f8ff',
                                     command=owner.restart_for_update)
        self.install.pack(side='left', padx=6)
        ctk.CTkButton(actions, text='Quit', command=owner.close, width=100, height=44,
                      fg_color='#1a263b', hover_color='#294754').pack(side='left', padx=6)
        ctk.CTkLabel(self.window, text='Game files and library data are kept.', text_color='#9bb7c5',
                     font=('Segoe UI', 10)).pack()
        self.window.after(80, self.show)
        self.update('available', manifest)

    def show(self):
        if not self.window.winfo_exists():
            return
        self.owner.deiconify()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.window.grab_set()

    def update(self, stage, manifest, ratio=None, error=''):
        self.manifest = manifest
        self.version.configure(text='Nexus ' + self.owner.updater.current + ' → ' + manifest['version'])
        if stage == 'available':
            self.progress.set(0)
            self.status.configure(text='Downloading the signed update…')
            self.install.configure(text='Downloading…', state='disabled')
        elif stage == 'downloading':
            self.progress.set(ratio or 0)
            self.status.configure(text=f'Downloading… {(ratio or 0)*100:.0f}%')
        elif stage == 'ready':
            self.progress.set(1)
            self.status.configure(text='Verified and ready. Restart Nexus to use the new version.')
            self.install.configure(text='Update & restart', state='normal', command=self.owner.restart_for_update)
        elif stage == 'error':
            self.status.configure(text='Update failed. Check your connection, disk space or antivirus, then retry.')
            self.install.configure(text='Retry update', state='normal', command=self.owner.updater.check)

    def restarting(self, message):
        self.install.configure(state='disabled', text='Restarting…')
        self.status.configure(text=message)

    def destroy(self):
        self.window.grab_release()
        self.window.destroy()
        self.overlay.destroy()
