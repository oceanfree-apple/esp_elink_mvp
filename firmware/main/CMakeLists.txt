idf_component_register(SRCS "main.c" "cloud.c" "wifi_station.c" "epd_gdep073e01.c"
    INCLUDE_DIRS "." EMBED_TXTFILES "cloud_ca.pem"
    REQUIRES esp_driver_uart esp_driver_gpio esp_driver_spi esp_timer esp_wifi
    esp_netif nvs_flash mqtt esp_http_client esp-tls mbedtls json lwip)
