#!/usr/bin/env python3
"""AnimTextData readers/writers (formats verified by byte-exact round trips of every loose file; see RESEARCH_LOG §1).
 AnimationOffsets/<hash>.txt : b'V4\\n' | u8 len(incl NUL) + behaviour path + NUL | u32 count | count x ( u8 len+NUL name , u8 len+NUL path )
 AnimationFileData/<hash>.txt: text  '3\\n1\\n<hash>\\n<count>\\n' + one path per line (behaviours first, then animations with .hkx), count = number of lines."""
import struct
def parse_offsets(b):
    assert b[:3]==b'V4\n'; i=3; n=b[i]; beh=b[i+1:i+1+n]; assert beh.endswith(b'\0'); i+=1+n
    cnt=struct.unpack_from('<I',b,i)[0]; i+=4; ents=[]
    for _ in range(cnt):
        n=b[i]; nm=b[i+1:i+1+n]; assert nm.endswith(b'\0'); i+=1+n
        n=b[i]; pa=b[i+1:i+1+n]; assert pa.endswith(b'\0'); i+=1+n; ents.append((nm[:-1].decode('latin1'),pa[:-1].decode('latin1')))
    return beh[:-1].decode('latin1'),ents,b[i:]   # b[i:] = second table, kept as raw bytes
def write_offsets(beh,ents,tail=b''):
    o=b'V4\n'+bytes([len(beh)+1])+beh.encode('latin1')+b'\0'+struct.pack('<I',len(ents))
    for nm,pa in ents: o+=bytes([len(nm)+1])+nm.encode('latin1')+b'\0'+bytes([len(pa)+1])+pa.encode('latin1')+b'\0'
    return o+tail
def parse_filedata(b):
    t=b.decode('latin1'); L=t.split('\n'); assert L[-1]=='' ; L=L[:-1]
    assert L[0]=='3' and L[1]=='1'; h=L[2]; cnt=int(L[3]); paths=L[4:]; assert cnt==len(paths),(cnt,len(paths)); return h,paths
def write_filedata(h,paths): return ('3\n1\n%s\n%d\n'%(h,len(paths))+''.join(p+'\n' for p in paths)).encode('latin1')
