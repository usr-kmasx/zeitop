#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "workload.h"
int main(void) {
  assert(zp_workload_ns("5",0,1)==5000000ULL);
  assert(zp_workload_ns("20",17,1)==20000000ULL);
  assert(zp_workload_ns("33",9,1)==33000000ULL);
  assert(zp_workload_ns("40",20,1)==40000000ULL);
  assert(zp_workload_ns("random",1,1234)==zp_workload_ns("random",1,1234));
  uint64_t a[4]={5000000ULL,20000000ULL,33000000ULL,40000000ULL};
  int found[4]={0};
  for(uint32_t i=0;i<200;i++){
    uint64_t x=zp_workload_ns("random",i,567);
    int valid=0;
    for(int j=0;j<4;j++) if(x==a[j]) {found[j]=1;valid=1;}
    assert(valid);
  }
  for(int j=0;j<4;j++)assert(found[j]);
  assert(zp_workload_ns("invalid",0,1)==UINT64_MAX);
  assert(zp_workload_ns(NULL,0,1)==0);
  puts("workload selection: deterministic, variable, and invalid inputs verified");
  return 0;
}
