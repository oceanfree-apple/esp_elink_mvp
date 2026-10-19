#include "cloud.h"
#include "wifi_station.h"
#include "cloud_config.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdatomic.h>
#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_rom_crc.h"
#include "esp_sntp.h"
#include "esp_timer.h"
#include "mqtt_client.h"
#include "mbedtls/sha256.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

extern const char cloud_ca_start[] asm("_binary_cloud_ca_pem_start");
typedef struct {char id[33], image[33], sha[65]; int64_t expires, issued;} command_t;
typedef struct {char id[33], sha[65], state[16], error[64]; int64_t issued;} record_t;
static record_t current;
static nvs_handle_t store;
static QueueHandle_t commands;
static esp_mqtt_client_handle_t client;
static atomic_bool connected;
static atomic_int phase, last_error;
static char boot_id[24];
static char event_topic[128], command_topic[128], presence_topic[128];

void elink_cloud_status(char *out,size_t size) {
    static const char *names[]={"waiting_wifi","waiting_time","connecting","connected","offline","storage_error"};
    snprintf(out,size,"cloud=%s cloud_error=%d",names[atomic_load(&phase)],atomic_load(&last_error));
}

static bool save_record(void) {
    return nvs_set_blob(store,"last_job",&current,sizeof(current))==ESP_OK && nvs_commit(store)==ESP_OK;
}
static void report(void) {
    if(!connected) return;
    cJSON *body=cJSON_CreateObject();
    cJSON_AddStringToObject(body,"boot_id",boot_id);
    cJSON_AddStringToObject(body,"job_id",current.id);
    cJSON_AddStringToObject(body,"sha256",current.sha);
    const char *display=elink_display_state();
    const char *state=current.state[0] ? current.state : "idle";
    // UART activity also prevents a concurrent cloud task.
    if(!strcmp(display,"receiving") || (!strcmp(display,"refreshing") && strcmp(state,"refreshing"))) state=display;
    cJSON_AddStringToObject(body,"state",state);
    cJSON_AddStringToObject(body,"error",current.error);
    char *text=cJSON_PrintUnformatted(body);
    if(text) {esp_mqtt_client_enqueue(client,event_topic,text,0,1,0,true); free(text);}
    cJSON_Delete(body);
}
static bool field(cJSON *body,const char *key,char *out,size_t n) {
    cJSON *v=cJSON_GetObjectItemCaseSensitive(body,key);
    if(!cJSON_IsString(v) || strlen(v->valuestring)!=n-1) return false;
    for(size_t i=0;i<n-1;i++) {
        char c=v->valuestring[i];
        if(!((c>='0'&&c<='9')||(c>='a'&&c<='f'))) return false;
    }
    memcpy(out,v->valuestring,n); return true;
}
static void mqtt_event(void *args,esp_event_base_t base,int32_t id,void *data) {
    esp_mqtt_event_handle_t event=data;
    if(id==MQTT_EVENT_CONNECTED) {
        connected=true;
        phase=3; last_error=0;
        esp_mqtt_client_subscribe(client,command_topic,1);
        esp_mqtt_client_enqueue(client,presence_topic,"{\"online\":true}",0,1,1,true);
        // Wake the worker for an immediate heartbeat without sharing record state.
        command_t wake={0}; xQueueSend(commands,&wake,0);
    } else if(id==MQTT_EVENT_DISCONNECTED) {connected=false; phase=4;}
    else if(id==MQTT_EVENT_ERROR) {
        if(event->error_handle) last_error=event->error_handle->esp_tls_last_esp_err;
    }
    else if(id==MQTT_EVENT_DATA) {
        static char payload[1024];
        static int assembled;
        if(event->current_data_offset==0) {
            assembled=0;
            if(event->topic_len!=(int)strlen(command_topic) || strncmp(event->topic,command_topic,event->topic_len)) return;
        }
        if(event->total_data_len<=0 || event->total_data_len>=(int)sizeof(payload) || event->current_data_offset!=assembled || event->data_len<0 || assembled+event->data_len>=(int)sizeof(payload)) return;
        memcpy(payload+assembled,event->data,event->data_len); assembled+=event->data_len;
        if(assembled!=event->total_data_len) return;
        payload[assembled]=0;
        cJSON *body=cJSON_Parse(payload); command_t cmd={0};
        cJSON *expiry=cJSON_GetObjectItemCaseSensitive(body,"expires_at");
        cJSON *size=cJSON_GetObjectItemCaseSensitive(body,"size");
        cJSON *issued=cJSON_GetObjectItemCaseSensitive(body,"issued_at_us");
        if(body && cJSON_IsNumber(expiry) && cJSON_IsNumber(issued) && cJSON_IsNumber(size) && size->valueint==192000 &&
           field(body,"job_id",cmd.id,sizeof(cmd.id)) && field(body,"image_id",cmd.image,sizeof(cmd.image)) && field(body,"sha256",cmd.sha,sizeof(cmd.sha))) {
            cmd.expires=(int64_t)expiry->valuedouble;
            cmd.issued=(int64_t)issued->valuedouble;
            xQueueSend(commands,&cmd,0);
        }
        cJSON_Delete(body);
    }
}

static bool download(const command_t *cmd,int64_t deadline) {
    char url[256],auth[192];
    snprintf(url,sizeof(url),"%s/v1/device/images/%s",CLOUD_BASE_URL,cmd->image);
    snprintf(auth,sizeof(auth),"Bearer %s",CLOUD_DEVICE_TOKEN);
    esp_http_client_config_t cfg={.url=url,.cert_pem=cloud_ca_start,.common_name=CLOUD_TLS_NAME,.timeout_ms=5000,
        .disable_auto_redirect=true,.buffer_size=4096};
    esp_http_client_handle_t http=esp_http_client_init(&cfg);
    if(!http) return false;
    esp_http_client_set_header(http,"Authorization",auth);
    esp_err_t result=esp_http_client_open(http,0);
    int64_t length=result==ESP_OK ? esp_http_client_fetch_headers(http) : -1;
    bool ok=result==ESP_OK && length==192000 && esp_http_client_get_status_code(http)==200;
    size_t received=0; uint8_t *image=elink_cloud_buffer();
    while(ok && received<192000) {
        if(esp_timer_get_time()>deadline) {ok=false;break;}
        int n=esp_http_client_read(http,(char*)image+received,(192000-received)>4096?4096:(192000-received));
        if(n<=0) {ok=false; break;}
        received+=n;
    }
    esp_http_client_close(http); esp_http_client_cleanup(http);
    if(!ok || received!=192000) return false;
    uint8_t hash[32]; char hex[65];
    if(mbedtls_sha256(image,192000,hash,0)!=0) return false;
    for(int i=0;i<32;i++) snprintf(hex+i*2,3,"%02x",hash[i]);
    if(strcmp(hex,cmd->sha)) return false;
    for(size_t i=0;i<192000;i++) {
        uint8_t a=image[i]>>4,b=image[i]&15;
        if(a>6 || b>6 || a==4 || b==4) return false;
    }
    return true;
}
static void fail(const char *error) {
    strlcpy(current.state,"failed",sizeof(current.state));
    strlcpy(current.error,error,sizeof(current.error)); save_record(); elink_cloud_fail(); report();
}
static void run(const command_t *cmd) {
    if(!cmd->id[0]) {report();return;}
    if(!strcmp(cmd->id,current.id)) {report();return;}
    if(cmd->issued<=current.issued) return;
    if(cmd->expires<time(NULL)) return;
    if(!elink_cloud_acquire()) {
        // Do not overwrite the record for a task which may still be running.
        return;
    }
    memset(&current,0,sizeof(current));
    current.issued=cmd->issued;
    strlcpy(current.id,cmd->id,sizeof(current.id)); strlcpy(current.sha,cmd->sha,sizeof(current.sha));
    strlcpy(current.state,"downloading",sizeof(current.state));
    if(!save_record()) {fail("nvs_write_failed");return;}
    report();
    bool ok=false; int64_t deadline=esp_timer_get_time()+45000000;
    for(int attempt=0;attempt<3 && !ok;attempt++) {
        if(esp_timer_get_time()>deadline) break;
        ok=download(cmd,deadline);
        if(!ok) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    if(!ok) {fail("download_or_integrity_failed");return;}
    strlcpy(current.state,"refreshing",sizeof(current.state));
    if(!save_record()) {fail("nvs_write_failed");return;}
    report();
    elink_cloud_commit(esp_rom_crc32_le(0,elink_cloud_buffer(),192000));
    unsigned polls=0;
    while(!strcmp(elink_display_state(),"refreshing")) {
        vTaskDelay(pdMS_TO_TICKS(500));
        if(++polls%20==0) report();
    }
    if(strcmp(elink_display_state(),"done")) {fail("panel_refresh_failed");return;}
    strlcpy(current.state,"succeeded",sizeof(current.state));
    if(!save_record()) {
        strlcpy(current.state,"uncertain",sizeof(current.state));
        strlcpy(current.error,"result_persistence_failed",sizeof(current.error));
    }
    report();
    elink_cloud_release();
}
static void worker(void *arg) {
    char wifi[128];
    do {vTaskDelay(pdMS_TO_TICKS(1000)); elink_wifi_status(wifi,sizeof(wifi));} while(!strstr(wifi,"wifi=connected"));
    if(nvs_open("elink_cloud",NVS_READWRITE,&store)!=ESP_OK) {phase=5;vTaskDelete(NULL);return;}
    size_t size=sizeof(current);
    if(nvs_get_blob(store,"last_job",&current,&size)!=ESP_OK || size!=sizeof(current)) memset(&current,0,sizeof(current));
    if(!strcmp(current.state,"downloading") || !strcmp(current.state,"refreshing")) {
        strlcpy(current.state,"uncertain",sizeof(current.state));
        strlcpy(current.error,"device_restarted",sizeof(current.error));
        if(!save_record()) {vTaskDelete(NULL);return;}
    }
    phase=1;
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0,"ntp.tencent.com");
    esp_sntp_setservername(1,"ntp.aliyun.com");
    esp_sntp_setservername(2,"pool.ntp.org"); esp_sntp_init();
    while(time(NULL)<1735689600) vTaskDelay(pdMS_TO_TICKS(1000));
    snprintf(boot_id,sizeof(boot_id),"%lld",(long long)esp_timer_get_time());
    snprintf(event_topic,sizeof(event_topic),"elink/v1/%s/events",CLOUD_DEVICE_ID);
    snprintf(command_topic,sizeof(command_topic),"elink/v1/%s/command",CLOUD_DEVICE_ID);
    snprintf(presence_topic,sizeof(presence_topic),"elink/v1/%s/presence",CLOUD_DEVICE_ID);
    esp_mqtt_client_config_t cfg={
        .broker.address.uri=CLOUD_MQTT_URI,
        .broker.verification.certificate=cloud_ca_start,
        .broker.verification.common_name=CLOUD_TLS_NAME,
        .credentials.username=CLOUD_DEVICE_ID,.credentials.client_id=CLOUD_DEVICE_ID,
        .credentials.authentication.password=CLOUD_MQTT_PASSWORD,
        .session.keepalive=30,.session.disable_clean_session=false,
        .session.last_will={.topic=presence_topic,.msg="{\"online\":false}",.qos=1,.retain=true},
        .network.reconnect_timeout_ms=3000,.buffer.size=1024};
    phase=2;
    client=esp_mqtt_client_init(&cfg);
    if(!client) {vTaskDelete(NULL);return;}
    esp_mqtt_client_register_event(client,ESP_EVENT_ANY_ID,mqtt_event,NULL);
    esp_mqtt_client_start(client);
    command_t cmd;
    for(;;) {
        if(xQueueReceive(commands,&cmd,pdMS_TO_TICKS(10000))) run(&cmd);
        else report();
    }
}
void elink_cloud_start(void) {
    commands=xQueueCreate(4,sizeof(command_t));
    if(!commands) abort();
    if(xTaskCreate(worker,"elink_cloud",12288,NULL,4,NULL)!=pdPASS) abort();
}
