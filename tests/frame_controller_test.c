/* Deterministic tests for the project-local frame controller. */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include "frame_controller.h"

#define PERIOD 33333333ULL
#define BASE 1000000000ULL

typedef struct {
    atomic_uint_fast64_t now;
    atomic_int waits;
} FakeClock;

static uint64_t fake_now(void *ctx) {
    return atomic_load(&((FakeClock *)ctx)->now);
}
static void fake_sleep_until(uint64_t deadline, void *ctx) {
    FakeClock *clock = ctx;
    atomic_fetch_add(&clock->waits, 1);
    uint64_t value = atomic_load(&clock->now);
    while (value < deadline &&
           !atomic_compare_exchange_weak(&clock->now, &value, deadline)) {}
}
static void reset_clock(FakeClock *clock) {
    atomic_store(&clock->now, BASE);
    atomic_store(&clock->waits, 0);
}
static zp_controller *make_controller(FakeClock *clock) {
    zp_clock hooks = {.now_ns=fake_now, .sleep_until_ns=fake_sleep_until, .ctx=clock};
    zp_controller *pacer = zp_controller_new(PERIOD, hooks);
    assert(pacer);
    return pacer;
}
static void test_independent_swapchains(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    zp_ticket first=zp_frame_reserve(p, 1, 100, 1);
    assert(first.deadline_ns == BASE);
    zp_frame_wait(p,first); zp_frame_complete(p,first,1);
    zp_ticket another=zp_frame_reserve(p, 1, 200, 1);
    assert(another.deadline_ns == BASE);
    zp_frame_wait(p,another); zp_frame_complete(p,another,1);
    zp_ticket second=zp_frame_reserve(p, 1, 100, 1);
    assert(second.deadline_ns == BASE+PERIOD);
    zp_frame_wait(p,second); zp_frame_complete(p,second,1);
    assert(fake_now(&clock)==BASE+PERIOD);
    assert(atomic_load(&clock.waits)==1);
    zp_controller_delete(p);
}
static void test_reset_on_disable(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    zp_ticket a=zp_frame_reserve(p,1,11,1);
    zp_frame_complete(p,a,1);
    zp_ticket disabled=zp_frame_reserve(p,1,11,0);
    assert(disabled.deadline_ns==0);
    zp_frame_complete(p,disabled,0);
    zp_ticket reenabled=zp_frame_reserve(p,1,11,1);
    assert(reenabled.deadline_ns==BASE);
    zp_frame_complete(p,reenabled,1);
    zp_controller_delete(p);
}
static void test_failure_does_not_consume_next_frame(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    zp_ticket first=zp_frame_reserve(p,2,12,1);
    zp_frame_complete(p,first,1);
    zp_ticket fail=zp_frame_reserve(p,2,12,1);
    assert(fail.deadline_ns==BASE+PERIOD);
    zp_frame_complete(p,fail,0);
    zp_ticket retry=zp_frame_reserve(p,2,12,1);
    assert(retry.deadline_ns==BASE+PERIOD);
    zp_frame_complete(p,retry,1);
    zp_controller_delete(p);
}
static void test_overdue_frame_drops_debt(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    zp_ticket a=zp_frame_reserve(p,1,10,1);
    zp_frame_complete(p,a,1);
    atomic_store(&clock.now,BASE+PERIOD*5);
    zp_ticket b=zp_frame_reserve(p,1,10,1);
    assert(b.deadline_ns==BASE+PERIOD*5);
    zp_frame_complete(p,b,1);
    zp_controller_delete(p);
}
static void test_destroy_and_reuse_handle(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    zp_ticket old=zp_frame_reserve(p,1,77,1);
    zp_frame_forget(p,1,77);
    zp_ticket fresh=zp_frame_reserve(p,1,77,1);
    assert(fresh.deadline_ns==BASE);
    zp_frame_complete(p,fresh,1);
    zp_frame_complete(p,old,1); /* no use-after-free on old stream */
    zp_frame_forget(p,1,77);
    zp_controller_delete(p);
}
static void test_device_isolation(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    zp_ticket one=zp_frame_reserve(p,1,44,1);
    zp_frame_complete(p,one,1);
    zp_ticket two=zp_frame_reserve(p,2,44,1);
    assert(two.deadline_ns==BASE);
    zp_frame_complete(p,two,1);
    zp_device_forget(p,1);
    zp_ticket newer=zp_frame_reserve(p,1,44,1);
    assert(newer.deadline_ns==BASE);
    zp_frame_complete(p,newer,1);
    zp_controller_delete(p);
}
typedef struct {
    zp_controller *p;
    zp_ticket ticket;
} Worker;
static void *reserve_from_thread(void *ctx) {
    Worker *w=ctx;
    w->ticket=zp_frame_reserve(w->p,9,333,1);
    return NULL;
}
static void test_concurrent_reservations_have_unique_deadlines(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    zp_ticket first=zp_frame_reserve(p,9,333,1);
    zp_frame_complete(p,first,1);
    Worker a={.p=p}, b={.p=p};
    pthread_t ta,tb;
    assert(!pthread_create(&ta,NULL,reserve_from_thread,&a));
    assert(!pthread_create(&tb,NULL,reserve_from_thread,&b));
    pthread_join(ta,NULL); pthread_join(tb,NULL);
    assert(a.ticket.deadline_ns != b.ticket.deadline_ns);
    assert((a.ticket.deadline_ns==BASE+PERIOD &&
            b.ticket.deadline_ns==BASE+PERIOD*2) ||
           (b.ticket.deadline_ns==BASE+PERIOD &&
            a.ticket.deadline_ns==BASE+PERIOD*2));
    zp_frame_wait(p,a.ticket); zp_frame_complete(p,a.ticket,1);
    zp_frame_wait(p,b.ticket); zp_frame_complete(p,b.ticket,1);
    zp_controller_delete(p);
}

enum { STRESS_THREADS=8, STRESS_FRAMES=32 };
typedef struct {
    zp_controller *controller;
    uint64_t times[STRESS_FRAMES];
} StressWorker;
static void *stress_reserve(void *ctx) {
    StressWorker *w=ctx;
    for(unsigned i=0;i<STRESS_FRAMES;i++) {
        zp_ticket ticket=zp_frame_reserve(w->controller,90,900,1);
        assert(ticket.stream && ticket.deadline_ns);
        w->times[i]=ticket.deadline_ns;
        zp_frame_complete(w->controller,ticket,1);
    }
    return NULL;
}
static int compare_u64(const void *a,const void *b) {
    uint64_t x=*(const uint64_t *)a, y=*(const uint64_t *)b;
    return (x>y)-(x<y);
}
static void test_parallel_stress_and_recreated_swapchain(void) {
    FakeClock clock; reset_clock(&clock);
    zp_controller *p=make_controller(&clock);
    pthread_t threads[STRESS_THREADS];
    StressWorker workers[STRESS_THREADS]={0};
    for(unsigned i=0;i<STRESS_THREADS;i++) {
        workers[i].controller=p;
        assert(!pthread_create(&threads[i],NULL,stress_reserve,&workers[i]));
    }
    uint64_t all[STRESS_THREADS*STRESS_FRAMES];
    for(unsigned i=0;i<STRESS_THREADS;i++) {
        assert(!pthread_join(threads[i],NULL));
        for(unsigned j=0;j<STRESS_FRAMES;j++)
            all[i*STRESS_FRAMES+j]=workers[i].times[j];
    }
    qsort(all,STRESS_THREADS*STRESS_FRAMES,sizeof(all[0]),compare_u64);
    assert(all[0]==BASE);
    for(unsigned i=1;i<STRESS_THREADS*STRESS_FRAMES;i++)
        assert(all[i]==all[i-1]+PERIOD);
    zp_frame_forget(p,90,900);
    zp_ticket reused=zp_frame_reserve(p,90,900,1);
    assert(reused.deadline_ns==BASE);
    zp_frame_complete(p,reused,1);
    zp_controller_delete(p);
}
int main(void) {
    test_independent_swapchains();
    test_reset_on_disable();
    test_failure_does_not_consume_next_frame();
    test_overdue_frame_drops_debt();
    test_destroy_and_reuse_handle();
    test_device_isolation();
    test_concurrent_reservations_have_unique_deadlines();
    test_parallel_stress_and_recreated_swapchain();
    puts("Frame controller: 8 deterministic checks passed");
    return 0;
}
