#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "present_telemetry.h"
int main(void) {
    assert(zp_present_elapsed(1,55,1000000000ULL)==0);
    assert(zp_present_elapsed(1,55,1033333333ULL)==33333333ULL);
    assert(zp_present_elapsed(1,66,1033333333ULL)==0);
    assert(zp_present_elapsed(2,55,1033333333ULL)==0);
    assert(zp_present_elapsed(1,55,1066666666ULL)==33333333ULL);
    zp_present_forget(1,55);
    assert(zp_present_elapsed(1,55,1100000000ULL)==0);
    assert(zp_present_elapsed(1,55,1133333333ULL)==33333333ULL);
    zp_present_forget_device(1);
    assert(zp_present_elapsed(1,55,1200000000ULL)==0);
    assert(zp_present_elapsed(2,55,1066666666ULL)==33333333ULL);
    assert(zp_present_elapsed(2,55,1066666666ULL)==0);
    assert(zp_present_send(33333333ULL)==0);
    puts("Telemetry state isolated, handle reuse safe and datagram sent");
    return 0;
}
