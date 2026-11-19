"""Reader for the two-section behaviour/clip info file (behaviorclipinformationandsubgraphanimationoffsetssinglefile.txt):
 '<n1>\\n' + n1 blocks + '<n2>\\n' + n2 sections.  block/section := '<key>\\nV4\\n' u8len+path\\0 u32 nrec nrec*record ;
 record := u8len+name\\0 u8len+name2\\0 f32 + 10 bytes + u32 nev + nev*( u8len+name\\0 f32 u8 )   (decoded from the bytes; verified by tiling)."""
import struct, re
def read_str(d,p): n=d[p]; return d[p+1:p+n].decode("latin1"),p+1+n
def parse_block(d,p):
    m=re.compile(rb'(\d+)\nV4\n').match(d,p); key=int(m.group(1)); p=m.end(); path,p=read_str(d,p); nrec=struct.unpack_from('<I',d,p)[0]; p+=4
    for _ in range(nrec):
        _,p=read_str(d,p); _,p=read_str(d,p); p+=14; nev=struct.unpack_from('<I',d,p)[0]; p+=4
        for _ in range(nev): _,p=read_str(d,p); p+=5
    return key,path,nrec,p
def parse(d):
    nl=d.index(b'\n'); n1=int(d[:nl]); p=nl+1; blocks=[]
    for _ in range(n1):
        s=p; key,path,nrec,p=parse_block(d,p); blocks.append((key,path,nrec,s,p))
    nl2=d.index(b'\n',p); n2=int(d[p:nl2]); return n1,blocks,p,n2,nl2+1
