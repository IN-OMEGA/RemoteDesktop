"""Application-owned Cloudflare Quick Tunnel. Each restart creates a fresh public URL."""
import asyncio
import os
from pathlib import Path
import re
import subprocess


class QuickTunnel:
    def __init__(self,state,binary,port,data_dir,process_factory=None):
        self.state,self.binary,self.port=state,Path(binary),port
        self.data_dir=Path(data_dir)
        self.factory=process_factory or asyncio.create_subprocess_exec
        self.task=None;self.process=None;self.stopping=False
        self.last_error=''
        self.restart_event=asyncio.Event()

    def publish(self,url,status):
        changed=url!=self.state.public_url
        self.state.public_url=url;self.state.public_status=status
        path=self.data_dir/'public-url.txt'
        if url:path.write_text(url+'\n',encoding='utf-8')
        elif path.exists():path.unlink()
        if url and changed and getattr(self.state,'link_mailer',None):self.state.link_mailer.schedule(url)

    async def start(self):
        if self.task and not self.task.done():return
        self.stopping=False;self.data_dir.mkdir(parents=True,exist_ok=True)
        # Isolate Quick Tunnel from any unrelated named-tunnel credentials/configuration.
        (self.data_dir/'quick-tunnel.yml').write_text('{}\n',encoding='utf-8')
        self.task=asyncio.create_task(self.run())

    async def stop_process(self):
        process,self.process=self.process,None
        if process and process.returncode is None:
            try:process.terminate()
            except ProcessLookupError:return
            try:await asyncio.wait_for(process.wait(),5)
            except asyncio.TimeoutError:process.kill();await process.wait()

    async def read_output(self,process):
        while True:
            line=await process.stdout.readline()
            if not line:break
            text=line.decode('utf-8',errors='replace')
            if any(word in text.lower() for word in ('error','failed','incorrect usage')):self.last_error=text.strip()[:350]
            match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',text)
            if match and self.process is process:
                self.publish(match.group(0),'Lien Internet actif · Cloudflare Try')

    async def run(self):
        try:
            while not self.stopping:
                self.restart_event.clear();self.publish('','Création du lien Cloudflare…')
                reader=exited=restarted=None
                try:
                    if not self.binary.is_file():raise FileNotFoundError('cloudflared est absent du dossier Nexus View')
                    environment={k:v for k,v in os.environ.items() if not k.startswith('TUNNEL_')}
                    self.process=process=await self.factory(str(self.binary),'tunnel',
                        '--config',str(self.data_dir/'quick-tunnel.yml'),'--url',f'http://127.0.0.1:{self.port}',
                        '--protocol','http2','--no-autoupdate',stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=environment)
                    reader=asyncio.create_task(self.read_output(process))
                    exited=asyncio.create_task(process.wait());restarted=asyncio.create_task(self.restart_event.wait())
                    await asyncio.wait((exited,restarted),return_when=asyncio.FIRST_COMPLETED)
                    if not self.restart_event.is_set():self.publish('','Tunnel interrompu · '+(self.last_error or 'nouvelle tentative…'))
                except (OSError,RuntimeError) as exc:self.publish('','Cloudflare indisponible : '+str(exc))
                finally:
                    await self.stop_process()
                    for task in (reader,exited,restarted):
                        if task and not task.done():task.cancel()
                    await asyncio.gather(*(t for t in (reader,exited,restarted) if t),return_exceptions=True)
                if not self.stopping and not self.restart_event.is_set():
                    try:await asyncio.wait_for(self.restart_event.wait(),10)
                    except asyncio.TimeoutError:pass
        finally:
            await self.stop_process();self.publish('','Tunnel arrêté')

    async def restart(self):
        self.publish('','Renouvellement du lien Cloudflare…')
        self.restart_event.set()

    async def close(self):
        self.stopping=True
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
