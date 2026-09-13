#ifndef __SPI_H__
#define __SPI_H__

#include <stdint.h>

typedef struct SPI_X {
	uint32_t CR1;       // 0x00
	uint32_t CR2;       // 0x04
	uint32_t SR;        // 0x08
	uint32_t DR;        // 0x0C
	uint32_t CRCPR;     // 0x10
	uint32_t RXCRCR;    // 0x14
	uint32_t TXCRCR;    // 0x18
    uint32_t I2SCFGR;   // 0x1C
    uint32_t I2SPR;     // 0x20
} SPI_x;

#define SPI1_BASE 0x40013000
#define SPI2_BASE 0x40003800
#define SPI3_BASE 0x40003C00

#define SPI1 ((SPI_x *)SPI1_BASE)
#define SPI2 ((SPI_x *)SPI2_BASE)
#define SPI3 ((SPI_x *)SPI3_BASE)

// SPI alternate function
#define SPI1_PIN_AF (5)
#define SPI2_PIN_AF (5)
#define SPI3_PIN_AF (6)

// SPI mode
#define SPI_FULL_DUP_MASTER   0
#define SPI_FULL_DUP_SLAVE    1
#define SPI_HALF_DUP_MASTER   2
#define SPI_HALF_DUP_SLAVE    3
#define SPI_RECV_ONLY_MASTER  4
#define SPI_RECV_ONLY_SLAVE   5
#define SPI_TRANS_ONLY_MASTER 6

// SPI register setting
#define SPI_CR1_MASTER     (1 << 2)
#define SPI_CR1_SPI_EN     (1 << 6)

#define SPI_CR2_SSOE       (1 << 2)
#define SPI_CR2_ERRI_EN    (1 << 5)
#define SPI_CR2_RXNEI_EN   (1 << 6)
#define SPI_CR2_TXEI_EN    (1 << 7)

#define SPI_SR_RX_NOTEMPTY (1 << 0)
#define SPI_SR_TX_EMPTY    (1 << 1)
#define SPI_SR_OVR		   (1 << 6)	
#define SPI_SR_BSY         (1 << 7)

/* SPI interface prototypes */
void spi_init(SPI_x *spi, uint8_t mode, uint8_t size, uint8_t use_it);
void spi_write(SPI_x *spi, uint16_t data);
void spi_read(SPI_x *spi, uint16_t *data);
void spi_deinit(SPI_x *spi);
void spi_regist_rx_callback(void (*func)(SPI_x *, uint8_t));
void spi_regist_ovr_callback(void (*func)(SPI_x *, uint8_t));

#endif