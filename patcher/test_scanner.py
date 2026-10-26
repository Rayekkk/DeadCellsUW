"""Test: the proxy's C bytecode scan (proxy/libhl_proxy.c, built as dcuw_test.exe) must find the same patch
as this reference implementation, which locates Viewport.NATIVE_WIDTH by name with a full bytecode parse.
Also checks that an already-patched exe is not patched twice.

usage:  python test_scanner.py <game dir>
"""
import os, subprocess, sys, tempfile
from hlparse import parse, NAMES
from build_proxy import build_test

EXES = ('deadcells.exe', 'deadcells_gl.exe')  # DX and GL builds embed different bytecode


def all_fields(types, ti):
    t = types[ti]
    if t['k'] == 15: return t['fields']
    if t['k'] not in (11, 21): return []
    return (all_fields(types, t['super']) if t['super'] >= 0 else []) + t['fields']


def find_native_width_op(m):
    """Return (func, op index) of the `Int` op whose value is stored into Viewport.NATIVE_WIDTH."""
    T = m['types']
    found = []
    for f in m['funcs']:
        R, ops = f['regs'], f['ops']
        for i, (op, a) in enumerate(ops):
            if NAMES[op] != 'SetField': continue
            fl = all_fields(T, R[a[0]])
            if T[R[a[0]]].get('name') != '$Viewport' or a[1] >= len(fl) or fl[a[1]][0] != 'NATIVE_WIDTH': continue
            for j in range(i - 1, max(-1, i - 8), -1):
                if NAMES[ops[j][0]] == 'Int' and ops[j][1][0] == a[2]:
                    found.append((f, j)); break
    if len(found) != 1:
        raise RuntimeError('expected exactly one NATIVE_WIDTH init, found %d (game update changed the code?)' % len(found))
    return found[0]


def varint_len(v):
    return 1 if 0 <= v < 0x80 else 2 if -0x2000 < v < 0x2000 else 4


def encode_varint(v):
    s, a = (0x20 if v < 0 else 0), abs(v)
    if s == 0 and a < 0x80: return bytes([a])
    if a < 0x2000: return bytes([0x80 | s | (a >> 8), a & 0xff])
    return bytes([0xc0 | s | (a >> 24), (a >> 16) & 0xff, (a >> 8) & 0xff, a & 0xff])


def arg_offsets(d, ofs):
    """Offsets of the two varint args of a 2-arg op starting at ofs (opcode byte)."""
    p, out = ofs + 1, []
    for _ in range(2):
        out.append(p)
        b = d[p]
        p += 1 if not b & 0x80 else 2 if not b & 0x40 else 4
    return out, p


def pick_int(ints, width, need_len):
    # shortcut: only values already present in the int table can be used; add a table entry if exact widths matter.
    cands = sorted((v, i) for i, v in enumerate(ints) if width <= v <= width + 128 and varint_len(i) == need_len)
    if not cands: raise RuntimeError('no usable int >= %d in bytecode table' % width)
    return cands[0]


def find_patch(exe_bytes, width):
    """(offset from the HLB header, old bytes, new bytes, new NATIVE_WIDTH) for the bytecode embedded in the exe."""
    m = parse(exe_bytes)
    start = exe_bytes.find(b'HLB\x04')
    d = bytearray(exe_bytes[start:m['end']])
    f, j = find_native_width_op(m)
    (_, idx_ofs), end = arg_offsets(d, f['ofs'][j] - start)
    val, new_idx = pick_int(m['ints'], width, end - idx_ofs)
    old = bytes(d[idx_ofs:end])
    d[idx_ofs:end] = encode_varint(new_idx)

    # self-check: the patched bytecode parses completely and yields the new value
    m2 = parse(bytes(d))
    f2, j2 = find_native_width_op(m2)
    assert m2['ints'][f2['ops'][j2][1][1]] == val and m2['end'] == len(d)
    return idx_ofs, old, bytes(d[idx_ofs:end]), val


def scan(harness, path):
    r = subprocess.run([harness, path], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    if len(sys.argv) != 2: sys.exit(__doc__)
    game = sys.argv[1]
    harness = build_test()
    for name in EXES:
        exe = os.path.join(game, name)
        if not os.path.exists(exe): continue
        data = open(exe, 'rb').read()
        off, old, new, val = find_patch(data, 960)
        code, outp = scan(harness, exe)
        pos, ln, idx, v = outp.split()
        assert code == 0 and int(pos, 16) == off and int(ln, 16) == len(old) and int(v, 16) == val, (name, outp, off, old, val)
        assert encode_varint(int(idx, 16)) == new, (name, outp, new)
        print('%s: C scan == reference (+0x%x, %s -> %s, width %d)' % (name, off, old.hex(), new.hex(), val))

        start = data.find(b'HLB')
        patched = bytearray(data); patched[start + off:start + off + len(new)] = new
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as t: t.write(patched)
        try:
            code, outp = scan(harness, t.name)
            assert code == 1 and 'not found' in outp, outp
            print('%s: already-patched bytecode is left alone' % name)
        finally:
            os.remove(t.name)


if __name__ == '__main__':
    main()
