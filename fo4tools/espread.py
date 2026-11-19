#!/usr/bin/env python3
"""Minimal read-only FO4 plugin reader: header/masters, top-level record counts, record walk."""
import struct, zlib, sys, collections
class Rec:
    __slots__=('type','flags','fid','data','off','size','group')
    @property
    def edid(self):
        """Editor ID as str, or None (parses subrecords each call; cache if hot)."""
        for t,d in subrecords(self.data):
            if t=='EDID':
                return d.split(b'\0')[0].decode('latin1')
        return None
    def subrecords(self):
        return subrecords(self.data)
def subrecords(data):
    i=0; out=[]; xxxx=None
    while i+6<=len(data):
        t=data[i:i+4].decode('latin1'); sz=struct.unpack_from('<H',data,i+4)[0]; i+=6
        if t=='XXXX': xxxx=struct.unpack_from('<I',data,i)[0]; i+=4; continue
        if xxxx is not None: sz=xxxx; xxxx=None
        out.append((t,data[i:i+sz])); i+=sz
    return out
def walk(buf,start=0,end=None,group=None):
    end=end or len(buf); i=start
    while i+24<=end:
        t=buf[i:i+4].decode('latin1'); size=struct.unpack_from('<I',buf,i+4)[0]
        if t=='GRUP':
            label=buf[i+8:i+12]; gtype=struct.unpack_from('<I',buf,i+12)[0]
            gl=label.decode('latin1') if gtype==0 else 'g%d'%gtype
            yield from walk(buf,i+24,i+size,gl if gtype==0 else group); i+=size
        else:
            flags,fid=struct.unpack_from('<II',buf,i+8); r=Rec(); r.type=t; r.flags=flags; r.fid=fid; r.off=i; r.size=size; r.group=group
            d=buf[i+24:i+24+size]
            if flags&0x00040000:
                try: d=zlib.decompress(d[4:])
                except Exception: d=b''
            r.data=d; yield r; i+=24+size
def load(path):
    buf=open(path,'rb').read(); recs=list(walk(buf)); return buf,recs
if __name__=='__main__':
    buf,recs=load(sys.argv[1])
    hdr=recs[0]; print("header:",hdr.type,"flags %08X"%hdr.flags)
    for t,d in subrecords(hdr.data):
        if t=='MAST': print("  master:",d.rstrip(b'\0').decode())
        elif t=='HEDR': print("  HEDR version %.2f numRecords %d nextID %08X"%(struct.unpack_from('<fII',d)))
        elif t in ('CNAM','SNAM'): print("  ",t,d.rstrip(b'\0').decode('latin1')[:100])
    c=collections.Counter(r.type for r in recs[1:]); print("records:",len(recs)-1,dict(c))
