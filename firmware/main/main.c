#include <stdio.h>
#include <string.h>
#include "driver/uart.h"
#include "esp_heap_caps.h"
#include "esp_rom_crc.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "epd_gdep073e01.h"
#include "wifi_station.h"
#include "cloud.h"

#define FRAME_SIZE GDEP073E01_PACKED_IMAGE_SIZE
#define MAX_PAYLOAD 4100
static uint8_t *image;
static size_t received;
static uint32_t expected_crc, displayed_crc;
static bool uploading;
static bool cloud_owned;
static const char *state = "idle";
static SemaphoreHandle_t lock;
static TaskHandle_t display_task;
static int64_t last_data;

bool elink_cloud_acquire(void) {
    xSemaphoreTake(lock,portMAX_DELAY);
    if(uploading && esp_timer_get_time()-last_data>30000000) {uploading=false; state="idle";}
    bool ok=!uploading && !cloud_owned && strcmp(state,"refreshing") && strcmp(state,"downloading");
    if(ok) {cloud_owned=true; state="downloading"; received=0;}
    xSemaphoreGive(lock);
    return ok;
}
uint8_t *elink_cloud_buffer(void) {return image;}
void elink_cloud_commit(uint32_t crc) {
    xSemaphoreTake(lock,portMAX_DELAY);
    expected_crc=crc; received=FRAME_SIZE; state="refreshing";
    xTaskNotifyGive(display_task);
    xSemaphoreGive(lock);
}
void elink_cloud_fail(void) {
    xSemaphoreTake(lock,portMAX_DELAY); cloud_owned=false; state="error"; xSemaphoreGive(lock);
}
void elink_cloud_release(void) {
    xSemaphoreTake(lock,portMAX_DELAY); cloud_owned=false; xSemaphoreGive(lock);
}
const char *elink_display_state(void) {
    xSemaphoreTake(lock,portMAX_DELAY); const char *s=state; xSemaphoreGive(lock); return s;
}

static uint32_t read32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static bool read_exact(uint8_t *p, size_t n) {
    while(n) {
        int r=uart_read_bytes(UART_NUM_0,p,n,pdMS_TO_TICKS(1500));
        if(r<=0) return false;
        p+=r; n-=r;
    }
    return true;
}
static void display_worker(void *arg) {
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        bool ok=gdep073e01_init();
        if(ok) ok=gdep073e01_display_packed_image(image, FRAME_SIZE);
        gdep073e01_sleep();
        xSemaphoreTake(lock,portMAX_DELAY);
        state=ok ? "done" : "error";
        if(ok) displayed_crc=expected_crc;
        xSemaphoreGive(lock);
    }
}
void app_main(void) {
    const uart_config_t config={.baud_rate=115200,.data_bits=UART_DATA_8_BITS,
        .parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,
        .flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,16384,0,0,NULL,0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0,&config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0,43,44,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));
    image=heap_caps_malloc(FRAME_SIZE,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    lock=xSemaphoreCreateMutex();
    if(!image || !lock) abort();
    xTaskCreate(display_worker,"epd_display",6144,NULL,5,&display_task);
    elink_wifi_start();
    elink_cloud_start();
    static uint8_t header[13], payload[MAX_PAYLOAD];
    char response[400], cached[400]="";
    uint32_t cached_seq=0, cached_crc=0;
    bool have_cached=false;
    unsigned matched=0;
    for (;;) {
        uint8_t c;
        if(!read_exact(&c,1)) continue;
        const char *magic="EPD1";
        if(c!=(uint8_t)magic[matched]) { matched=(c=='E'); continue; }
        if(++matched<4) continue;
        matched=0;
        if(!read_exact(header,sizeof(header))) continue;
        uint8_t cmd=header[0];
        uint32_t seq=read32(header+1), len=read32(header+5), crc=read32(header+9);
        if(len>MAX_PAYLOAD) { uart_flush_input(UART_NUM_0); continue; }
        if(!read_exact(payload,len)) continue;
        uint32_t actual=esp_rom_crc32_le(0,header,9);
        actual=esp_rom_crc32_le(actual,payload,len);
        if(actual!=crc) {
            snprintf(response,sizeof(response),"@EPD %lu ERR crc\n",(unsigned long)seq);
            uart_write_bytes(UART_NUM_0,response,strlen(response)); continue;
        }
        if(have_cached && seq==cached_seq && crc==cached_crc) {
            uart_write_bytes(UART_NUM_0,cached,strlen(cached)); continue;
        }
        xSemaphoreTake(lock,portMAX_DELAY);
        const char *err=NULL;
        if(uploading && esp_timer_get_time()-last_data>30000000) { uploading=false; state="idle"; }
        if(cmd==1 && len==0) {
            char wifi[96];
            char cloud[96];
            elink_wifi_status(wifi,sizeof(wifi));
            elink_cloud_status(cloud,sizeof(cloud));
            snprintf(response,sizeof(response),"@EPD %lu OK state=%s received=%u crc=%08lx version=1 %s %s\n",
                (unsigned long)seq,state,(unsigned)received,(unsigned long)displayed_crc,wifi,cloud);
        } else if(cmd==5 && len==4) {
            char scan[150];
            elink_wifi_scan_result(read32(payload),scan,sizeof(scan));
            snprintf(response,sizeof(response),"@EPD %lu OK %s\n",(unsigned long)seq,scan);
        } else {
            if(cloud_owned || strcmp(state,"refreshing")==0 || strcmp(state,"downloading")==0) err="busy";
            else if(cmd==2 && len==8) {
                if(read32(payload)!=FRAME_SIZE) err="size";
                else {expected_crc=read32(payload+4); received=0; uploading=true; state="receiving"; last_data=esp_timer_get_time();}
            } else if(cmd==3 && len>4 && uploading) {
                uint32_t offset=read32(payload);
                if(offset!=received || len-4>FRAME_SIZE-received) err="offset";
                else {memcpy(image+received,payload+4,len-4); received+=len-4; last_data=esp_timer_get_time();}
            } else if(cmd==4 && len==0 && uploading) {
                if(received!=FRAME_SIZE) err="incomplete";
                else if(esp_rom_crc32_le(0,image,FRAME_SIZE)!=expected_crc) err="image_crc";
                else {uploading=false; state="refreshing"; xTaskNotifyGive(display_task);}
            } else err="command";
            snprintf(response,sizeof(response),"@EPD %lu %s %s\n",(unsigned long)seq,err?"ERR":"OK",err?err:state);
        }
        xSemaphoreGive(lock);
        strcpy(cached,response); cached_seq=seq; cached_crc=crc; have_cached=true;
        uart_write_bytes(UART_NUM_0,response,strlen(response));
    }
}
