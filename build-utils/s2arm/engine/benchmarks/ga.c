#include <stdint.h>
#include <pthread.h>
#include <stdatomic.h>
#define LOG(...) ((void)0)
#define GVA_LO 0xC000000000ull
#define GVA_HI 0x10000000000ull
typedef struct { uint64_t g,c,n; } gva_ent;
static gva_ent *g_gva; static int g_ngva;
static pthread_rwlock_t g_gva_lk=PTHREAD_RWLOCK_INITIALIZER;
uint64_t nvn_ga2ca(uint64_t a) {
    if (a < GVA_LO || a >= GVA_HI) return a;
    uint64_t r = a; int lo = 0, hi;
    pthread_rwlock_rdlock(&g_gva_lk);
    hi = g_ngva - 1;
    while (lo <= hi) { int m = (lo + hi) / 2; if (g_gva[m].g <= a) lo = m + 1; else hi = m - 1; }   // hi = 最后一个起点 ≤ a 的段
    if (hi >= 0 && a - g_gva[hi].g <= g_gva[hi].n && g_gva[hi].c) r = g_gva[hi].c + (a - g_gva[hi].g);   // c = 0：虚拟池没拿到预留段   // 段尾（a = 起点 + 字节数）也认：游戏常给区间末端
    pthread_rwlock_unlock(&g_gva_lk);
    static _Atomic int once; if (r == a && !once++) LOG("【红】[nvn] GPU 地址 %#llx 不在任何池里（池已释放 / 游戏算错）：原样交给回放（只报一次）", (unsigned long long)a);
    return r;
}
