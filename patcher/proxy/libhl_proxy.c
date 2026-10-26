// Proxy for HashLink's libhl.dll (32-bit). Every export forwards to libhl_orig.dll (see generated libhl.def)
// except hl_global_init, which first patches the game's embedded bytecode in memory.
// The exe on disk is never touched (it is SteamStub-protected); by the time main() calls hl_global_init
// the DRM check is over and the bytecode resource has not been read yet.
//
// Patch: the game sets Viewport.NATIVE_WIDTH = 683 at startup and shows min(window, pixelScale * NATIVE_WIDTH)
// pixels, masking the rest black. We repoint that `Int` op to another int-table entry (same varint length).
// Built without a C runtime (kernel32 only), see build_proxy.py. DCUW_TEST builds a file-based test harness.
#include <windows.h>

#define ORIGINAL_WIDTH 683
#define ORIGINAL_HEIGHT 400
#define TARGET_WIDTH 960  // game pixels; fills any 21:9 screen (32:9 would need ~1280), no effect on 16:9
#define OP_INT 1
#define OP_GETGLOBAL 36
#define OP_SETFIELD 39

static int slen(const char *s) { int n = 0; while (s[n]) n++; return n; }

static int same(const void *a, const void *b, unsigned n) {
    const unsigned char *x = a, *y = b;
    while (n--) if (*x++ != *y++) return 0;
    return 1;
}

static void hexnum(char *out, unsigned v) {
    char tmp[9]; int n = 0;
    do { tmp[n++] = "0123456789abcdef"[v & 15]; v >>= 4; } while (v);
    out[0] = '0'; out[1] = 'x';
    for (int i = 0; i < n; i++) out[2 + i] = tmp[n - 1 - i];
    out[2 + n] = 0;
}

// ---- HashLink bytecode scan -------------------------------------------------------------------------------

typedef struct { const unsigned char *p, *end; int bad; } reader;

static int rbyte(reader *r) {
    if (r->p >= r->end) { r->bad = 1; return 0; }
    return *r->p++;
}

static int rindex(reader *r) {
    int b = rbyte(r), v;
    if (!(b & 0x80)) return b & 0x7f;
    if (!(b & 0x40)) v = rbyte(r) | ((b & 31) << 8);
    else { int c = rbyte(r), d = rbyte(r), e = rbyte(r); v = ((b & 31) << 24) | (c << 16) | (d << 8) | e; }
    return (b & 0x20) ? -v : v;
}

static unsigned varint_len(int v) { return v >= 0 && v < 0x80 ? 1 : v > -0x2000 && v < 0x2000 ? 2 : 4; }

static void encode_varint(int v, unsigned char *out) {
    unsigned s = v < 0 ? 0x20 : 0, a = v < 0 ? -v : v;
    if (!s && a < 0x80) { out[0] = a; return; }
    if (a < 0x2000) { out[0] = 0x80 | s | (a >> 8); out[1] = a & 0xff; return; }
    out[0] = 0xc0 | s | (a >> 24); out[1] = (a >> 16) & 0xff; out[2] = (a >> 8) & 0xff; out[3] = a & 0xff;
}

typedef struct { unsigned pos, len; int new_idx, new_val; } patch_t;

// Finds `Int r, 683; GetGlobal g; SetField g.f = r; Int r, 400; GetGlobal g2; SetField g2.(f+1) = r`
// (NATIVE_WIDTH then NATIVE_HEIGHT in Viewport's static init) and picks the replacement int index.
// Returns NULL on success, else an error message. bc points at the "HLB" header.
static const char *find_patch(const unsigned char *bc, unsigned size, patch_t *out) {
    reader r = {bc + 4, bc + size, 0};
    if (size < 8 || !same(bc, "HLB\4", 4)) return "no HashLink v4 bytecode";
    rindex(&r);  // flags
    int nints = rindex(&r);
    for (int i = 0; i < 8; i++) rindex(&r);  // floats, strings, types, globals, natives, functions, constants, entry
    if (r.bad || nints <= 0 || (unsigned)(r.end - r.p) / 4 < (unsigned)nints) return "bad bytecode header";
    const unsigned char *ints = r.p;
#define INTV(i) ((int)(ints[4 * (i)] | ints[4 * (i) + 1] << 8 | ints[4 * (i) + 2] << 16 | (unsigned)ints[4 * (i) + 3] << 24))
#define IS_INT(i, v) ((i) >= 0 && (i) < nints && INTV(i) == (v))

    int found = 0;
    for (const unsigned char *p = ints + 4 * nints; p < r.end; p++) {
        if (*p != OP_INT) continue;
        reader q = {p + 1, r.end, 0};
        int reg = rindex(&q);
        const unsigned char *idx_at = q.p;
        int idx = rindex(&q);
        if (q.bad || !IS_INT(idx, ORIGINAL_WIDTH)) continue;
        unsigned idx_len = (unsigned)(q.p - idx_at);
        if (rbyte(&q) != OP_GETGLOBAL) continue;
        int g = rindex(&q); rindex(&q);
        if (rbyte(&q) != OP_SETFIELD || rindex(&q) != g) continue;
        int field = rindex(&q);
        if (rindex(&q) != reg || rbyte(&q) != OP_INT || rindex(&q) != reg) continue;
        int idx2 = rindex(&q);
        if (!IS_INT(idx2, ORIGINAL_HEIGHT) || rbyte(&q) != OP_GETGLOBAL) continue;
        int g2 = rindex(&q); rindex(&q);
        if (rbyte(&q) != OP_SETFIELD || rindex(&q) != g2 || rindex(&q) != field + 1 || rindex(&q) != reg || q.bad) continue;
        found++;
        out->pos = (unsigned)(idx_at - bc);
        out->len = idx_len;
    }
    if (found != 1) return found ? "NATIVE_WIDTH init found more than once, not patching" : "NATIVE_WIDTH init not found (already patched or game changed)";

    // shortcut: only widths already present in the int table are usable; fine for the 960 default.
    out->new_idx = -1;
    for (int i = 0; i < nints; i++) {
        int v = INTV(i);
        if (v >= TARGET_WIDTH && v <= TARGET_WIDTH + 128 && varint_len(i) == out->len && (out->new_idx < 0 || v < out->new_val)) {
            out->new_idx = i; out->new_val = v;
        }
    }
    return out->new_idx < 0 ? "no usable width value in int table" : NULL;
}

#ifndef DCUW_TEST

// ---- proxy ------------------------------------------------------------------------------------------------

static HMODULE self;

// Path of a file next to this dll.
static void sibling(char *out, const char *name) {
    int i = (int)GetModuleFileNameA(self, out, MAX_PATH);
    while (i > 0 && out[i - 1] != '\\') i--;
    for (int k = 0; name[k] && i < MAX_PATH - 1; k++) out[i++] = name[k];
    out[i] = 0;
}

// Appends "a b c\r\n" to dc_ultrawide.log (any part may be NULL).
static void log3(const char *a, const char *b, const char *c) {
    char path[MAX_PATH];
    DWORD w;
    sibling(path, "dc_ultrawide.log");
    HANDLE h = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    const char *parts[3] = {a, b, c};
    for (int i = 0; i < 3; i++) if (parts[i]) { WriteFile(h, parts[i], slen(parts[i]), &w, NULL); WriteFile(h, " ", 1, &w, NULL); }
    WriteFile(h, "\r\n", 2, &w, NULL);
    CloseHandle(h);
}

// Locates the "HLB\x04" bytecode header inside the exe's .rsrc section.
static unsigned char *find_bytecode(unsigned *avail) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    for (int i = 0; i < nt->FileHeader.NumberOfSections; i++, s++) {
        if (!same(s->Name, ".rsrc", 6)) continue;
        unsigned char *p = base + s->VirtualAddress, *end = p + s->Misc.VirtualSize - 4;
        for (; p < end; p++)
            if (same(p, "HLB\4", 4)) { *avail = (unsigned)(end + 4 - p); return p; }
    }
    return NULL;
}

static void apply_patch(void) {
    char exe[MAX_PATH], num[12], *exename = exe;
    unsigned avail;
    patch_t pt = {0, 0, 0, 0};
    GetModuleFileNameA(NULL, exe, MAX_PATH);
    for (char *p = exe; *p; p++) if (*p == '\\') exename = p + 1;

    unsigned char *bc = find_bytecode(&avail);
    const char *err = bc ? find_patch(bc, avail, &pt) : "bytecode not found";
    if (err) { log3(exename, err, NULL); return; }
    unsigned char enc[4];
    DWORD prot;
    encode_varint(pt.new_idx, enc);
    if (!VirtualProtect(bc + pt.pos, pt.len, PAGE_READWRITE, &prot)) { log3(exename, "VirtualProtect failed", NULL); return; }
    for (unsigned i = 0; i < pt.len; i++) bc[pt.pos + i] = enc[i];
    VirtualProtect(bc + pt.pos, pt.len, prot, &prot);
    hexnum(num, pt.pos);
    log3(exename, "patched NATIVE_WIDTH at", num);
}

typedef void (*void_fn)(void);

void hl_global_init(void) {
    static void_fn real;
    if (!real) {
        char orig[MAX_PATH];
        apply_patch();
        sibling(orig, "libhl_orig.dll");
        HMODULE h = LoadLibraryA(orig);
        real = h ? (void_fn)GetProcAddress(h, "hl_global_init") : NULL;
        if (!real) { log3("cannot load", orig, NULL); return; }
    }
    real();
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)r;
    if (reason == DLL_PROCESS_ATTACH) { self = h; DisableThreadLibraryCalls(h); }
    return TRUE;
}

#else

// ---- test harness: dcuw_test.exe <exe path>  ->  prints "<pos from HLB> <len> <new idx> <new value>" ----------

static void out(const char *s) { DWORD w; WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), s, slen(s), &w, NULL); }

void start(void) {
    char *cmd = GetCommandLineA(), num[12];
    if (*cmd == '"') { cmd++; while (*cmd && *cmd != '"') cmd++; if (*cmd) cmd++; }
    else while (*cmd && *cmd != ' ') cmd++;
    while (*cmd == ' ') cmd++;
    if (*cmd == '"') { char *q = ++cmd; while (*q && *q != '"') q++; *q = 0; }
    HANDLE h = CreateFileA(cmd, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) { out("cannot open\n"); ExitProcess(2); }
    DWORD size = GetFileSize(h, NULL), got = 0;
    unsigned char *d = VirtualAlloc(NULL, size, MEM_COMMIT, PAGE_READWRITE);
    ReadFile(h, d, size, &got, NULL);
    CloseHandle(h);
    unsigned i = 0;
    while (i + 4 <= got && !same(d + i, "HLB\4", 4)) i++;
    patch_t pt;
    const char *err = find_patch(d + i, got - i, &pt);
    if (err) { out(err); out("\n"); ExitProcess(1); }
    hexnum(num, pt.pos); out(num); out(" ");
    hexnum(num, pt.len); out(num); out(" ");
    hexnum(num, (unsigned)pt.new_idx); out(num); out(" ");
    hexnum(num, (unsigned)pt.new_val); out(num); out("\n");
    ExitProcess(0);
}

#endif
