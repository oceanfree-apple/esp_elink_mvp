#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GDEP073E01_WIDTH 800
#define GDEP073E01_HEIGHT 480
#define GDEP073E01_PACKED_IMAGE_SIZE (GDEP073E01_WIDTH * GDEP073E01_HEIGHT / 2)

bool gdep073e01_init(void);
bool gdep073e01_begin_frame(void);
bool gdep073e01_feed_frame(const uint8_t *data, size_t len);
bool gdep073e01_end_frame(void);
bool gdep073e01_display_packed_image(const uint8_t *data, size_t len);
void gdep073e01_sleep(void);

#ifdef __cplusplus
}
#endif
