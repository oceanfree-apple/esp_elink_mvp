#pragma once
#include <stddef.h>
void elink_wifi_start(void);
void elink_wifi_status(char *output, size_t size);
void elink_wifi_scan_result(unsigned index, char *output, size_t size);
