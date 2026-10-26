"""Builds release/libhl_uw.dll (32-bit proxy for libhl.dll) from proxy/libhl_proxy.c with the mingw-w64 GNU toolchain.

All exports of the real libhl.dll are forwarded to libhl_orig.dll with their original ordinals,
except hl_global_init which the proxy implements.

usage:  python build_proxy.py <path to the real libhl.dll>   (libhl_orig.dll once the mod is installed)
"""
import os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROXY_DIR = os.path.join(HERE, 'proxy')
OUT_DLL = os.path.join(HERE, '..', 'release', 'libhl_uw.dll')
OWN = {'hl_global_init'}
# kernel32 imports used by the proxy and by the DCUW_TEST harness
K32_IMPORTS = ['CloseHandle@4', 'CreateFileA@28', 'DisableThreadLibraryCalls@4', 'ExitProcess@4', 'GetCommandLineA@0',
               'GetFileSize@8', 'GetModuleFileNameA@12', 'GetModuleHandleA@4', 'GetProcAddress@8', 'GetStdHandle@4',
               'LoadLibraryA@4', 'ReadFile@20', 'VirtualAlloc@16', 'VirtualProtect@16', 'WriteFile@20']
CFLAGS = ['-m32', '-O2', '-Wall', '-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns', '-fno-stack-protector']


def exports(path):
    """[(ordinal, name)] of a PE32 dll's named exports."""
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec, osz = struct.unpack_from('<H', d, pe + 6)[0], struct.unpack_from('<H', d, pe + 20)[0]
    opt = pe + 24
    if struct.unpack_from('<H', d, opt)[0] != 0x10b: raise ValueError('%s is not a 32-bit dll' % path)
    secs = [struct.unpack_from('<8sIIII', d, opt + osz + 40 * i) for i in range(nsec)]

    def off(rva):
        for _, vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return rva - va + ro
        raise ValueError('rva %x outside sections' % rva)

    e = off(struct.unpack_from('<I', d, opt + 96)[0])
    base, _, nn, _, an, ao = struct.unpack_from('<IIIIII', d, e + 16)
    out = []
    for i in range(nn):
        name = d[off(struct.unpack_from('<I', d, off(an) + 4 * i)[0]):].split(b'\0', 1)[0].decode()
        out.append((base + struct.unpack_from('<H', d, off(ao) + 2 * i)[0], name))
    return out


def run(*a):
    subprocess.check_call(a, cwd=PROXY_DIR)


def kernel32_lib():
    # GNU toolchain (gcc -m32 + ld i386pe): MSVC's x86 linker rejects .def forwarders. No C runtime, only kernel32.
    open(os.path.join(PROXY_DIR, 'kernel32.def'), 'w').write(
        'LIBRARY kernel32.dll\nEXPORTS\n' + ''.join('  %s\n' % f for f in K32_IMPORTS))
    run('dlltool', '-m', 'i386', '-f', '--32', '-k', '-d', 'kernel32.def', '-l', 'libk32.a')


def build(real_dll):
    exps = exports(real_dll)
    assert OWN <= {n for _, n in exps}, 'hl_global_init missing from %s' % real_dll
    lines = ['LIBRARY libhl', 'EXPORTS']
    for ordn, name in sorted(exps):
        lines.append('  %s @%d' % (name, ordn) if name in OWN else '  %s=libhl_orig.%s @%d' % (name, name, ordn))
    open(os.path.join(PROXY_DIR, 'libhl.def'), 'w').write('\n'.join(lines) + '\n')

    kernel32_lib()
    run('gcc', *CFLAGS, '-c', 'libhl_proxy.c', '-o', 'libhl_proxy.o')
    out = os.path.abspath(OUT_DLL)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run('ld', '-m', 'i386pe', '--shared', '-s', '-e', '_DllMain@12', '--dynamicbase', '--nxcompat',
        '-o', out, 'libhl_proxy.o', 'libhl.def', 'libk32.a')

    assert sorted(exports(out)) == sorted(exps), 'proxy exports differ from the real libhl'
    print('built %s (%d exports)' % (out, len(exps)))
    return out


def build_test():
    """dcuw_test.exe: runs the proxy's bytecode scan on an exe file (see test_scanner.py)."""
    kernel32_lib()
    run('gcc', *CFLAGS, '-DDCUW_TEST', '-c', 'libhl_proxy.c', '-o', 'dcuw_test.o')
    run('ld', '-m', 'i386pe', '-e', '_start', '--subsystem', 'console', '-o', 'dcuw_test.exe', 'dcuw_test.o', 'libk32.a')
    return os.path.join(PROXY_DIR, 'dcuw_test.exe')


if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit(__doc__)
    build(sys.argv[1])
