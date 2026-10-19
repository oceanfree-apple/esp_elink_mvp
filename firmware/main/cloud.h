#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
void elink_cloud_start(void);
void elink_cloud_status(char *out,size_t size);
bool elink_cloud_acquire(void);
uint8_t *elink_cloud_buffer(void);
void elink_cloud_commit(uint32_t crc);
void elink_cloud_release(void);
void elink_cloud_fail(void);
const char *elink_display_state(void);
