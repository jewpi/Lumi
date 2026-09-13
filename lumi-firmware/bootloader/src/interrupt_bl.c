#include <stdint.h>
#include "timer.h"
#include "spi.h"

volatile uint32_t ticks;

extern void (*spi_rx_callback)(SPI_x *spi, uint8_t data);
extern void (*spi_ovr_callback)(SPI_x *spi, uint8_t data);

void isr_systick(void)
{
	ticks++;
}

void isr_spi1(void)
{
	uint32_t sr = SPI1->SR;
	uint8_t recv_data;

	if (sr & SPI_SR_RX_NOTEMPTY) {
		recv_data = (uint8_t)SPI1->DR;
		
		if (spi_rx_callback) {
			spi_rx_callback(SPI1, recv_data);
		}
	}

	if (sr & SPI_SR_OVR) {
		recv_data = (uint8_t)SPI1->DR;
		(void)SPI1->SR;

		if (spi_ovr_callback) {
			spi_ovr_callback(SPI1, recv_data);
		}
	}
}