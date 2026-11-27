// SPDX-License-Identifier: Apache-2.0
// Manual S2Arm differential bench. The workload and episode labels are synthetic.
#include <assert.h>
#include <sched.h>
#include <stdio.h>
#include <time.h>

#include "rb_energy_predict.h"
#include "rb_probe_policy.h"
#include "rb_spec_gate.h"

#define SEC(n) ((uint64_t)(n) * UINT64_C(1000000000))

enum { STABLE, GRADUAL, ABRUPT, SCENE, PLATEAU, WARM, MISSING, PRESSURE, REPLAY_COUNT };
enum { HISTORICAL, REACTIVE, OBSERVE, ACTIVE, MODE_COUNT };
static const char *const scenarios[] = {
    "stable", "gradual", "abrupt", "scene_complexity", "false_plateau", "warm_launch", "missing_or_stale", "os_pressure"
};
static const char *const modes[] = {"historical", "reactive", "observe_v2", "active_v2"};

typedef struct {
    uint64_t submitted, duration;
    int work, eligible;
} sample;

static sample make_sample(int scenario, unsigned t) {
    sample s = {SEC(t), 240000 + 1000 * (t % 3), RB_ENERGY_WORK_BUSY, 1};
    if (scenario == SCENE) s.work = t < 15 ? RB_ENERGY_WORK_LIGHT : RB_ENERGY_WORK_BUSY;
    if (scenario == GRADUAL || scenario == PLATEAU || scenario == MISSING || scenario == PRESSURE) {
        if (t >= 13 && t < 21) s.duration = 262000 + (t - 13) * 9000;
    }
    if ((scenario == GRADUAL && t >= 21 && t < 38) || (scenario == ABRUPT && t >= 21 && t < 38))
        s.duration = 810000 + 1000 * (t % 3);
    if (scenario == PLATEAU && t >= 21) s.duration = t < 38 ? 336000 : 242000;
    if (scenario == WARM) s.duration = t < 20 ? 810000 + 1000 * (t % 3) : 240000;
    if (scenario == MISSING && t >= 15 && t < 39) {
        s.submitted = t < 25 ? 0 : SEC(t - 3);
        s.work = RB_ENERGY_WORK_UNKNOWN;
    }
    if (scenario == PRESSURE && t >= 17 && t < 28) s.eligible = 0;
    return s;
}

typedef struct {
    unsigned optional, foreground, capped, prevention, slow;
    uint64_t final_reference;
} outcome;

static outcome replay(int scenario, int mode) {
    rb_energy_guard reactive = {0};
    rb_energy_predictor predictor = {0};
    rb_spec_gate gate = RB_SPEC_GATE_INITIALIZER;
    outcome out = {0};
    for (unsigned t = 1; t <= 60; ++t) {
        sample s = make_sample(scenario, t);
        int capped = mode == REACTIVE && rb_energy_update(&reactive, SEC(t),
                            s.submitted, s.duration, s.work, s.eligible);
        if (mode == OBSERVE || mode == ACTIVE)
            rb_energy_predict_update(&predictor, SEC(t), s.submitted, s.duration, s.work, s.eligible);
        if (!out.prevention && predictor.state == RB_ENERGY_PREVENT) out.prevention = t;
        if (!out.slow && (capped || predictor.state == RB_ENERGY_SLOW)) out.slow = t;
        unsigned limit = mode == ACTIVE ? rb_energy_predict_limit(&predictor) : 0;
        out.capped += limit == 1 || capped;
        int level = !s.eligible ? RB_SPEC_HOLD : capped ? RB_SPEC_ONE : RB_SPEC_RUN;
        rb_spec_publish_energy_plan(&gate, level, 2, RB_FLOOR_NONE, capped, limit);
        int optional0 = rb_spec_admit(&gate, 0), optional1 = rb_spec_admit(&gate, 1);
        out.optional += optional0 + optional1;
        rb_spec_release(&gate, &optional1);
        rb_spec_release(&gate, &optional0);
        // The required path continues to obtain its ordinary lease on both lanes.
        int foreground0 = rb_spec_admit_startup(&gate, 0, RB_LEASE_FOREGROUND);
        int foreground1 = rb_spec_admit_startup(&gate, 1, RB_LEASE_FOREGROUND);
        out.foreground += foreground0 + foreground1;
        rb_spec_release(&gate, &foreground1);
        rb_spec_release(&gate, &foreground0);
    }
    out.final_reference = predictor.reference_ns;
    pthread_cond_destroy(&gate.changed);
    pthread_cond_destroy(&gate.primary);
    pthread_mutex_destroy(&gate.mutex);
    return out;
}

static void compare_modes(void) {
    for (int scenario = 0; scenario < REPLAY_COUNT; ++scenario) {
        outcome cases[MODE_COUNT];
        for (int mode = 0; mode < MODE_COUNT; ++mode) {
            cases[mode] = replay(scenario, mode);
            outcome o = cases[mode];
            printf("synthetic scenario=%s mode=%s first_prevention_s=%u first_slow_detection_s=%u "
                   "optional=%u foreground=%u capped_intervals=%u final_reference_ns=%llu\n",
                   scenarios[scenario], modes[mode], o.prevention, o.slow, o.optional, o.foreground, o.capped,
                   (unsigned long long)o.final_reference);
        }
        assert(cases[HISTORICAL].optional == cases[OBSERVE].optional);
        assert(cases[HISTORICAL].foreground == cases[OBSERVE].foreground);
        assert(cases[HISTORICAL].foreground == cases[ACTIVE].foreground);
        assert(cases[OBSERVE].prevention == cases[ACTIVE].prevention);
        if (scenario == GRADUAL || scenario == PLATEAU) {
            assert(cases[ACTIVE].prevention && cases[ACTIVE].optional < cases[HISTORICAL].optional);
        } else {
            assert(!cases[ACTIVE].prevention);
        }
        if (scenario == GRADUAL || scenario == ABRUPT) {
            assert(cases[ACTIVE].slow == 22 && cases[REACTIVE].slow == 22);
        } else {
            assert(!cases[ACTIVE].slow);
        }
        if (scenario == WARM) assert(cases[ACTIVE].final_reference == 240000);
    }
}

// Illustrative alternatives on the same time series. These heuristics use
// the same relative reference and never change the engine's admission plan.
static void compare_features(void) {
    for (int scenario = 0; scenario < REPLAY_COUNT; ++scenario) {
        rb_energy_predictor predictor = {0};
        unsigned ewma = 1000, load_streak = 0;
        unsigned average_warning = 0, load_warning = 0, abrupt_alarm = 0;
        for (unsigned t = 1; t <= 60; ++t) {
            sample s = make_sample(scenario, t);
            int valid = rb_energy_predict_update(&predictor, SEC(t), s.submitted, s.duration, s.work, s.eligible);
            if (!valid || !predictor.ratio_permille) {
                ewma = 1000;
                load_streak = 0;
                continue;
            }
            ewma = (3 * ewma + predictor.ratio_permille) / 4;
            if (!average_warning && ewma >= 1200) average_warning = t;
            if (!load_warning && ++load_streak >= 15) load_warning = t;
            if (!abrupt_alarm && predictor.ratio_permille >= 1600) abrupt_alarm = t;
        }
        printf("synthetic alternatives scenario=%s ewma_first_s=%u sustained_load_first_s=%u change_first_s=%u\n",
               scenarios[scenario], average_warning, load_warning, abrupt_alarm);
    }
}

static void disrupted_replay(void) {
    rb_energy_predictor p = {0};
    for (unsigned t = 1; t <= 3; ++t)
        rb_energy_predict_update(&p, SEC(t), SEC(t), 240000, RB_ENERGY_WORK_BUSY, 1);
    assert(p.reference_ns == 240000);
    rb_energy_predict_update(&p, SEC(10), SEC(10), 810000, RB_ENERGY_WORK_BUSY, 1);
    rb_energy_predict_update(&p, SEC(11), SEC(10), 810000, RB_ENERGY_WORK_BUSY, 1);
    assert(!rb_energy_predict_limit(&p));
    rb_energy_predict_update(&p, SEC(11), SEC(11), 810000, RB_ENERGY_WORK_BUSY, 1);
    assert(p.state == RB_ENERGY_SLOW);
    rb_energy_predict_update(&p, SEC(12), SEC(12), 810000, RB_ENERGY_WORK_LIGHT, 1);
    assert(p.state == RB_ENERGY_SLOW);
    rb_energy_predict_update(&p, SEC(13), SEC(13), 810000, RB_ENERGY_WORK_LIGHT, 1);
    assert(!rb_energy_predict_limit(&p));
    rb_energy_predict_update(&p, SEC(15), SEC(13) + 1, 810000, RB_ENERGY_WORK_BUSY, 0);
    rb_energy_predict_update(&p, SEC(16), SEC(13) + 1, 810000, RB_ENERGY_WORK_BUSY, 1);
    assert(!p.last_ns && !p.slow);
    rb_energy_predict_update(&p, SEC(17), SEC(17), 810000, RB_ENERGY_WORK_BUSY, 1);
    rb_energy_predict_update(&p, SEC(18), SEC(18), 810000, RB_ENERGY_WORK_BUSY, 1);
    rb_energy_predict_update(&p, SEC(29), SEC(19), 810000, RB_ENERGY_WORK_BUSY, 1);
    assert(!rb_energy_predict_limit(&p) && p.reference_ns == 240000);
    p = (rb_energy_predictor){0};
    assert(!p.reference_ns && !p.seen_ns);

    assert(rb_probe_every_parse("0") == 0);
    assert(rb_probe_adapt_period(1, 0, 0) == SEC(3));
    assert(rb_probe_adapt_period(1, 1, 0) == SEC(5));
    assert(rb_probe_adapt_period(1, 1, 1) == SEC(2));
    assert(rb_probe_adapt_period(0, 1, 1) == SEC(8));
    assert(!rb_probe_adapt_due(SEC(7), SEC(8), SEC(2), 9));
    assert(!rb_probe_adapt_due(SEC(7), SEC(5), SEC(2), 7));
    assert(rb_probe_adapt_due(SEC(7), SEC(5), SEC(2), 9));
}

typedef struct {
    rb_spec_gate gate;
    _Atomic int reached_denial;
} shared_gate;

static void *take_after_release(void *arg) {
    shared_gate *shared = arg;
    for (;;) {
        uint64_t ticket = atomic_load(&shared->gate.epoch);
        int lease = rb_spec_admit(&shared->gate, 1);
        if (lease) {
            rb_spec_release(&shared->gate, &lease);
            return NULL;
        }
        atomic_store(&shared->reached_denial, 1);
        rb_spec_wait_worker(&shared->gate, ticket, 1);
    }
}

static void check_reopened_slot(void) {
    shared_gate shared = {.gate = RB_SPEC_GATE_INITIALIZER};
    rb_spec_publish_energy_plan(&shared.gate, RB_SPEC_RUN, 2, RB_FLOOR_NONE, 0, 1);
    int optional = rb_spec_admit(&shared.gate, 0);
    int foreground = rb_spec_admit_startup(&shared.gate, 1, RB_LEASE_FOREGROUND);
    assert(optional && foreground && !rb_spec_admit(&shared.gate, 1));
    pthread_t waiter;
    assert(!pthread_create(&waiter, NULL, take_after_release, &shared));
    while (!atomic_load(&shared.reached_denial)) sched_yield();
    rb_spec_release(&shared.gate, &foreground);
    assert(!rb_spec_admit(&shared.gate, 1));
    uint64_t before = atomic_load(&shared.gate.epoch);
    rb_spec_release(&shared.gate, &optional);
    assert(atomic_load(&shared.gate.epoch) != before);
    assert(!pthread_join(waiter, NULL));
    assert(!shared.gate.active);
    pthread_cond_destroy(&shared.gate.changed);
    pthread_cond_destroy(&shared.gate.primary);
    pthread_mutex_destroy(&shared.gate.mutex);
}

static void noisy_replay(void) {
    for (unsigned mode = 0; mode < 2; ++mode) {
        uint32_t input = UINT32_C(0x521d6713);  // same replay in both arms
        struct timespec start, end;
        assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &start));
        unsigned checksum = 0;
        for (unsigned session = 0; session < 2000; ++session) {
            rb_energy_predictor p = {0};
            rb_energy_guard old = {0};
            for (unsigned t = 1; t <= 120; ++t) {
                input = input * UINT32_C(1664525) + UINT32_C(1013904223);
                uint64_t observed = input % 17 == 0 ? 0 : SEC(t);
                int work = input % 3, eligible = input % 11 != 0;
                uint64_t probe = 240000 + input % 1000000;
                if (mode) {
                    uint64_t previous = p.reference_ns;
                    rb_energy_predict_update(&p, SEC(t), observed, probe, work, eligible);
                    assert(!previous || p.reference_ns <= previous);
                    assert(eligible || !rb_energy_predict_limit(&p));
                    checksum += p.state;
                } else checksum += rb_energy_update(&old, SEC(t), observed, probe, work, eligible);
            }
        }
        assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &end));
        int64_t ns = (end.tv_sec - start.tv_sec) * INT64_C(1000000000) + end.tv_nsec - start.tv_nsec;
        printf("synthetic cpu mode=%s observations=240000 process_ns=%llu checksum=%u\n",
               mode ? "v2" : "reactive", (unsigned long long)ns, checksum);
    }
}

int main(void) {
    compare_modes();
    compare_features();
    disrupted_replay();
    check_reopened_slot();
    noisy_replay();
}
