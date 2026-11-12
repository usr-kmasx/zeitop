/* Thread-safe, per-swapchain deadline reservation for early frame pacing. */
#include "frame_controller.h"
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>

struct zp_stream {
    uintptr_t device;
    uint64_t swapchain;
    uint64_t last_deadline_ns;
    unsigned outstanding;
    int retired;
    struct zp_stream *next;
};
struct zp_controller {
    pthread_mutex_t lock;
    zp_clock clock;
    uint64_t period_ns;
    zp_stream *streams;
};
static zp_stream *find_active(zp_controller *c, uintptr_t device, uint64_t swapchain) {
    for (zp_stream *s=c->streams; s; s=s->next) {
        if (!s->retired && s->device==device && s->swapchain==swapchain)
            return s;
    }
    return NULL;
}
/* The final pending ticket owns a retired stream until it completes. */
static void collect_retired(zp_controller *c) {
    zp_stream **slot=&c->streams;
    while (*slot) {
        zp_stream *s=*slot;
        if (s->retired && s->outstanding==0) {
            *slot=s->next;
            free(s);
        } else slot=&s->next;
    }
}
zp_controller *zp_controller_new(uint64_t period_ns, zp_clock clock) {
    if (!period_ns || !clock.now_ns || !clock.sleep_until_ns)
        return NULL;
    zp_controller *c=calloc(1,sizeof(*c));
    if (!c) return NULL;
    if (pthread_mutex_init(&c->lock,NULL)!=0) {
        free(c);return NULL;
    }
    c->period_ns=period_ns;
    c->clock=clock;
    return c;
}
void zp_controller_delete(zp_controller *c) {
    if (!c) return;
    pthread_mutex_lock(&c->lock);
    zp_stream *stream=c->streams;
    while (stream) {
        zp_stream *next=stream->next;
        free(stream);
        stream=next;
    }
    pthread_mutex_unlock(&c->lock);
    pthread_mutex_destroy(&c->lock);
    free(c);
}
zp_ticket zp_frame_reserve(zp_controller *c, uintptr_t device,
                           uint64_t swapchain, int enabled) {
    zp_ticket ticket={0};
    if (!c || !device || !swapchain) return ticket;
    pthread_mutex_lock(&c->lock);
    zp_stream *stream=find_active(c,device,swapchain);
    if (!enabled) {
        if (stream) stream->last_deadline_ns=0;
        pthread_mutex_unlock(&c->lock);
        return ticket;
    }
    if (!stream) {
        stream=calloc(1,sizeof(*stream));
        if (!stream) {
            pthread_mutex_unlock(&c->lock);
            return ticket; /* safe unpaced fallback */
        }
        stream->device=device;
        stream->swapchain=swapchain;
        stream->next=c->streams;
        c->streams=stream;
    }
    uint64_t now=c->clock.now_ns(c->clock.ctx);
    uint64_t target=now;
    if (stream->last_deadline_ns &&
        UINT64_MAX-c->period_ns > stream->last_deadline_ns) {
        uint64_t next=stream->last_deadline_ns+c->period_ns;
        if (next > now) target=next;
    }
    ticket.stream=stream;
    ticket.previous_ns=stream->last_deadline_ns;
    ticket.deadline_ns=target;
    stream->last_deadline_ns=target;
    stream->outstanding++;
    pthread_mutex_unlock(&c->lock);
    return ticket;
}
void zp_frame_wait(zp_controller *c, zp_ticket ticket) {
    if (c && ticket.stream && ticket.deadline_ns > c->clock.now_ns(c->clock.ctx))
        c->clock.sleep_until_ns(ticket.deadline_ns,c->clock.ctx);
}
void zp_frame_complete(zp_controller *c, zp_ticket ticket, int success) {
    if (!c || !ticket.stream) return;
    pthread_mutex_lock(&c->lock);
    zp_stream *stream=ticket.stream;
    if (!success && !stream->retired &&
        stream->last_deadline_ns==ticket.deadline_ns)
        stream->last_deadline_ns=ticket.previous_ns;
    if (stream->outstanding) stream->outstanding--;
    collect_retired(c);
    pthread_mutex_unlock(&c->lock);
}
void zp_frame_forget(zp_controller *c, uintptr_t device, uint64_t swapchain) {
    if (!c) return;
    pthread_mutex_lock(&c->lock);
    for (zp_stream *s=c->streams; s; s=s->next) {
        if (s->device==device && s->swapchain==swapchain)
            s->retired=1;
    }
    collect_retired(c);
    pthread_mutex_unlock(&c->lock);
}
void zp_device_forget(zp_controller *c, uintptr_t device) {
    if (!c) return;
    pthread_mutex_lock(&c->lock);
    for (zp_stream *s=c->streams; s; s=s->next) {
        if (s->device==device) s->retired=1;
    }
    collect_retired(c);
    pthread_mutex_unlock(&c->lock);
}
