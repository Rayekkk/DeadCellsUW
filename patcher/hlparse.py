# Minimal HashLink bytecode (v4) reader: types, functions, ops (with file offsets).
import struct, sys

NARGS = [2,2,2,2,2,2,1, 3,3,3,3,3,3,3,3,3,3,3,3,3, 2,2,1,1,
         2,3,4,5,6,-1,-1,-1,-1, 2,3,3, 2,2,3,3,2,2,3,3,
         2,2,2,2,3,3,3,3,3,3,3,3,3,3,1, 2,2,2,2,2,2,2,
         0,1,1,1,-1,1,2,1, 3,3,3,3,3,3,3,3,
         1,2,2,2,2,2,2,2,-1,2,2,4,3, 0,2,3,0,3,3]
NAMES = ("Mov Int Float Bool Bytes String Null Add Sub Mul SDiv UDiv SMod UMod Shl SShr UShr And Or Xor "
         "Neg Not Incr Decr Call0 Call1 Call2 Call3 Call4 CallN CallMethod CallThis CallClosure "
         "StaticClosure InstanceClosure VirtualClosure GetGlobal SetGlobal Field SetField GetThis SetThis DynGet DynSet "
         "JTrue JFalse JNull JNotNull JSLt JSGte JSGt JSLte JULt JUGte JNotLt JNotGte JEq JNotEq JAlways "
         "ToDyn ToSFloat ToUFloat ToInt SafeCast UnsafeCast ToVirtual Label Ret Throw Rethrow Switch NullCheck Trap EndTrap "
         "GetI8 GetI16 GetMem GetArray SetI8 SetI16 SetMem SetArray New ArraySize Type GetType GetTID Ref Unref Setref "
         "MakeEnum EnumAlloc EnumIndex EnumField SetEnumField Assert RefData RefOffset Nop Prefetch Asm").split()

class R:
    def __init__(s, d, p): s.d, s.p = d, p
    def b(s):
        v = s.d[s.p]; s.p += 1; return v
    def i32(s):
        v = struct.unpack_from('<i', s.d, s.p)[0]; s.p += 4; return v
    def f64(s):
        v = struct.unpack_from('<d', s.d, s.p)[0]; s.p += 8; return v
    def idx(s):
        b = s.b()
        if not b & 0x80: return b & 0x7f
        if not b & 0x40:
            v = s.b() | ((b & 31) << 8)
        else:
            c, d_, e = s.b(), s.b(), s.b()
            v = ((b & 31) << 24) | (c << 16) | (d_ << 8) | e
        return -v if b & 0x20 else v
    def strings(s, n):
        size = s.i32(); data = s.d[s.p:s.p+size]; s.p += size
        out, off = [], 0
        for _ in range(n):
            l = s.idx(); out.append(data[off:off+l].decode('utf8', 'replace')); off += l + 1
        return out

def parse(d):
    start = d.find(b'HLB\x04')
    if start < 0: raise ValueError('no HashLink v4 bytecode found')
    r = R(d, start + 3)
    ver = r.b(); flags = r.idx()
    nints, nfloats, nstrings, ntypes, nglobals, nnatives, nfuncs, nconsts, entry = [r.idx() for _ in range(9)]
    ints = [r.i32() for _ in range(nints)]
    floats = [r.f64() for _ in range(nfloats)]
    strs = r.strings(nstrings)
    dfiles = r.strings(r.idx()) if flags & 1 else []
    types = []
    for _ in range(ntypes):
        k = r.b(); t = {'k': k}
        if k in (10, 20):
            t['args'] = [r.idx() for _ in range(r.b())]; t['ret'] = r.idx()
        elif k in (11, 21):
            t['name'] = strs[r.idx()]; t['super'] = r.idx(); t['global'] = r.idx()
            nf, np_, nb = r.idx(), r.idx(), r.idx()
            t['fields'] = [(strs[r.idx()], r.idx()) for _ in range(nf)]
            t['protos'] = [(strs[r.idx()], r.idx(), r.idx()) for _ in range(np_)]
            t['bindings'] = [(r.idx(), r.idx()) for _ in range(nb)]
        elif k in (14, 19, 22):
            t['of'] = r.idx()
        elif k == 15:
            t['fields'] = [(strs[r.idx()], r.idx()) for _ in range(r.idx())]
        elif k == 17:
            t['name'] = strs[r.idx()]
        elif k == 18:
            t['name'] = strs[r.idx()]; t['global'] = r.idx()
            t['cons'] = []
            for _ in range(r.idx()):
                n = strs[r.idx()]; t['cons'].append((n, [r.idx() for _ in range(r.idx())]))
        types.append(t)
    globals_ = [r.idx() for _ in range(nglobals)]
    natives = [(strs[r.idx()], strs[r.idx()], r.idx(), r.idx()) for _ in range(nnatives)]
    funcs = []
    for _ in range(nfuncs):
        f = {'type': r.idx(), 'findex': r.idx()}
        nregs, nops = r.idx(), r.idx()
        f['regs'] = [r.idx() for _ in range(nregs)]
        ops, f['ofs'] = [], []
        for _ in range(nops):
            f['ofs'].append(r.p)  # file offset of the opcode byte, used for patching
            op = r.b(); n = NARGS[op]
            if n == -1:
                if NAMES[op] == 'Switch':
                    a = [r.idx(), r.idx()]; a += [r.idx() for _ in range(a[1])]; a.append(r.idx())
                else:
                    a = [r.idx(), r.idx()]; c = r.b(); a += [r.idx() for _ in range(c)]
            else:
                a = [r.idx() for _ in range(n)]
            ops.append((op, a))
        f['ops'] = ops
        if flags & 1:
            dbg, curfile, curline, i = [], -1, 0, 0
            while i < nops:
                c = r.b()
                if c & 1:
                    curfile = ((c >> 1) << 8) | r.b()
                elif c & 2:
                    cnt = (c >> 2) & 15
                    for _ in range(cnt): dbg.append((curfile, curline)); i += 1
                    curline += c >> 6
                elif c & 4:
                    curline += c >> 3; dbg.append((curfile, curline)); i += 1
                else:
                    b2, b3 = r.b(), r.b(); curline = (c >> 3) | (b2 << 5) | (b3 << 13)
                    dbg.append((curfile, curline)); i += 1
            f['dbg'] = dbg
            if ver >= 3:
                f['assigns'] = [(strs[r.idx()], r.idx()) for _ in range(r.idx())]
        funcs.append(f)
    consts = []
    for _ in range(nconsts):
        g = r.idx(); consts.append((g, [r.idx() for _ in range(r.idx())]))
    return dict(ver=ver, ints=ints, floats=floats, strs=strs, dfiles=dfiles, types=types, globals=globals_,
                natives=natives, funcs=funcs, consts=consts, entry=entry, end=r.p)

if __name__ == '__main__':
    m = parse(open(sys.argv[1], 'rb').read())
    print('parsed ok; funcs', len(m['funcs']), 'types', len(m['types']), 'end', hex(m['end']))
