"""Recover direct LAN ICE candidates from the authenticated HTTP peer, without public STUN."""
import ipaddress
import hashlib


def with_lan_candidates(sdp,peer,proxied=False):
    try:address=ipaddress.ip_address(peer)
    except (ValueError,TypeError):return sdp,0
    if proxied or not address.is_private or address.is_loopback or address.is_link_local:
        return sdp,0
    lines=sdp.splitlines();result=[];added=0;seen=set()
    for line in lines:
        # Add before end-of-candidates, preserving the original privacy/mDNS candidate.
        if line.startswith('a=candidate:'):
            fields=line.split()
            if len(fields)>=8 and fields[2].lower()=='udp' and fields[4].lower().endswith('.local') and fields[7]=='host':
                direct=fields.copy();direct[0]='a=candidate:'+hashlib.sha256((fields[0]+str(address)).encode()).hexdigest()[:16];direct[4]=str(address)
                entry=' '.join(direct)
                if entry not in seen:result.append(entry);seen.add(entry);added+=1
        result.append(line)
    return '\r\n'.join(result)+'\r\n',added
