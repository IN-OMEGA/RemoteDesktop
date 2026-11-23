"""SMTP content, DPAPI settings and notification deduplication without sending real email."""
import asyncio
from pathlib import Path
import sys
import tempfile
import json
import smtplib
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.link_mailer import MailSettings,LinkMailer,addresses
from host.code_store import crypt

async def main():
    with tempfile.TemporaryDirectory(prefix='nexus-mail-') as directory:
        path=Path(directory);env=path/'.env';cache=path/'mail.bin'
        env.write_text('mailto_email=test-sender@gmail.com\nmailto_key="abcd efgh ijkl mnop"\n')
        settings=MailSettings.load([env],cache)
        assert settings.recipients==[]
        assert b'abcdefghijklmnop' not in cache.read_bytes() and b'test-sender@gmail.com' not in cache.read_bytes()
        assert MailSettings.load([],cache).password==settings.password
        # Legacy sender-as-recipient settings are never interpreted as an explicit new list.
        old={'username':settings.username,'password':settings.password,'recipient':settings.username}
        cache.write_bytes(crypt(json.dumps(old).encode()))
        assert MailSettings.load([env],cache).recipients==[]
        assert addresses('One@example.com; two@example.com\nONE@example.com,,')==['One@example.com','two@example.com']
        state=SimpleNamespace(public_url='https://test-live-link.trycloudflare.com',token='a'*24,mail_status='')
        mailer=LinkMailer(state,settings,cache)
        mailer.schedule(state.public_url);assert not mailer.tasks
        mailer.set_recipients('one@example.com\ntwo@example.com,ONE@example.com')
        settings=mailer.settings
        assert settings.recipients==['one@example.com','two@example.com']
        try:mailer.set_recipients('one@example.com\ninvalid-address')
        except ValueError:pass
        else:raise AssertionError('Invalid address accepted')
        assert mailer.settings.recipients==settings.recipients
        messages=[]
        class SMTP:
            def __init__(self,*args,**kwargs):assert kwargs['context'].check_hostname
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def login(self,user,key):assert user==settings.username and key==settings.password
            def send_message(self,msg):messages.append(msg)
        url='https://test-live-link.trycloudflare.com';code='a'*24
        with patch('host.link_mailer.smtplib.SMTP_SSL',SMTP):settings.send(url,code)
        assert len(messages)==2
        assert [str(msg['To']) for msg in messages]==settings.recipients
        assert 'two@example.com' not in messages[0].as_string()
        msg=messages[0]
        content=msg.get_content();assert url in content and code in content and settings.password not in content
        class PartialSMTP(SMTP):
            def send_message(self,msg):
                if str(msg['To'])=='two@example.com':raise smtplib.SMTPRecipientsRefused({'two@example.com':(550,b'refused')})
        with patch('host.link_mailer.smtplib.SMTP_SSL',PartialSMTP):assert settings.send(url,code)=={'sent':1,'failed':1}
        sent=[]
        def send(url,code):sent.append((url,code));return {'sent':2,'failed':0}
        settings.send=send
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch('host.link_mailer.urllib.request.urlopen',lambda *a,**k:Response()):
            mailer.schedule(url);mailer.schedule(url)
            await asyncio.gather(*list(mailer.tasks));assert sent==[(url,code)]
            stale='https://old-link.trycloudflare.com';mailer.schedule(stale)
            await asyncio.gather(*list(mailer.tasks));assert len(sent)==1
        assert MailSettings.load([env],cache).recipients==['one@example.com','two@example.com']
        assert settings.password not in state.mail_status
        mailer.set_recipients('');assert MailSettings.load([env],cache).recipients==[]
        mailer.schedule('https://another-link.trycloudflare.com');assert not mailer.tasks
        await mailer.close()
    print('PASS: explicit multiple recipients, no guessed destination, legacy migration, separate private messages, validation/deduplication, saved list and empty-list disable, verified TLS.')

if __name__=='__main__':asyncio.run(main())
