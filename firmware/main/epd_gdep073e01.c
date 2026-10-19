#include "epd_gdep073e01.h"

#include <string.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

static const char *TAG = "gdep073e01";

enum {
    CMD_PSR = 0x00,
    CMD_PWRR = 0x01,
    CMD_POF = 0x02,
    CMD_POFS = 0x03,
    CMD_PON = 0x04,
    CMD_BTST1 = 0x05,
    CMD_BTST2 = 0x06,
    CMD_DTM = 0x10,
    CMD_DRF = 0x12,
    CMD_PLL = 0x30,
    CMD_CDI = 0x50,
    CMD_TCON = 0x60,
    CMD_TRES = 0x61,
    CMD_T_VDCS = 0x84,
    CMD_PWS = 0xE3,
    CMD_CMDH = 0xAA,
};

static spi_device_handle_t s_spi;
static bool s_initialized;

static bool panel_ready_level(void);

static inline int pin_mosi(void) { return CONFIG_GDEP_PIN_MOSI; }
static inline int pin_sclk(void) { return CONFIG_GDEP_PIN_SCLK; }
static inline int pin_cs(void) { return CONFIG_GDEP_PIN_CS; }
static inline int pin_dc(void) { return CONFIG_GDEP_PIN_DC; }
static inline int pin_rst(void) { return CONFIG_GDEP_PIN_RST; }
static inline int pin_busy(void) { return CONFIG_GDEP_PIN_BUSY; }

static bool panel_ready_level(void)
{
#if CONFIG_GDEP_BUSY_LEVEL_READY
    return true;
#else
    return false;
#endif
}

static esp_err_t spi_send_bytes(const uint8_t *data, size_t len)
{
    while (len > 0) {
        size_t chunk = len > 4096 ? 4096 : len;
        spi_transaction_t t = {
            .length = chunk * 8,
            .tx_buffer = data,
        };
        ESP_RETURN_ON_ERROR(spi_device_polling_transmit(s_spi, &t), TAG, "spi transmit failed");
        data += chunk;
        len -= chunk;
    }
    return ESP_OK;
}

static esp_err_t epd_write_command(uint8_t cmd)
{
    gpio_set_level(pin_dc(), 0);
    return spi_send_bytes(&cmd, 1);
}

static esp_err_t epd_write_data(const uint8_t *data, size_t len)
{
    gpio_set_level(pin_dc(), 1);
    return spi_send_bytes(data, len);
}

static esp_err_t epd_write_data_byte(uint8_t value)
{
    return epd_write_data(&value, 1);
}

static void epd_reset(void)
{
    gpio_set_level(pin_rst(), 0);
    vTaskDelay(pdMS_TO_TICKS(50));
    gpio_set_level(pin_rst(), 1);
    vTaskDelay(pdMS_TO_TICKS(200));
}

static esp_err_t epd_wait_ready(TickType_t timeout_ticks)
{
    const int expected = panel_ready_level() ? 1 : 0;
    TickType_t start = xTaskGetTickCount();
    while (gpio_get_level(pin_busy()) != expected) {
        if ((xTaskGetTickCount() - start) > timeout_ticks) {
            ESP_LOGE(TAG, "wait ready timeout: expect=%d actual=%d elapsed=%lu ms",
                     expected, gpio_get_level(pin_busy()),
                     (unsigned long)((xTaskGetTickCount() - start) * portTICK_PERIOD_MS));
            return ESP_ERR_TIMEOUT;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return ESP_OK;
}

bool gdep073e01_init(void)
{
    esp_err_t ret;

    if (!s_initialized) {
        gpio_config_t out_conf = {
            .pin_bit_mask = (1ULL << pin_dc()) | (1ULL << pin_rst()),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_GOTO_ON_ERROR(gpio_config(&out_conf), fail, TAG, "gpio out config failed");

        gpio_config_t in_conf = {
            .pin_bit_mask = (1ULL << pin_busy()),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_GOTO_ON_ERROR(gpio_config(&in_conf), fail, TAG, "gpio in config failed");

        spi_bus_config_t buscfg = {
            .mosi_io_num = pin_mosi(),
            .miso_io_num = -1,
            .sclk_io_num = pin_sclk(),
            .quadwp_io_num = -1,
            .quadhd_io_num = -1,
            .max_transfer_sz = 4096,
        };
        ESP_GOTO_ON_ERROR(spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO), fail, TAG, "spi bus init failed");

        spi_device_interface_config_t devcfg = {
            .clock_speed_hz = CONFIG_GDEP_SPI_CLOCK_HZ,
            .mode = 0,
            .spics_io_num = pin_cs(),
            .queue_size = 1,
        };
        ESP_GOTO_ON_ERROR(spi_bus_add_device(SPI2_HOST, &devcfg, &s_spi), fail, TAG, "spi device add failed");

        gpio_set_level(pin_rst(), 1);
        gpio_set_level(pin_dc(), 1);
        s_initialized = true;
        ESP_LOGI(TAG,
                 "panel bus ready: MOSI=%d SCLK=%d CS=%d DC=%d RST=%d BUSY=%d SPI=%dHz",
                 pin_mosi(), pin_sclk(), pin_cs(), pin_dc(), pin_rst(), pin_busy(),
                 CONFIG_GDEP_SPI_CLOCK_HZ);
    }

    epd_reset();

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_CMDH), fail, TAG, "cmdh");
    {
        static const uint8_t data[] = {0x49, 0x55, 0x20, 0x08, 0x09, 0x18};
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "cmdh data");
    }

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_PWRR), fail, TAG, "pwrr");
    ESP_GOTO_ON_ERROR(epd_write_data_byte(0x3F), fail, TAG, "pwrr data");

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_PSR), fail, TAG, "psr");
    {
        static const uint8_t data[] = {0x5F, 0x69};
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "psr data");
    }

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_POFS), fail, TAG, "pofs");
    {
        static const uint8_t data[] = {0x00, 0x54, 0x00, 0x44};
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "pofs data");
    }

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_BTST1), fail, TAG, "btst1");
    {
        static const uint8_t data[] = {0x40, 0x1F, 0x1F, 0x2C};
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "btst1 data");
    }

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_BTST2), fail, TAG, "btst2");
    {
        static const uint8_t data[] = {0x6F, 0x1F, 0x17, 0x49};
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "btst2 data");
    }

    {
        static const uint8_t btst3_cmd = 0x08;
        static const uint8_t data[] = {0x6F, 0x1F, 0x1F, 0x22};
        ESP_GOTO_ON_ERROR(epd_write_command(btst3_cmd), fail, TAG, "btst3");
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "btst3 data");
    }

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_PLL), fail, TAG, "pll");
    ESP_GOTO_ON_ERROR(epd_write_data_byte(0x08), fail, TAG, "pll data");

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_CDI), fail, TAG, "cdi");
    ESP_GOTO_ON_ERROR(epd_write_data_byte(0x3F), fail, TAG, "cdi data");

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_TCON), fail, TAG, "tcon");
    {
        static const uint8_t data[] = {0x02, 0x00};
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "tcon data");
    }

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_TRES), fail, TAG, "tres");
    {
        static const uint8_t data[] = {0x03, 0x20, 0x01, 0xE0};
        ESP_GOTO_ON_ERROR(epd_write_data(data, sizeof(data)), fail, TAG, "tres data");
    }

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_T_VDCS), fail, TAG, "tvdcs");
    ESP_GOTO_ON_ERROR(epd_write_data_byte(0x01), fail, TAG, "tvdcs data");

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_PWS), fail, TAG, "pws");
    ESP_GOTO_ON_ERROR(epd_write_data_byte(0x2F), fail, TAG, "pws data");

    ESP_GOTO_ON_ERROR(epd_write_command(CMD_PON), fail, TAG, "pon");
    ret = epd_wait_ready(pdMS_TO_TICKS(10000));
#if CONFIG_GDEP_IGNORE_BUSY_TIMEOUT
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "ignoring BUSY timeout after PON for diagnostics");
    }
#else
    ESP_GOTO_ON_ERROR(ret, fail, TAG, "wait ready after pon");
#endif

    return true;

fail:
    ESP_LOGE(TAG, "panel init failed, final BUSY=%d", gpio_get_level(pin_busy()));
    return false;
}

bool gdep073e01_display_packed_image(const uint8_t *data, size_t len)
{
    if (len != GDEP073E01_PACKED_IMAGE_SIZE) {
        ESP_LOGE(TAG, "invalid packed image size: %u", (unsigned)len);
        return false;
    }

    uint8_t *chunk = heap_caps_malloc(4096, MALLOC_CAP_DMA | MALLOC_CAP_8BIT);
    if (!chunk) {
        ESP_LOGE(TAG, "failed to alloc DMA chunk");
        return false;
    }

    if (!gdep073e01_begin_frame()) {
        free(chunk);
        return false;
    }

    size_t offset = 0;
    while (offset < len) {
        size_t to_copy = len - offset > 4096 ? 4096 : len - offset;
        memcpy(chunk, data + offset, to_copy);
        if (!gdep073e01_feed_frame(chunk, to_copy)) {
            free(chunk);
            return false;
        }
        offset += to_copy;
    }

    free(chunk);
    return gdep073e01_end_frame();
}

bool gdep073e01_begin_frame(void)
{
    if (epd_write_command(CMD_DTM) != ESP_OK) {
        ESP_LOGE(TAG, "failed to write DTM");
        return false;
    }
    return true;
}

bool gdep073e01_feed_frame(const uint8_t *data, size_t len)
{
    if (epd_write_data(data, len) != ESP_OK) {
        ESP_LOGE(TAG, "failed sending image data chunk len=%u", (unsigned)len);
        return false;
    }
    return true;
}

bool gdep073e01_end_frame(void)
{
    esp_err_t ret;
    ESP_RETURN_ON_FALSE(epd_write_command(CMD_DRF) == ESP_OK, false, TAG, "drf command failed");
    ESP_RETURN_ON_FALSE(epd_write_data_byte(0x00) == ESP_OK, false, TAG, "drf data failed");
    ret = epd_wait_ready(pdMS_TO_TICKS(120000));
#if CONFIG_GDEP_IGNORE_BUSY_TIMEOUT
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "ignoring refresh BUSY timeout for diagnostics");
    }
#else
    ESP_RETURN_ON_FALSE(ret == ESP_OK, false, TAG, "wait ready after refresh failed");
#endif
    return true;
}

void gdep073e01_sleep(void)
{
    if (!s_initialized) {
        return;
    }

    if (epd_write_command(CMD_POF) == ESP_OK) {
        epd_wait_ready(pdMS_TO_TICKS(5000));
    }
}
