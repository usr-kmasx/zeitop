#define _POSIX_C_SOURCE 200809L
#include "timed_present_run.h"
#include "workload.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* Experiment only. We do not patch the application's Vulkan device. */
enum { MAX_IMAGES=16, MAX_FEEDBACK=32 };
static uint64_t clock_monotonic_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC,&ts);
    return (uint64_t)ts.tv_sec*1000000000ULL+(uint64_t)ts.tv_nsec;
}
static void sleep_ns(uint64_t ns) {
    struct timespec ts={.tv_sec=(time_t)(ns/1000000000ULL),
                        .tv_nsec=(long)(ns%1000000000ULL)};
    while(nanosleep(&ts,&ts)==-1) {}
}
static int calibrate_present_time(const zp_timed_present_options *o,
                                  uint64_t *stage_ns,uint64_t *host_ns,
                                  uint64_t *deviation_ns) {
    if(!o->calibrate)return -1;
    VkSwapchainCalibratedTimestampInfoEXT extra={
        .sType=VK_STRUCTURE_TYPE_SWAPCHAIN_CALIBRATED_TIMESTAMP_INFO_EXT,
        .swapchain=o->swapchain,
        .presentStage=VK_PRESENT_STAGE_IMAGE_FIRST_PIXEL_OUT_BIT_EXT,
        .timeDomainId=o->stage_local_domain_id
    };
    VkCalibratedTimestampInfoKHR stamps[2]={
        {.sType=VK_STRUCTURE_TYPE_CALIBRATED_TIMESTAMP_INFO_KHR,
         .pNext=&extra,.timeDomain=VK_TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT},
        {.sType=VK_STRUCTURE_TYPE_CALIBRATED_TIMESTAMP_INFO_KHR,
         .timeDomain=VK_TIME_DOMAIN_CLOCK_MONOTONIC_KHR}
    };
    uint64_t values[2]={0},deviation=0;
    VkResult result=o->calibrate(o->device,2,stamps,values,&deviation);
    if(result!=VK_SUCCESS || !values[0] || !values[1]) {
        fprintf(stderr,"ZEITOP_TIMESTAMP_CALIBRATION_FAILED=%d\n",result);
        return -1;
    }
    *stage_ns=values[0];
    *host_ns=values[1];
    *deviation_ns=deviation;
    return 0;
}
static unsigned drain_feedback(const zp_timed_present_options *o,FILE *output) {
    VkPastPresentationTimingInfoEXT request={
        .sType=VK_STRUCTURE_TYPE_PAST_PRESENTATION_TIMING_INFO_EXT,
        .swapchain=o->swapchain
    };
    VkPastPresentationTimingEXT events[MAX_FEEDBACK]={0};
    VkPresentStageTimeEXT stages[MAX_FEEDBACK][2]={0};
    for(unsigned i=0;i<MAX_FEEDBACK;i++) {
        events[i].sType=VK_STRUCTURE_TYPE_PAST_PRESENTATION_TIMING_EXT;
        events[i].presentStageCount=2;
        events[i].pPresentStages=stages[i];
    }
    VkPastPresentationTimingPropertiesEXT response={
        .sType=VK_STRUCTURE_TYPE_PAST_PRESENTATION_TIMING_PROPERTIES_EXT,
        .presentationTimingCount=MAX_FEEDBACK,
        .pPresentationTimings=events
    };
    VkResult result=o->get_past(o->device,&request,&response);
    if(result!=VK_SUCCESS && result!=VK_INCOMPLETE) {
        fprintf(stderr,"ZEITOP_GET_PRESENT_FEEDBACK_FAILED=%d\n",result);
        return 0;
    }
    unsigned found=0;
    for(uint32_t i=0;i<response.presentationTimingCount;i++) {
        uint64_t first_pixel_out_ns=0;
        uint64_t queue_end_ns=0;
        for(uint32_t k=0;k<events[i].presentStageCount && k<2;k++) {
            if(stages[i][k].stage==VK_PRESENT_STAGE_IMAGE_FIRST_PIXEL_OUT_BIT_EXT)
                first_pixel_out_ns=stages[i][k].time;
            if(stages[i][k].stage==VK_PRESENT_STAGE_QUEUE_OPERATIONS_END_BIT_EXT)
                queue_end_ns=stages[i][k].time;
        }
        if(first_pixel_out_ns) {
            fprintf(output,"%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%d,%" PRIu64 "\n",
                    events[i].presentId,events[i].targetTime,
                    first_pixel_out_ns,queue_end_ns,events[i].timeDomain,
                    events[i].timeDomainId);
            found++;
        }
    }
    fflush(output);
    return found;
}

int zp_run_timed_present(const zp_timed_present_options *o) {
    if(!o || !o->get_past || !o->calibrate || !o->feedback_path ||
       o->frame_count<1 || o->frame_count>240) return 2;
    uint64_t local_start=0,host_start=0,max_deviation=0;
    if(calibrate_present_time(o,&local_start,&host_start,&max_deviation)!=0)return 3;
    printf("ZEITOP_REAL_CLOCK_CALIBRATION_DEVIATION_NS=%" PRIu64 "\n",max_deviation);
    uint64_t start_cpu=clock_monotonic_ns();
    /* Start 70ms ahead of the calibrated stage-local clock. */
    uint64_t base=local_start+70000000ULL;
    const uint64_t period=o->target_interval_ns ? o->target_interval_ns : 33333333ULL;
    uint64_t total_cpu_work_ns=0;
    const char *pattern=o->cpu_work_pattern ? o->cpu_work_pattern : "0";
    if (zp_workload_ns(pattern,0,o->cpu_work_seed)==UINT64_MAX) return 20;
    printf("ZEITOP_TEST_WORK_PATTERN=%s\n",pattern);
    if(period < 8000000ULL || period > 1000000000ULL) return 19;
    printf("ZEITOP_REQUESTED_INTERVAL_NS=%" PRIu64 "\n",period);
    printf("ZEITOP_NEAREST_REFRESH=%d\n",o->nearest_refresh);
    uint32_t image_count=0;
    VkResult rc=vkGetSwapchainImagesKHR(o->device,o->swapchain,&image_count,NULL);
    if(rc!=VK_SUCCESS || image_count<2 || image_count>MAX_IMAGES) {
        fprintf(stderr,"ZEITOP_SWAPCHAIN_IMAGE_COUNT_ERROR rc=%d count=%u\n",rc,image_count);
        return 4;
    }
    VkImage images[MAX_IMAGES]={0};
    rc=vkGetSwapchainImagesKHR(o->device,o->swapchain,&image_count,images);
    if(rc!=VK_SUCCESS) return 5;
    VkCommandPool pool=VK_NULL_HANDLE;
    VkCommandPoolCreateInfo pool_info={
        .sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
        .queueFamilyIndex=o->queue_family
    };
    rc=vkCreateCommandPool(o->device,&pool_info,NULL,&pool);
    if(rc!=VK_SUCCESS) return 6;
    VkCommandBuffer commands[MAX_IMAGES]={0};
    VkCommandBufferAllocateInfo cmd_alloc={
        .sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool=pool,
        .level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount=image_count
    };
    rc=vkAllocateCommandBuffers(o->device,&cmd_alloc,commands);
    if(rc!=VK_SUCCESS) {
        vkDestroyCommandPool(o->device,pool,NULL);
        return 7;
    }
    VkSemaphore acquired[MAX_IMAGES]={0},ready[MAX_IMAGES]={0};
    VkFence fences[MAX_IMAGES]={0};
    VkSemaphoreCreateInfo sem_info={.sType=VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
    VkFenceCreateInfo fence_info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO,
                                 .flags=VK_FENCE_CREATE_SIGNALED_BIT};
    FILE *csv=NULL;
    int status=0;
    unsigned feedback=0,scheduled=0;
    for(uint32_t k=0;k<image_count;k++) {
        if(vkCreateSemaphore(o->device,&sem_info,NULL,&acquired[k])!=VK_SUCCESS ||
           vkCreateSemaphore(o->device,&sem_info,NULL,&ready[k])!=VK_SUCCESS ||
           vkCreateFence(o->device,&fence_info,NULL,&fences[k])!=VK_SUCCESS) {
            status=8;goto cleanup;
        }
    }
    csv=fopen(o->feedback_path,"w");
    if(!csv){status=9;goto cleanup;}
    fputs("present_id,target_time_ns,first_pixel_out_ns,queue_operations_end_ns,time_domain,time_domain_id\n",csv);
    for(uint32_t frame=0;frame<o->frame_count;frame++) {
        const uint32_t slot=frame%image_count;
        if(vkWaitForFences(o->device,1,&fences[slot],VK_TRUE,UINT64_MAX)!=VK_SUCCESS) {
            status=10;break;
        }
        uint32_t image=0;
        rc=vkAcquireNextImageKHR(o->device,o->swapchain,UINT64_MAX,
                                 acquired[slot],VK_NULL_HANDLE,&image);
        if((rc!=VK_SUCCESS && rc!=VK_SUBOPTIMAL_KHR) || image>=image_count) {
            fprintf(stderr,"ZEITOP_ACQUIRE_FAILED rc=%d\n",rc);
            status=11;break;
        }
        /* CPU-side rendering workload AFTER acquisition, BEFORE submission. */
        uint64_t cpu_ns=zp_workload_ns(pattern,frame,o->cpu_work_seed);
        zp_busy_work(cpu_ns);
        total_cpu_work_ns+=cpu_ns;
        if(vkResetCommandBuffer(commands[slot],0)!=VK_SUCCESS) {status=12;break;}
        VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        if(vkBeginCommandBuffer(commands[slot],&begin)!=VK_SUCCESS) {status=13;break;}
        VkImageSubresourceRange color={
            .aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.baseMipLevel=0,
            .levelCount=1,.baseArrayLayer=0,.layerCount=1
        };
        VkImageMemoryBarrier to_transfer={
            .sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .srcAccessMask=0,.dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,
            .oldLayout=VK_IMAGE_LAYOUT_UNDEFINED,
            .newLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .image=images[image],.subresourceRange=color
        };
        vkCmdPipelineBarrier(commands[slot],
                             VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                             VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&to_transfer);
        VkClearColorValue fill={.float32={(float)(frame%2),0.15f,0.45f,1.0f}};
        vkCmdClearColorImage(commands[slot],images[image],
                             VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,&fill,1,&color);
        VkImageMemoryBarrier to_present={
            .sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,.dstAccessMask=0,
            .oldLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            .newLayout=VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
            .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .image=images[image],.subresourceRange=color
        };
        vkCmdPipelineBarrier(commands[slot],
                             VK_PIPELINE_STAGE_TRANSFER_BIT,
                             VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,
                             0,0,NULL,0,NULL,1,&to_present);
        if(vkEndCommandBuffer(commands[slot])!=VK_SUCCESS) {status=14;break;}
        if(vkResetFences(o->device,1,&fences[slot])!=VK_SUCCESS) {status=15;break;}
        VkPipelineStageFlags wait_stage=VK_PIPELINE_STAGE_TRANSFER_BIT;
        VkSubmitInfo submit={
            .sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .waitSemaphoreCount=1,.pWaitSemaphores=&acquired[slot],
            .pWaitDstStageMask=&wait_stage,
            .commandBufferCount=1,.pCommandBuffers=&commands[slot],
            .signalSemaphoreCount=1,.pSignalSemaphores=&ready[image]
        };
        rc=vkQueueSubmit(o->queue,1,&submit,fences[slot]);
        if(rc!=VK_SUCCESS){status=16;break;}

        VkPresentTimingInfoEXT timing={
            .sType=VK_STRUCTURE_TYPE_PRESENT_TIMING_INFO_EXT,
            .targetTime=o->schedule_enabled ? base+(uint64_t)frame*period : 0,
            .flags=o->nearest_refresh ? VK_PRESENT_TIMING_INFO_PRESENT_AT_NEAREST_REFRESH_CYCLE_BIT_EXT : 0,
            .timeDomainId=o->stage_local_domain_id,
            .presentStageQueries=VK_PRESENT_STAGE_QUEUE_OPERATIONS_END_BIT_EXT |
                                 VK_PRESENT_STAGE_IMAGE_FIRST_PIXEL_OUT_BIT_EXT,
            .targetTimeDomainPresentStage=VK_PRESENT_STAGE_IMAGE_FIRST_PIXEL_OUT_BIT_EXT
        };
        VkPresentTimingsInfoEXT timings={
            .sType=VK_STRUCTURE_TYPE_PRESENT_TIMINGS_INFO_EXT,
            .swapchainCount=1,.pTimingInfos=&timing
        };
        VkPresentInfoKHR info={
            .sType=VK_STRUCTURE_TYPE_PRESENT_INFO_KHR,
            .pNext=&timings,
            .waitSemaphoreCount=1,.pWaitSemaphores=&ready[image],
            .swapchainCount=1,.pSwapchains=&o->swapchain,
            .pImageIndices=&image
        };
        rc=vkQueuePresentKHR(o->queue,&info);
        if(rc!=VK_SUCCESS && rc!=VK_SUBOPTIMAL_KHR) {
            fprintf(stderr,"ZEITOP_TIMED_PRESENT_FAILED frame=%u rc=%d\n",frame,rc);
            status=17;break;
        }
        scheduled++;
        feedback+=drain_feedback(o,csv);
    }

    if(vkDeviceWaitIdle(o->device)!=VK_SUCCESS && status==0)status=18;
    for(unsigned attempt=0;attempt<70 && feedback<scheduled;attempt++) {
        feedback+=drain_feedback(o,csv);
        if(feedback>=scheduled)break;
        sleep_ns(10000000ULL);
    }
    printf("ZEITOP_CPU_WORK_NS_TOTAL=%" PRIu64 "\n",total_cpu_work_ns);
    printf("ZEITOP_PRESENTS_SUBMITTED=%u\n",scheduled);
    printf("ZEITOP_TARGETING_ACTIVE=%d\n",o->schedule_enabled);
    printf("ZEITOP_PRESENT_FEEDBACK_COUNT=%u\n",feedback);
    printf("ZEITOP_HOST_DURATION_NS=%" PRIu64 "\n",clock_monotonic_ns()-start_cpu);
cleanup:
    if(csv)fclose(csv);
    for(uint32_t k=0;k<image_count;k++) {
        if(fences[k])vkDestroyFence(o->device,fences[k],NULL);
        if(ready[k])vkDestroySemaphore(o->device,ready[k],NULL);
        if(acquired[k])vkDestroySemaphore(o->device,acquired[k],NULL);
    }
    vkDestroyCommandPool(o->device,pool,NULL);
    return status;
}
