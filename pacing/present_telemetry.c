#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include "present_telemetry.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

typedef struct zp_sample {
    uintptr_t device;
    uint64_t swapchain;
    uint64_t last_ns;
    struct zp_sample *next;
} zp_sample;
static pthread_mutex_t sample_lock=PTHREAD_MUTEX_INITIALIZER;
static zp_sample *samples;
static _Thread_local int telemetry_socket=-1;

uint64_t zp_present_elapsed(uintptr_t device,uint64_t swapchain,uint64_t time_ns) {
    if(!device || !swapchain || !time_ns)return 0;
    pthread_mutex_lock(&sample_lock);
    zp_sample *s=samples;
    while(s && (s->device!=device || s->swapchain!=swapchain))s=s->next;
    if(!s) {
        s=calloc(1,sizeof(*s));
        if(!s){pthread_mutex_unlock(&sample_lock);return 0;}
        s->device=device;
        s->swapchain=swapchain;
        s->next=samples;
        samples=s;
    }
    uint64_t delta=time_ns>s->last_ns && s->last_ns ? time_ns-s->last_ns : 0;
    s->last_ns=time_ns;
    pthread_mutex_unlock(&sample_lock);
    return delta;
}
void zp_present_forget(uintptr_t device,uint64_t swapchain) {
    pthread_mutex_lock(&sample_lock);
    zp_sample **link=&samples;
    while(*link) {
        zp_sample *s=*link;
        if(s->device==device && s->swapchain==swapchain) {
            *link=s->next;free(s);
        } else link=&s->next;
    }
    pthread_mutex_unlock(&sample_lock);
}
void zp_present_forget_device(uintptr_t device) {
    pthread_mutex_lock(&sample_lock);
    zp_sample **link=&samples;
    while(*link) {
        zp_sample *s=*link;
        if(s->device==device) {
            *link=s->next;free(s);
        } else link=&s->next;
    }
    pthread_mutex_unlock(&sample_lock);
}
int zp_present_send(uint64_t elapsed_ns) {
    if(!elapsed_ns)return -1;
    const char *root=getenv("ZEITOP_HOME");
    if(!root || root[0]!='/')return -1;
    struct sockaddr_un address={0};
    address.sun_family=AF_UNIX;
    int n=snprintf(address.sun_path,sizeof(address.sun_path),
                   "%s/runtime/zeitop.sock",root);
    if(n<=0 || (size_t)n>=sizeof(address.sun_path))return -1;
    if(telemetry_socket<0) {
        telemetry_socket=socket(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);
        if(telemetry_socket<0)return -1;
    }
    char packet[80];
    n=snprintf(packet,sizeof(packet),"ZEITOP1 %ld %.3f",
               (long)getpid(),(double)elapsed_ns/1000000.0);
    if(n<=0 || (size_t)n>=sizeof(packet))return -1;
    return sendto(telemetry_socket,packet,(size_t)n,MSG_DONTWAIT,
                  (struct sockaddr *)&address,sizeof(address))==n ? 0 : -1;
}
