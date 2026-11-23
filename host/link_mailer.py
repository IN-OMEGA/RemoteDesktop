"""Private SMTP settings and link notifications. Never sends Windows credentials."""
import asyncio
from dataclasses import dataclass,asdict,field,replace
from email.message import EmailMessage
from email.utils import formatdate,make_msgid
import json
import os
from pathlib import Path
import re
import smtplib
import socket
import ssl
import tempfile
import urllib.request
from host.code_store import crypt


def address(value):
    value=value.strip()
    if not re.fullmatch(r'[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+',value):raise ValueError('Adresse e-mail invalide')
    return value


def addresses(value):
    if isinstance(value,str):value=re.split(r'[,;\n\r]+',value)
    if not isinstance(value,(list,tuple)):raise ValueError('Liste d’adresses invalide')
    result=[];seen=set()
    for item in value:
        if not isinstance(item,str):raise ValueError('Adresse e-mail invalide')
        if not item.strip():continue
        item=address(item)
        if item.casefold() not in seen:result.append(item);seen.add(item.casefold())
    return result


@dataclass(repr=False)
class MailSettings:
    username:str
    password:str
    recipients:list[str]=field(default_factory=list)
    host:str='smtp.gmail.com'
    port:int=465

    @classmethod
    def load(cls,paths,cache):
        saved=None
        if cache.exists():
            try:
                values=json.loads(crypt(cache.read_bytes(),unprotect=True).decode('utf-8'))
                # Previous versions guessed a recipient from the sending account. Require
                # an explicit new list rather than silently retaining that old destination.
                values.pop('recipient',None)
                values['recipients']=addresses(values.get('recipients',[]))
                saved=cls(**values)
            except (OSError,ValueError,TypeError):pass
        for path in paths:
            if not path.is_file():continue
            values={}
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                match=re.match(r'^\s*(?:export\s+)?([\w]+)\s*=\s*(.*?)\s*$',line)
                if match:
                    value=match[2]
                    if value[:1] in ('"',"'") and value[-1:]==value[:1]:value=value[1:-1]
                    else:value=re.split(r'\s+#',value,maxsplit=1)[0].strip()
                    values[match[1].lower()]=value
            username=values.get('mailto_email','');password=values.get('mailto_key','')
            if not username or not password:continue
            username=address(username)
            recipients=list(saved.recipients) if saved and saved.username==username else []
            settings=cls(username,password.replace(' ',''),recipients,
                         values.get('smtp_host','smtp.gmail.com'),int(values.get('smtp_port','465')))
            settings.save(cache);return settings
        return saved

    def save(self,cache):
        cache.parent.mkdir(parents=True,exist_ok=True)
        encrypted=crypt(json.dumps(asdict(self)).encode('utf-8'))
        with tempfile.NamedTemporaryFile(dir=cache.parent,delete=False) as file:
            temporary=Path(file.name);file.write(encrypted)
        try:os.replace(temporary,cache)
        finally:temporary.unlink(missing_ok=True)

    def message(self,url,code,recipient):
        if not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',url):raise ValueError('Lien Cloudflare invalide')
        if not re.fullmatch(r'[A-Za-z0-9_-]{24}',code):raise ValueError('Code Nexus invalide')
        msg=EmailMessage();msg['From']=self.username;msg['To']=address(recipient)
        msg['Subject']='Nexus View — votre nouveau lien de connexion'
        msg['Date']=formatdate(localtime=True);msg['Message-ID']=make_msgid()
        msg.set_content(f'Votre lien Nexus View est prêt.\n\nPC : {socket.gethostname()}\nLien : {url}\nCode de connexion Nexus : {code}\n\nCe code est celui de Nexus View, pas le mot de passe de votre compte Windows.\nLe lien précédent cesse de fonctionner après son remplacement.\nGardez ce message privé : le lien et le code permettent de contrôler ce PC.\n')
        return msg

    def send(self,url,code):
        recipients=tuple(self.recipients)
        if not recipients:return {'sent':0,'failed':0}
        result={'sent':0,'failed':0}
        def deliver(smtp):
            smtp.login(self.username,self.password)
            for recipient in recipients:
                try:
                    smtp.send_message(self.message(url,code,recipient));result['sent']+=1
                except (smtplib.SMTPException,OSError):result['failed']+=1
        context=ssl.create_default_context()
        if self.port==465:
            with smtplib.SMTP_SSL(self.host,self.port,timeout=12,context=context) as smtp:
                deliver(smtp)
        else:
            with smtplib.SMTP(self.host,self.port,timeout=12) as smtp:
                smtp.ehlo();smtp.starttls(context=context);smtp.ehlo()
                deliver(smtp)
        return result


class LinkMailer:
    def __init__(self,state,settings,cache):
        self.state,self.settings,self.cache=state,settings,cache
        self.tasks=set();self.seen=set()

    def set_recipients(self,value):
        settings=replace(self.settings,recipients=addresses(value))
        settings.save(self.cache);self.settings=settings

    def schedule(self,url):
        if not self.settings.recipients:
            self.state.mail_status='Ajoutez les destinataires dans Connexion pour activer l’envoi.';return
        if url in self.seen:return
        self.seen.add(url)
        task=asyncio.create_task(self.notify(url));self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def notify(self,url):
        self.state.mail_status='Lien créé · vérification avant envoi…'
        for attempt in range(10):
            if self.state.public_url!=url:return
            def ready():
                with urllib.request.urlopen(url,timeout=5) as response:return response.status==200
            try:
                if await asyncio.to_thread(ready):break
            except OSError:pass
            await asyncio.sleep(min(5,attempt+1))
        else:
            self.state.mail_status='Envoi suspendu : le lien public ne répond pas encore.'
            self.seen.discard(url);return
        if self.state.public_url!=url or not self.settings.recipients:return
        self.state.mail_status='Envoi de l’e-mail en cours…'
        try:
            result=await asyncio.to_thread(self.settings.send,url,self.state.token)
            if self.state.public_url==url:
                if result['failed']:self.state.mail_status=f"Envoi partiel : {result['sent']} réussi(s), {result['failed']} refusé(s)."
                else:self.state.mail_status=f"E-mail envoyé à {result['sent']} destinataire(s) · lien et code Nexus"
        except smtplib.SMTPAuthenticationError:
            self.state.mail_status='Gmail a refusé l’identification. Vérifiez la clé d’application dans .env.'
        except (smtplib.SMTPException,OSError,ValueError):
            self.state.mail_status='Échec de l’envoi de l’e-mail. Vérifiez la configuration et le réseau.'

    async def close(self):
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
