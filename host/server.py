import argparse
import asyncio
import ctypes
import json
import logging
import os
from pathlib import Path
import platform
import secrets
import sys
import subprocess
import threading
import time
from collections import deque

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCRtpSender, RTCConfiguration,RTCIceServer
import aiortc.rtcrtpsender as sender_module
from aiortc.codecs import CODECS
from aiortc.rtcrtpparameters import RTCRtpCodecParameters
import psutil

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.capture import DesktopTrack
from host.audio import LoopbackTrack
from host.encoder import DesktopEncoder, probe_nvenc
from host.remote_input import RemoteInput
from host.host_ui import HostUI
from host.configuration import PROFILES, stream_profile
from host.display import display_info
from host.code_store import CodeStore
from host.password_auth import PasswordAuth
from host.clipboard_sync import WindowsClipboard,validate_text
from host.lan_signaling import with_lan_candidates
from host.session_gate import SessionGate
from host.tunnel_stream import run_stream
from host.desktop_actions import DesktopActions
from host.public_tunnel import QuickTunnel
from host.link_mailer import MailSettings,LinkMailer

BASE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))


class State:
    def __init__(self,native_path=None,code_store=None):
        self.native_path=native_path or (BASE/'native'/'RemoteCoreCapture.dll' if getattr(sys,'frozen',False) else BASE/'build'/'RemoteCoreCapture.dll')
        self.password_auth=PasswordAuth()
        self.clipboard=WindowsClipboard()
        self.code_store=code_store
        self.token=code_store.load_or_create() if code_store is not None else secrets.token_urlsafe(18)
        self.nvenc=probe_nvenc()
        self.encoder='h264_nvenc' if self.nvenc['available'] else 'libx264'
        self.profile=PROFILES['1080p60'].copy()
        self.profile_name='1080p60'
        self.epoch=time.perf_counter()
        self.errors=deque(maxlen=15)
        self.active=False
        self.connecting=False
        self.control_enabled=True
        self.peer=''
        self.pc=None
        self.ws=None
        self.control_ws=None
        self.stream_tasks=[]
        self.session_id=''
        self.video=None
        self.audio=None
        self.loop=None
        self.gamepad_status='Non initialisé — pilote ViGEmBus facultatif'
        self.audio_status='Inactif'
        self.metrics={}
        self.reset_metrics()
        self.input=RemoteInput(self)
        self.process=psutil.Process()
        self.process.cpu_percent()
        self.started=time.monotonic()
        self.last_snapshot=(self.started,0,0,0)
        self.rate_history=deque(maxlen=30)
        self.resource_timestamp=0
        self.resources=(0,0)
        self.children={}
        self.gpu_utilization=None
        self.codec_profile='baseline'
        self.server_ready=False
        self.server_error=None
        self.bind='0.0.0.0'
        self.desktop_actions=None
        self.prepared_session=''
        self.ice_servers=[]
        self.setup_desktop=False
        self.desktop_setup_task=None
        self.public_tunnel=None
        self.public_url=''
        self.public_status='Désactivé'
        self.link_mailer=None
        self.mail_status='E-mail non configuré'

    async def session_connected(self):
        identity=self.session_id
        if not self.desktop_actions or not self.setup_desktop or not identity or self.prepared_session==identity:return
        self.prepared_session=identity
        task=self.desktop_setup_task=asyncio.create_task(asyncio.to_thread(self.desktop_actions.prepare))
        try:
            for message in await asyncio.shield(task):self.error(message)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise
        finally:
            if self.desktop_setup_task is task and task.done():self.desktop_setup_task=None

    @property
    def control_allowed(self):return self.active and self.control_enabled

    def regenerate_code(self):
        code=secrets.token_urlsafe(18)
        while code==self.token:code=secrets.token_urlsafe(18)
        if self.code_store is not None:self.code_store.replace(code)
        self.token=code
        self.request_disconnect()
        return code

    def reset_metrics(self):
        self.metrics=dict(frames=0,source_frames=0,source_skipped=0,pacing_missed=0,capture_ms=0,
                          encoded=0,encode_ms=0,encoded_bytes=0,audio_frames=0,audio_dropped=0)
        if hasattr(self,'rate_history'):self.rate_history.clear()

    def error(self,message):
        if not self.errors or self.errors[-1]['message']!=message:
            self.errors.append(dict(time=time.strftime('%H:%M:%S'),message=message))
            logging.warning(message)

    def release_input(self):
        if self.loop:self.loop.call_soon_threadsafe(self.input.release)

    def refresh_video(self):
        self.force_keyframe=True
        if self.pc:
            for sender in self.pc.getSenders():
                if sender.track and sender.track.kind=='video':sender._send_keyframe()

    def request_disconnect(self):
        # Immediately close the gate even if an event is already queued.
        self.active=False
        if self.loop:asyncio.run_coroutine_threadsafe(self.disconnect(),self.loop)

    def restart_public_tunnel(self):
        if not self.loop or not self.public_tunnel:return
        async def restart():
            await self.disconnect()
            await self.public_tunnel.restart()
        asyncio.run_coroutine_threadsafe(restart(),self.loop)

    def resend_link_email(self):
        if not self.loop or not self.link_mailer or not self.public_url:return
        def schedule():
            self.link_mailer.seen.discard(self.public_url);self.link_mailer.schedule(self.public_url)
        self.loop.call_soon_threadsafe(schedule)

    async def disconnect(self):
        self.active=False
        self.input.release()
        self.session_id=''
        self.setup_desktop=False
        pc,self.pc=self.pc,None
        ws,self.ws=self.ws,None
        control_ws,self.control_ws=self.control_ws,None
        tasks,self.stream_tasks=self.stream_tasks,[]
        video,self.video=self.video,None
        audio,self.audio=self.audio,None
        if video:video.stop()
        if audio:audio.stop()
        if control_ws and not control_ws.closed:await control_ws.close(code=4001,message=b'Session ended')
        current=asyncio.current_task()
        for task in tasks:
            if task is not current:task.cancel()
        if tasks:await asyncio.gather(*(task for task in tasks if task is not current),return_exceptions=True)
        if ws and not ws.closed:await ws.close(code=4001,message=b'Session replaced or ended')
        if pc:await pc.close()
        if video:
            await asyncio.to_thread(video.close_native)
        if self.desktop_setup_task:
            task=self.desktop_setup_task
            await asyncio.shield(task)
            if self.desktop_setup_task is task:self.desktop_setup_task=None
        if self.desktop_actions:
            for message in await asyncio.to_thread(self.desktop_actions.restore):self.error(message)
        self.peer=''
        self.audio_status='Inactif'

    def snapshot(self):
        now=time.monotonic()
        if not self.rate_history or now-self.rate_history[-1][0]>.2:
            self.rate_history.append((now,self.metrics['frames'],self.metrics['encoded'],self.metrics['encoded_bytes']))
        while len(self.rate_history)>2 and now-self.rate_history[1][0]>2:self.rate_history.popleft()
        t,frames,encoded,byte_count=self.rate_history[0]
        seconds=max(.01,now-t)
        result=dict(self.metrics)
        if now-self.resource_timestamp>.5:
            cpu=self.process.cpu_percent()
            memory=self.process.memory_info().rss
            active_children={}
            for child in self.process.children(recursive=True):
                try:
                    process=self.children.get(child.pid,child)
                    cpu+=process.cpu_percent();memory+=process.memory_info().rss
                    active_children[child.pid]=process
                except psutil.Error:pass
            self.children=active_children
            self.resources=(round(cpu/(psutil.cpu_count() or 1),1),round(memory/1e6,1))
            self.resource_timestamp=now
        result.update(fps=round((self.metrics['frames']-frames)/seconds,1),
                      encode_fps=round((self.metrics['encoded']-encoded)/seconds,1),
                      mbps=round((self.metrics['encoded_bytes']-byte_count)*8/seconds/1e6,2),
                      cpu_percent=self.resources[0],memory_mb=self.resources[1],
                      encoder=self.encoder,nvenc=self.nvenc,errors=list(self.errors),active=self.active,
                      session_exists=self.pc is not None or self.ws is not None,session_id=self.session_id,connection_state=self.pc.connectionState if self.pc else 'connected' if self.ws else 'closed',
                      control=self.control_allowed,audio=self.audio_status,gamepad=self.gamepad_status,
                      profile=self.profile_name,quality=self.profile.get('quality','performance'),
                      codec_profile=self.codec_profile,display=display_info(),uptime=round(now-self.started),
                      gpu_encode_utilization=self.gpu_utilization,
                      copy_path=('D3D11 NV12 GPU → RAM partagée → NVENC' if self.metrics.get('pixel_format')=='nv12' else 'DXGI BGRA → RAM → conversion YUV → NVENC') if self.encoder=='h264_nvenc' else 'DXGI → RAM → libx264',
                      windows=platform.platform(),mail_status=self.mail_status)
        self.last_snapshot=(now,self.metrics['frames'],self.metrics['encoded'],self.metrics['encoded_bytes'])
        return result


def create_app(state,ui):
    gate=SessionGate(state)
    # Advertise H.264 High as well as Baseline; the selected encoder profile follows SDP.
    # Level asymmetry lets receivers negotiate their own decoder level.
    base=next(c for c in CODECS['video'] if c.mimeType.lower()=='video/h264')
    for profile_id,payload in [('640c34',103),('640034',105),('4d0034',107)]:
        if not any(c.parameters.get('profile-level-id')==profile_id for c in CODECS['video']):
            CODECS['video'].extend([
                RTCRtpCodecParameters(mimeType='video/H264',clockRate=90000,payloadType=payload,
                    rtcpFeedback=base.rtcpFeedback.copy(),parameters={'level-asymmetry-allowed':'1','packetization-mode':'1','profile-level-id':profile_id}),
                RTCRtpCodecParameters(mimeType='video/rtx',clockRate=90000,payloadType=payload+1,parameters={'apt':payload})])
    original=sender_module.get_encoder
    def make_encoder(codec):
        if codec.mimeType.lower()=='video/h264':
            identifier=codec.parameters.get('profile-level-id','')
            profile='high' if identifier.startswith('64') else 'main' if identifier.startswith('4d') else 'baseline'
            return DesktopEncoder(state,profile)
        return original(codec)
    sender_module.get_encoder=make_encoder

    @web.middleware
    async def security(request,handler):
        # Proxies/LAN aliases may rewrite Host while keeping the browser's Origin.
        # APIs use explicit Bearer secrets, never ambient cookies. Authenticate first.
        # No CORS wildcard: the browser still calls APIs through its own origin.
        if request.path in ('/api/stream','/api/control') and request.headers.get('Upgrade','').lower()=='websocket':
            pass  # The first WebSocket message authenticates before any resources/session changes.
        elif request.path=='/api/unlock':
            pass  # Credentials are checked by the handler, including behind HTTPS proxies.
        elif request.path.startswith('/api/'):
            value=request.headers.get('Authorization','')
            if not secrets.compare_digest(value.encode('utf-8'),('Bearer '+state.token).encode('utf-8')):
                raise web.HTTPUnauthorized(text='Code de connexion incorrect')
            if not state.password_auth.valid(request.headers.get('X-Nexus-Access','')):
                raise web.HTTPUnauthorized(text='Mot de passe requis ou accès expiré')
        else:
            origin=request.headers.get('Origin')
            if origin and origin!=f'{request.scheme}://{request.host}':
                raise web.HTTPForbidden(text='Origine refusée')
        response=await handler(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    app=web.Application(middlewares=[security],client_max_size=128*1024)

    async def index(request):return web.FileResponse(BASE/'web'/'index.html')
    async def asset(request):
        name=request.match_info['name']
        if name not in ('app.js','controls.js','tools.js','keyboard.js','playback.js','clipboard.js','style.css','manifest.webmanifest'):raise web.HTTPNotFound()
        return web.FileResponse(BASE/'web'/name)
    async def brand_asset(request):
        name=request.match_info['name']
        if name not in ('nexus-emblem.png','nexus.ico'):raise web.HTTPNotFound()
        return web.FileResponse(BASE/'assets'/name)
    async def font_asset(request):
        name=request.match_info['name']
        if name not in ('SpaceGrotesk.ttf','OFL.txt'):raise web.HTTPNotFound()
        return web.FileResponse(BASE/'web'/'fonts'/name)
    async def unlock(request):
        if not state.password_auth.reserve_attempt():
            raise web.HTTPTooManyRequests(text='Trop de tentatives. Réessayez dans une minute.')
        data=await request.json()
        if not isinstance(data,dict):raise web.HTTPBadRequest(text='Requête invalide')
        code=data.get('code');password=data.get('password')
        code_ok=isinstance(code,str) and secrets.compare_digest(code.encode(),state.token.encode())
        password_ok=await asyncio.to_thread(state.password_auth.verify,password)
        if not code_ok or not password_ok:
            raise web.HTTPUnauthorized(text='Code ou mot de passe incorrect')
        return web.json_response({'access':state.password_auth.issue()})

    async def status(request):
        return web.json_response({**state.snapshot(),'ice_servers':state.ice_servers,'tunnel_required':bool(request.headers.get('Forwarded') or request.headers.get('X-Forwarded-For'))})
    async def profiles(request):return web.json_response({k:{**v,'verified':False} for k,v in PROFILES.items()})
    async def client_state(request):
        data=await request.json()
        if not isinstance(data,dict):raise web.HTTPBadRequest()
        allowed=('event','connection','ice','signaling','width','height','paused','ready','error','frames','time','transport')
        clean={key:str(data[key])[:80] for key in allowed if key in data}
        logging.info('Client peer=%s agent=%s status=%s',request.remote,request.headers.get('User-Agent','')[:160],json.dumps(clean,ensure_ascii=True))
        return web.json_response({'ok':True})

    async def offer(request):
        params=await request.json()
        if not isinstance(params,dict):raise web.HTTPBadRequest(text='Requête JSON invalide')
        name=params.get('profile','1080p60')
        if not isinstance(name,str) or name not in PROFILES:raise web.HTTPBadRequest(text='Profil invalide')
        try:profile=stream_profile(name,params.get('bitrate_mbps'),params.get('quality'))
        except (ValueError,TypeError,OverflowError) as exc:raise web.HTTPBadRequest(text=str(exc))
        safari=params.get('compatibility')=='safari' or any(v in request.headers.get('User-Agent','') for v in ('iPhone','iPad','iPod'))
        if safari:
            profile.update(width=min(profile['width'],1280),height=min(profile['height'],720),
                           fps=min(profile['fps'],30),bitrate=min(profile['bitrate'],8_000_000),h264_level=31)
        if params.get('type')!='offer' or not isinstance(params.get('sdp'),str):raise web.HTTPBadRequest(text='Offre SDP invalide')
        identity=gate.client_id(params.get('client_id'))
        if not await ui.approve(request.remote,name):raise web.HTTPForbidden(text='Connexion refusée : les connexions sont désactivées sur le PC hôte.')
        async with gate.admit(identity,request.headers.get('Authorization',''),request.headers.get('X-Nexus-Access','')):
            try:
                state.profile=profile;state.profile_name=name
                state.setup_desktop=params.get('prepare_desktop') is True
                state.reset_metrics();state.last_snapshot=(time.monotonic(),0,0,0)
                state.encoder='h264_nvenc' if state.nvenc['available'] else 'libx264'
                state.epoch=time.perf_counter()
                pc=state.pc=RTCPeerConnection(RTCConfiguration(iceServers=[RTCIceServer(**entry) for entry in state.ice_servers] if params.get('internet') is True else []))
                state.peer=request.remote
                disconnect_timer=None

                async def expire_disconnect():
                    await asyncio.sleep(12)
                    if state.pc is pc and pc.connectionState=='disconnected':
                        state.error('Réseau interrompu pendant 12 secondes : session fermée.')
                        await state.disconnect()

                @pc.on('connectionstatechange')
                async def changed():
                    nonlocal disconnect_timer
                    if state.pc is not pc:return
                    logging.info('Session peer=%s state=%s ice=%s',request.remote,pc.connectionState,pc.iceConnectionState)
                    state.active=pc.connectionState=='connected'
                    if state.active:await state.session_connected()
                    if pc.connectionState=='disconnected':
                        state.input.release()
                        if disconnect_timer is None or disconnect_timer.done():disconnect_timer=asyncio.create_task(expire_disconnect())
                    else:
                        if disconnect_timer:disconnect_timer.cancel();disconnect_timer=None
                    if pc.connectionState in ('failed','closed'):
                        await state.disconnect()

                @pc.on('datachannel')
                def channel_open(channel):
                    if channel.label!='commands':return
                    @channel.on('message')
                    def message(data):
                        if state.pc is not pc or not isinstance(data,str) or len(data)>4096:return
                        try:
                            event=json.loads(data)
                            if event.get('type')=='ping':
                                channel.send(json.dumps({'type':'pong','at':event.get('at'),'control':state.control_allowed}))
                            elif event.get('type')=='video-refresh':state.refresh_video()
                            else:state.input.event(event)
                        except (ValueError,TypeError,KeyError,OverflowError):pass
                    @channel.on('close')
                    def closed():
                        if state.pc is pc:state.input.release()

                # aiortc filters the offered codecs during setRemoteDescription, so set preferences first.
                transceiver=pc.addTransceiver('video',direction='sendonly')
                codecs=[c for c in RTCRtpSender.getCapabilities('video').codecs if c.mimeType.lower()=='video/h264']
                if safari:codecs=[c for c in codecs if c.parameters.get('profile-level-id')=='42e01f']
                else:codecs.sort(key=lambda c:0 if c.parameters.get('profile-level-id','').startswith('64') else 1 if c.parameters.get('profile-level-id','').startswith('4d') else 2)
                transceiver.setCodecPreferences(codecs)
                remote_sdp,lan_count=with_lan_candidates(params['sdp'],request.remote,
                    proxied=bool(request.headers.get('Forwarded') or request.headers.get('X-Forwarded-For')))
                logging.info('Offer peer=%s safari=%s direct_lan_candidates=%d',request.remote,safari,lan_count)
                await pc.setRemoteDescription(RTCSessionDescription(sdp=remote_sdp,type='offer'))
                state.video=DesktopTrack(state)
                pc.addTrack(state.video)
                if params.get('audio',True):
                    state.audio=LoopbackTrack(state)
                    pc.addTrack(state.audio)
                answer=await pc.createAnswer()
                await pc.setLocalDescription(answer)
                if state.pc is not pc or not secrets.compare_digest(request.headers.get('Authorization','').encode(),('Bearer '+state.token).encode()):
                    await pc.close()
                    raise web.HTTPUnauthorized(text='Le code a changé. Utilisez le nouveau code du PC hôte.')
                return web.json_response({'sdp':pc.localDescription.sdp,'type':pc.localDescription.type,'session_id':state.session_id})
            except web.HTTPException:raise
            except Exception as exc:
                state.error(str(exc));await state.disconnect()
                raise web.HTTPBadRequest(text='Initialisation impossible : '+str(exc))

    async def disconnect(request):
        if not secrets.compare_digest(request.headers.get('X-Nexus-Session',''),state.session_id) or not state.session_id:
            return web.json_response({'ok':True,'replaced':True})
        await state.disconnect()
        return web.json_response({'ok':True})

    async def tunnel(request):
        ws=web.WebSocketResponse(heartbeat=15,max_msg_size=8192,compress=False)
        await ws.prepare(request)
        try:
            params=await asyncio.wait_for(ws.receive_json(),10)
            if not isinstance(params,dict):raise ValueError('Requête invalide')
            token=params.pop('token','')
            if not isinstance(token,str) or not gate.authenticated('Bearer '+token,params.get('access','')):
                await ws.send_json({'type':'error','message':'Code de connexion incorrect'})
                await ws.close(code=4003);return ws
            identity=gate.client_id(params.get('client_id'))
            name=params.get('profile','1080p60')
            if not isinstance(name,str) or name not in PROFILES:raise ValueError('Profil invalide')
            profile=stream_profile(name,params.get('bitrate_mbps'),params.get('quality'))
            mobile=params.get('compatibility')=='safari' or any(v in request.headers.get('User-Agent','') for v in ('iPhone','iPad','iPod'))
            # TCP needs bounded bandwidth and frame rates to avoid a growing latency queue.
            profile.update(width=min(profile['width'],1280 if mobile else 1920),
                           height=min(profile['height'],720 if mobile else 1080),
                           fps=min(profile['fps'],30 if mobile else 60),bitrate=min(profile['bitrate'],6_000_000 if mobile else 20_000_000),
                           codec_profile='baseline' if mobile else 'high')
            if not await ui.approve(request.remote,name):raise ValueError('Connexions désactivées sur le PC hôte.')
            async with gate.admit(identity,'Bearer '+token,params.get('access','')):
                state.profile=profile;state.profile_name=name;state.reset_metrics()
                state.setup_desktop=params.get('prepare_desktop') is True
                state.epoch=time.perf_counter();state.peer=request.remote
                state.encoder='h264_nvenc' if state.nvenc['available'] else 'libx264'
                state.ws=ws
                state.stream_tasks=[asyncio.create_task(run_stream(state,ws,bool(params.get('audio',True))))]
            async for msg in ws:
                if state.ws is not ws:break
                if msg.type!=web.WSMsgType.TEXT:continue
                try:
                    event=json.loads(msg.data)
                    if not isinstance(event,dict):continue
                    if event.get('type')=='ping':
                        await ws.send_json({'type':'pong','at':event.get('at'),'control':state.control_allowed})
                    elif event.get('type')=='video-refresh':state.refresh_video()
                    else:state.input.event(event)
                except (ValueError,TypeError,KeyError,OverflowError):pass
        except (ValueError,TypeError,asyncio.TimeoutError,web.HTTPException) as exc:
            if not ws.closed:
                await ws.send_json({'type':'error','message':str(exc) or 'Authentification expirée'})
                await ws.close(code=4003)
        finally:
            if state.ws is ws:await state.disconnect()
        return ws

    async def maintenance():
        count=0
        while True:
            await asyncio.sleep(.5)
            if time.monotonic()-state.input.last>2:state.input.release()
            count+=1
            if count%4==0:
                def utilization():
                    try:
                        r=subprocess.run(['nvidia-smi','--query-gpu=utilization.encoder','--format=csv,noheader,nounits'],
                                         capture_output=True,text=True,timeout=2,creationflags=subprocess.CREATE_NO_WINDOW)
                        return int(r.stdout.strip().splitlines()[0]) if r.returncode==0 else None
                    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):return None
                state.gpu_utilization=await asyncio.to_thread(utilization)

    async def desktop_action(request):
        if not state.control_allowed or not state.session_id or request.headers.get('X-Nexus-Session','')!=state.session_id:
            raise web.HTTPForbidden(text='Session de contrôle inactive ou remplacée')
        params=await request.json()
        action=params.get('action') if isinstance(params,dict) else None
        if action not in ('cmd','classroom'):raise web.HTTPBadRequest(text='Action non autorisée')
        if not state.desktop_actions:raise web.HTTPServiceUnavailable(text='Actions Windows indisponibles')
        try:await asyncio.to_thread(state.desktop_actions.launch,action)
        except (OSError,RuntimeError) as exc:raise web.HTTPBadRequest(text=str(exc))
        return web.json_response({'ok':True})

    async def clipboard(request):
        if not state.control_allowed or not state.session_id or request.headers.get('X-Nexus-Session','')!=state.session_id:
            raise web.HTTPForbidden(text='Session de contrôle inactive ou remplacée')
        try:
            if request.method=='GET':return web.json_response(state.clipboard.snapshot(request.query.get('since')))
            data=await request.json()
            if not isinstance(data,dict):raise ValueError('Requête invalide')
            sequence=state.clipboard.set_text(validate_text(data.get('text')))
            if data.get('paste') is True:
                held=bool(state.input.keys.intersection({'ControlLeft','ControlRight'}))
                if not held:state.input.key('ControlLeft',True)
                state.input.key('KeyV',True,logical=True);state.input.key('KeyV',False,logical=True)
                if not held:state.input.key('ControlLeft',False)
            return web.json_response({'sequence':sequence})
        except (ValueError,UnicodeError) as exc:raise web.HTTPBadRequest(text=str(exc))
        except OSError:raise web.HTTPServiceUnavailable(text='Presse-papiers occupé. Réessayez.')

    async def control_socket(request):
        ws=web.WebSocketResponse(heartbeat=10,max_msg_size=8192,compress=False)
        await ws.prepare(request)
        try:
            auth=await asyncio.wait_for(ws.receive_json(),10)
            if not isinstance(auth,dict):raise ValueError('Authentification invalide')
            token=auth.get('token');identity=auth.get('session_id')
            if not isinstance(token,str) or not gate.authenticated('Bearer '+token,auth.get('access','')):raise ValueError('Code incorrect')
            if not isinstance(identity,str) or not state.session_id or not secrets.compare_digest(identity,state.session_id):
                raise ValueError('Session remplacée ou terminée')
            if state.ws is None:raise ValueError('Aucun flux tunnel actif')
            previous=state.control_ws;state.control_ws=ws
            if previous and not previous.closed:await previous.close(code=4001)
            await ws.send_json({'type':'control-ready','session_id':identity})
            async for msg in ws:
                if state.control_ws is not ws or state.session_id!=identity:break
                if msg.type!=web.WSMsgType.TEXT:continue
                try:
                    event=json.loads(msg.data)
                    if not isinstance(event,dict):continue
                    if event.get('type')=='ping':await ws.send_json({'type':'pong','at':event.get('at'),'control':state.control_allowed})
                    elif event.get('type')=='video-refresh':state.refresh_video()
                    else:state.input.event(event)
                except (ValueError,TypeError,KeyError,OverflowError):pass
        except (ValueError,TypeError,asyncio.TimeoutError) as exc:
            if not ws.closed:
                await ws.send_json({'type':'error','message':str(exc)})
                await ws.close(code=4003)
        finally:
            if state.control_ws is ws:state.control_ws=None;state.input.release()
        return ws

    async def startup(app):
        state.loop=asyncio.get_running_loop()
        app['watchdog']=asyncio.create_task(maintenance())
    async def cleanup(app):
        app['watchdog'].cancel()
        await state.disconnect()
        if getattr(state,'clipboard',None):state.clipboard.close()
    app.on_startup.append(startup);app.on_cleanup.append(cleanup)
    app.router.add_get('/',index)
    app.router.add_get('/{name:app.js|controls.js|tools.js|keyboard.js|playback.js|clipboard.js|style.css|manifest.webmanifest}',asset)
    app.router.add_get('/assets/{name}',brand_asset)
    app.router.add_get('/fonts/{name}',font_asset)
    app.router.add_post('/api/unlock',unlock)
    app.router.add_get('/api/status',status)
    app.router.add_get('/api/profiles',profiles)
    app.router.add_post('/api/client-state',client_state)
    app.router.add_post('/api/offer',offer)
    app.router.add_post('/api/disconnect',disconnect)
    app.router.add_get('/api/stream',tunnel)
    app.router.add_get('/api/control',control_socket)
    app.router.add_get('/api/clipboard',clipboard)
    app.router.add_post('/api/clipboard',clipboard)
    app.router.add_post('/api/action',desktop_action)
    return app


async def serve(state,ui,bind,port,stop):
    runner=web.AppRunner(create_app(state,ui),access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner,bind,port).start()
        state.server_ready=True
        if state.public_tunnel:await state.public_tunnel.start()
        logging.info('Interface prête : http://localhost:%d',port)
        while not stop.is_set():await asyncio.sleep(.2)
    finally:
        state.server_ready=False
        if state.public_tunnel:await state.public_tunnel.close()
        if state.link_mailer:await state.link_mailer.close()
        await runner.cleanup()


def main():
    parser=argparse.ArgumentParser(description='Nexus View — partage de bureau par code privé')
    parser.add_argument('--bind',default='0.0.0.0',help='LAN par défaut ; 127.0.0.1 pour le mode local uniquement')
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--tray',action='store_true',help='Démarrer dans la zone de notification')
    parser.add_argument('--no-tunnel',action='store_true',help='Désactiver le lien Internet Cloudflare')
    args=parser.parse_args()
    ctypes.windll.user32.SetProcessDPIAware()
    log_dir=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'NexusView'
    log_dir.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,filename=log_dir/'host.log',encoding='utf-8',format='%(asctime)s %(levelname)s %(message)s')
    try:
        state=State(code_store=CodeStore())
        state.password_auth=PasswordAuth(log_dir/'remote-password.bin')
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(None,'Impossible de charger le code enregistré. Aucun nouveau code n’a été généré.\n\n'+str(exc),'Nexus View',0x10)
        return
    state.desktop_actions=DesktopActions(state.native_path)
    try:
        paths=[]
        if os.environ.get('NEXUS_ENV_FILE'):paths.append(Path(os.environ['NEXUS_ENV_FILE']))
        if getattr(sys,'frozen',False):paths.append(Path(sys.executable).parent/'.env')
        paths.extend([Path.cwd()/'.env',Path(__file__).resolve().parent.parent/'.env'])
        cache=log_dir/'mail-settings.bin';settings=MailSettings.load(paths,cache)
        if settings:
            state.link_mailer=LinkMailer(state,settings,cache)
            state.mail_status='E-mail configuré · envoi au prochain lien' if settings.recipients else 'Choisissez les destinataires dans Connexion pour activer l’envoi.'
    except (OSError,ValueError):state.mail_status='Configuration e-mail invalide. Vérifiez .env.'
    if not args.no_tunnel:
        binary=BASE/'tools'/'cloudflared.exe' if getattr(sys,'frozen',False) else BASE/'third_party'/'cloudflared'/'cloudflared.exe'
        state.public_tunnel=QuickTunnel(state,binary,args.port,log_dir)
    state.ice_servers=json.loads(os.environ.get('NEXUS_ICE_SERVERS','[{"urls":"stun:stun.cloudflare.com:3478"}]'))
    state.bind=args.bind;ui=HostUI(state,args.port,start_hidden=args.tray);stop=threading.Event()
    ui.stop_callback=stop.set
    def worker():
        try:asyncio.run(serve(state,ui,args.bind,args.port,stop))
        except Exception as exc:
            state.error('Serveur : '+str(exc))
            state.server_error=str(exc)
    thread=threading.Thread(target=worker,daemon=True);thread.start()
    ui.run();stop.set();thread.join(timeout=10)


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
