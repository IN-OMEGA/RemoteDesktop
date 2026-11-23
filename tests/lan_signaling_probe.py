from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.lan_signaling import with_lan_candidates
from aiortc.sdp import candidate_from_sdp

sdp='v=0\r\na=candidate:abc 1 udp 2113937151 iphone.local 55555 typ host\r\na=end-of-candidates\r\n'
result,count=with_lan_candidates(sdp,'192.168.12.50')
assert count==1 and sdp.splitlines()[1] in result
line=next(line for line in result.splitlines() if line.startswith('a=candidate:') and '192.168.12.50' in line)
candidate=candidate_from_sdp(line[len('a=candidate:'):])
assert candidate.ip=='192.168.12.50' and candidate.port==55555 and candidate.type=='host'
assert result.index(line)<result.index('a=end-of-candidates')
for peer,proxied in [('127.0.0.1',False),('169.254.1.1',False),('8.8.8.8',False),('192.168.12.50',True)]:
    assert with_lan_candidates(sdp,peer,proxied)==(sdp,0)
print('PASS: valid direct LAN candidate added; mDNS preserved; proxy/public/loopback excluded.')
