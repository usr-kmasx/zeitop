/* 32-bit child output to verify correct preload path. */
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    const char *preload = getenv("LD_PRELOAD");
    puts(preload ? preload : "MISSING_LD_PRELOAD");
    return preload ? 0 : 1;
}
