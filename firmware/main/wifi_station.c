#include "wifi_station.h"
#include <stdio.h>
#include <string.h>
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#if __has_include("wifi_credentials.h")
#include "wifi_credentials.h"
#endif

#ifdef WIFI_STA_SSID
static portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
static enum {STARTING, CONNECTING, CONNECTED, DISCONNECTED, FAILED} link_state=STARTING;
static esp_ip4_addr_t address;
static int last_reason;
static wifi_ap_record_t scan_records[32];
static uint16_t scan_count;
static void event_handler(void *arg, esp_event_base_t base, int32_t event, void *data) {
    if(base==IP_EVENT && event==IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *got=data;
        portENTER_CRITICAL(&mux);
        address=got->ip_info.ip; link_state=CONNECTED; last_reason=0;
        portEXIT_CRITICAL(&mux);
    } else if(base==WIFI_EVENT && event==WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *lost=data;
        portENTER_CRITICAL(&mux);
        address.addr=0; link_state=DISCONNECTED; last_reason=lost->reason;
        portEXIT_CRITICAL(&mux);
        esp_wifi_connect();
    }
}
static bool setup(void) {
    esp_err_t err=nvs_flash_init();
    // Preserve existing NVS data on errors rather than erasing another project's settings.
    if(err!=ESP_OK) return false;
    if(esp_netif_init()!=ESP_OK) return false;
    if(esp_event_loop_create_default()!=ESP_OK) return false;
    if(!esp_netif_create_default_wifi_sta()) return false;
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    if(esp_wifi_init(&init)!=ESP_OK) return false;
    if(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,event_handler,NULL)!=ESP_OK) return false;
    if(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,event_handler,NULL)!=ESP_OK) return false;
    if(esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK) return false;
    if(esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK) return false;
    wifi_config_t config={0};
    _Static_assert(sizeof(WIFI_STA_SSID)-1<=32,"SSID too long");
    _Static_assert(sizeof(WIFI_STA_PASSWORD)-1<=64,"Password too long");
    memcpy(config.sta.ssid,WIFI_STA_SSID,sizeof(WIFI_STA_SSID)-1);
    memcpy(config.sta.password,WIFI_STA_PASSWORD,sizeof(WIFI_STA_PASSWORD)-1);
    config.sta.pmf_cfg.capable=true;
    config.sta.sae_pwe_h2e=WPA3_SAE_PWE_BOTH;
    if(esp_wifi_set_config(WIFI_IF_STA,&config)!=ESP_OK) return false;
    if(esp_wifi_start()!=ESP_OK) return false;
    // Cache a scan for diagnostics before associating, without blocking UART commands.
    if(esp_wifi_scan_start(NULL,true)==ESP_OK) {
        uint16_t count=32;
        static wifi_ap_record_t found[32];
        if(esp_wifi_scan_get_ap_records(&count,found)==ESP_OK) {
            portENTER_CRITICAL(&mux);
            memcpy(scan_records,found,count*sizeof(found[0])); scan_count=count;
            portEXIT_CRITICAL(&mux);
        }
    }
    portENTER_CRITICAL(&mux); link_state=CONNECTING; portEXIT_CRITICAL(&mux);
    return esp_wifi_connect()==ESP_OK;
}
static void worker(void *arg) {
    if(!setup()) {portENTER_CRITICAL(&mux); link_state=FAILED; portEXIT_CRITICAL(&mux);}
    vTaskDelete(NULL);
}
void elink_wifi_start(void) {
    if(xTaskCreate(worker,"wifi_setup",6144,NULL,4,NULL)!=pdPASS) {
        portENTER_CRITICAL(&mux); link_state=FAILED; portEXIT_CRITICAL(&mux);
    }
}
void elink_wifi_status(char *output,size_t size) {
    portENTER_CRITICAL(&mux);
    int state=link_state, reason=last_reason; esp_ip4_addr_t ip=address;
    portEXIT_CRITICAL(&mux);
    static const char *names[]={"starting","connecting","connected","disconnected","error"};
    wifi_ap_record_t ap; int rssi=0;
    if(state==CONNECTED && esp_wifi_sta_get_ap_info(&ap)==ESP_OK) rssi=ap.rssi;
    snprintf(output,size,"wifi=%s ip=" IPSTR " rssi=%d reason=%d",names[state],IP2STR(&ip),rssi,reason);
}
void elink_wifi_scan_result(unsigned index,char *output,size_t size) {
    wifi_ap_record_t ap={0};
    portENTER_CRITICAL(&mux);
    unsigned count=scan_count;
    if(index<count) ap=scan_records[index];
    portEXIT_CRITICAL(&mux);
    if(index>=count) {snprintf(output,size,"count=%u end=1",count); return;}
    char hex[65]; size_t len=strnlen((char*)ap.ssid,32);
    for(size_t i=0;i<len;i++) snprintf(hex+i*2,3,"%02x",ap.ssid[i]);
    hex[len*2]=0;
    snprintf(output,size,"count=%u ssid_hex=%s rssi=%d channel=%u auth=%d",count,hex,ap.rssi,ap.primary,ap.authmode);
}
#else
void elink_wifi_start(void) {}
void elink_wifi_status(char *output,size_t size) {snprintf(output,size,"wifi=disabled ip=0.0.0.0 rssi=0 reason=0");}
void elink_wifi_scan_result(unsigned index,char *output,size_t size) {snprintf(output,size,"count=0 end=1");}
#endif
