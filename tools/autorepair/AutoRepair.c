/*
 * MOAutoRepair.dll - player buildings repair themselves, like the AI's do.
 *
 * A Syringe plugin for Mental Omega 3.3.6 (YR 1.001 + Ares 3.0) with one job
 * and one hook. Written for this project; the approach follows the engine
 * facts documented by MagicShiba's MO_ExperienceEnhancements (notes/建筑一键
 * 维修.md), every address re-verified by disassembling gamemd.exe here.
 *
 * Every SCAN_INTERVAL game frames it walks BuildingClass::Array and, for each
 * building of the local player that is damaged, not already being repaired
 * and repairable by the engine's own test, queues the standard Repair event -
 * byte for byte what clicking the wrench on it does (gamemd 0x4AC0C3..0x4AC207).
 * The engine then repairs it and charges for it exactly as for a manual click.
 *
 * Why not just flip IsBeingRepaired like the AI path (0x450708) does: that
 * writes simulation state locally without an event. The event keeps every
 * client in step and is the path the game itself uses for the player.
 *
 * The Repair event TOGGLES repair (handler 0x4C6EFD -> SetRepairState(-1)),
 * so a building already under repair must never get one: that would switch
 * its repair off. The engine clears IsBeingRepaired at full health (0x4509B4).
 */
/* Built with no C runtime and no headers (see build.py): the few Windows
 * types it needs are spelled out here. */
typedef unsigned long DWORD;
typedef int BOOL;
typedef void* HINSTANCE;
typedef void* LPVOID;
#define WINAPI __stdcall
#define TRUE 1

#define HOOK_MAINLOOP    0x55D360u  /* MainLoop entry: mov al,[0xA8E9A0] (5 B, no rel) */

#define SCAN_INTERVAL    30         /* game frames between scans (15 fps -> ~2 s) */
#define MAX_PER_SCAN     8          /* events queued per scan at most */
#define OUTLIST_RESERVE  32         /* leave this many OutList slots to the player */
/* An event runs a few frames after it is queued. Until then IsBeingRepaired
 * still reads 0, and a second event would toggle the repair straight back
 * off - so a building we asked for is left alone for this long. */
#define RESEND_GUARD     90         /* frames */
#define GUARD_SLOTS      64

/* ---- engine data (gamemd.exe, verified by disassembly) --------------------- */
#define CURRENT_FRAME    (*(volatile int*)0xA8ED84)           /* written by EventClass ctor 0x4C6623 */
#define PLAYER_HOUSE     (*(char* volatile*)0xA83D4C)         /* HouseClass::CurrentPlayer */
#define BUILDINGS_ITEMS  (*(char** volatile*)0xA8EB44)        /* BuildingClass::Array.Items */
#define BUILDINGS_COUNT  (*(volatile int*)0xA8EB50)           /* BuildingClass::Array.Count */

#define OUT_COUNT        (*(volatile int*)0xA802C8)           /* OutList count, max 128 */
#define OUT_TAIL         (*(volatile int*)0xA802D0)           /* OutList write index */
#define OUT_EVENTS       ((char*)0xA802D4)                    /* OutList events, 111 B each */
#define OUT_TIMES        ((DWORD*)0xA83A54)                   /* OutList timestamps */
#define OUT_CAPACITY     128
#define EVENT_SIZE       111

#define BUILDING_VTABLE  0x7E3EBCu
#define VT_CAN_REPAIR    0x94   /* -> 0x452630: Health>0 && ClickRepairable && ... (bool in AL) */
#define VT_MISSION       0x184  /* -> 0x5B3040: current mission */
#define MISSION_CONSTRUCTION 0x12
#define MISSION_SELLING      0x13

#define OFF_HEALTH       0x6C   /* ObjectClass::Health */
#define OFF_INLIMBO      0x81
#define OFF_ISALIVE      0x90
#define OFF_OWNER        0x21C  /* TechnoClass::Owner */
#define OFF_TYPE         0x520  /* BuildingClass::Type */
#define OFF_REPAIRING    0x6E8  /* BuildingClass::IsBeingRepaired */
#define OFF_STRENGTH     0xA0   /* ObjectTypeClass::Strength */
#define OFF_HOUSE_INDEX  0x30   /* HouseClass::ArrayIndex */

#define EVENT_REPAIR     0x15

/* thiscall entry points, called through fastcall (ecx = this, edx unused) */
typedef unsigned char (__fastcall *FnBool)(void* self, void* edx);
typedef int (__fastcall *FnInt)(void* self, void* edx);
typedef void* (__fastcall *FnTargetCtor)(void* target, void* edx, void* object);       /* 0x6E6AB0 */
typedef void* (__fastcall *FnEventCtor)(void* ev, void* edx, int house, int type,
                                        DWORD target_id, DWORD target_rtti);         /* 0x4C65E0 */
#define TargetClass_ctor ((FnTargetCtor)0x6E6AB0u)
#define EventClass_ctor  ((FnEventCtor)0x4C65E0u)
/* the game's own import slot for WINMM!timeGetTime (0x4ABFB6 loads it from here) */
#define game_timeGetTime ((DWORD (WINAPI*)(void))(*(DWORD*)0x7E1530u))

static int g_lastScan = -1000000;
static struct { char* b; int frame; } g_guard[GUARD_SLOTS];

static int recently_sent(char* b, int frame)
{
    for (int i = 0; i < GUARD_SLOTS; ++i)
        if (g_guard[i].b == b && frame - g_guard[i].frame < RESEND_GUARD && frame >= g_guard[i].frame)
            return 1;
    return 0;
}

static void remember(char* b, int frame)
{
    int oldest = 0;
    for (int i = 0; i < GUARD_SLOTS; ++i) {
        if (g_guard[i].b == b || !g_guard[i].b) { oldest = i; break; }
        if (g_guard[i].frame < g_guard[oldest].frame) oldest = i;
    }
    g_guard[oldest].b = b;
    g_guard[oldest].frame = frame;
}

static int is_exe_ptr(DWORD p) { return p >= 0x401000u && p < 0x898000u; }

static void* vfunc(char* obj, int slot) { return (void*)(*(DWORD**)obj)[slot / 4]; }

/* the building is one we should queue a Repair event for */
static int wants_repair(char* b, char* player)
{
    if (!b || *(DWORD*)b != BUILDING_VTABLE) return 0;          /* really a building */
    if (*(char**)(b + OFF_OWNER) != player) return 0;           /* ours */
    if (!*(unsigned char*)(b + OFF_ISALIVE) || *(unsigned char*)(b + OFF_INLIMBO)) return 0;
    if (*(unsigned char*)(b + OFF_REPAIRING)) return 0;         /* event would toggle it OFF */
    char* type = *(char**)(b + OFF_TYPE);
    if (!type) return 0;
    int health = *(int*)(b + OFF_HEALTH);
    if (health <= 0 || health >= *(int*)(type + OFF_STRENGTH)) return 0;
    int mission = ((FnInt)vfunc(b, VT_MISSION))(b, 0);
    if (mission == MISSION_CONSTRUCTION || mission == MISSION_SELLING) return 0;
    void* can = vfunc(b, VT_CAN_REPAIR);
    if (!is_exe_ptr((DWORD)can)) return 0;
    return ((FnBool)can)(b, 0) != 0;                             /* only AL is meaningful */
}

/* exactly what the wrench click does (0x4AC0D3..0x4AC207) */
static int queue_repair(char* b, char* player)
{
    if (OUT_COUNT >= OUT_CAPACITY - OUTLIST_RESERVE) return 0;
    DWORD target[2] = {0, 0};
    TargetClass_ctor(target, 0, b);
    char ev[EVENT_SIZE + 1];
    for (int i = 0; i < (int)sizeof ev; ++i) ev[i] = 0;
    EventClass_ctor(ev, 0, *(int*)(player + OFF_HOUSE_INDEX), EVENT_REPAIR,
                    target[0], target[1] & 0xFF);
    int slot = OUT_TAIL;
    char* dst = OUT_EVENTS + slot * EVENT_SIZE;
    for (int i = 0; i < EVENT_SIZE; ++i) dst[i] = ev[i];
    OUT_TIMES[slot] = game_timeGetTime();
    OUT_TAIL = (slot + 1) & (OUT_CAPACITY - 1);
    OUT_COUNT = OUT_COUNT + 1;
    return 1;
}

static void scan(void)
{
    int frame = CURRENT_FRAME;
    if (frame - g_lastScan < SCAN_INTERVAL && frame >= g_lastScan) return;
    g_lastScan = frame;

    char* player = PLAYER_HOUSE;
    char** items = BUILDINGS_ITEMS;
    int count = BUILDINGS_COUNT;
    if (!player || !items || count <= 0 || count > 100000) return;

    int sent = 0;
    for (int i = 0; i < count && sent < MAX_PER_SCAN; ++i) {
        char* b = items[i];
        if (!recently_sent(b, frame) && wants_repair(b, player) && queue_repair(b, player)) {
            remember(b, frame);
            ++sent;
        }
    }
}

/* ---- Syringe ---------------------------------------------------------------- */

__declspec(dllexport) DWORD __cdecl AutoRepair_MainLoop(void* regs)
{
    (void)regs;
    scan();
    return 0;   /* replay the stolen mov al,[0xA8E9A0] and carry on */
}

struct SyHookDecl { unsigned int addr, size; const char* name; unsigned int pad; };

__attribute__((section(".syhks00"), used, aligned(16)))
const struct SyHookDecl g_hooks[] = {
    { HOOK_MAINLOOP, 5u, "AutoRepair_MainLoop", 0u },
};

/* No C runtime: this is the whole entry point (linked with -nostdlib). */
BOOL WINAPI DllMainCRTStartup(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)h; (void)reason; (void)r;
    return TRUE;
}
