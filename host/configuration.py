"""Validated stream settings. Resolution envelopes never upscale the desktop."""
PROFILES={
 'premium':dict(width=3840,height=2160,fps=120,bitrate=60_000_000,quality='premium'),
 '720p30':dict(width=1280,height=720,fps=30,bitrate=5_000_000,quality='performance'),
 '1080p60':dict(width=1920,height=1080,fps=60,bitrate=25_000_000,quality='premium'),
 '1080p120':dict(width=1920,height=1080,fps=120,bitrate=40_000_000,quality='balanced'),
 '1440p60':dict(width=2560,height=1440,fps=60,bitrate=40_000_000,quality='premium'),
 '4k60':dict(width=3840,height=2160,fps=60,bitrate=60_000_000,quality='premium'),
 '4k120':dict(width=3840,height=2160,fps=120,bitrate=80_000_000,quality='balanced'),
}

def stream_profile(name,bitrate_mbps=None,quality=None):
    profile=PROFILES[name].copy()
    if bitrate_mbps not in (None,''):
        if isinstance(bitrate_mbps,bool):raise ValueError('Débit invalide')
        rate=float(bitrate_mbps)
        if not 1<=rate<=100:raise ValueError('Le débit doit être compris entre 1 et 100 Mb/s.')
        profile['bitrate']=int(rate*1_000_000)
    if quality is not None:
        if quality not in ('performance','balanced','premium'):raise ValueError('Qualité invalide')
        profile['quality']=quality
    return profile
