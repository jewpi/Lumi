#include <stdint.h>
#include "spi.h"
#include "gpio.h"
#include "rcc.h"
#include "nvic.h"

// SPI1 pins
#define SPI1_MOSI_PIN (5)   // PB5
#define SPI1_MISO_PIN (4)   // PB4
#define SPI1_SCK_PIN  (5)   // PA5
#define SPI1_NSS_PIN  (4)   // PA4

void (*spi_rx_callback)(SPI_x *spi, uint8_t data) = 0;
void (*spi_ovr_callback)(SPI_x *spi, uint8_t data) = 0;

static void spi_reset(SPI_x *spi)
{
    if (spi == SPI1) {
        RCC_APB2_CLOCK_RST |= SPI1_APB2_CLOCK_ER_VAL;
        __asm__ volatile ("DMB");
        RCC_APB2_CLOCK_RST &= ~SPI1_APB2_CLOCK_ER_VAL;
    }
}

static void spi_pins_setup(SPI_x *spi)
{
    if (spi == SPI1) {
        /* PA5, PA4 SPI AF gpio set */
        gpio_set_mode(GPIOA, SPI1_SCK_PIN, GPIO_MODE_AF);
        gpio_set_mode(GPIOA, SPI1_NSS_PIN, GPIO_MODE_AF);

        gpio_set_af(GPIOA, SPI1_SCK_PIN, SPI1_PIN_AF);
        gpio_set_af(GPIOA, SPI1_NSS_PIN, SPI1_PIN_AF);

        /* PB5, PB4 SPI AF gpio set */
        gpio_set_mode(GPIOB, SPI1_MOSI_PIN, GPIO_MODE_AF);
        gpio_set_mode(GPIOB, SPI1_MISO_PIN, GPIO_MODE_AF);

        gpio_set_af(GPIOB, SPI1_MOSI_PIN, SPI1_PIN_AF);
        gpio_set_af(GPIOB, SPI1_MISO_PIN, SPI1_PIN_AF);

        /* NSS pin pull-up */
        gpio_set_pupd(GPIOA, SPI1_NSS_PIN, GPIO_PUPD_PU);

        /* SPI pin 고속모드 설정 */
        gpio_set_ospeed(GPIOA, SPI1_SCK_PIN, GPIO_OSPEED_VH);
        gpio_set_ospeed(GPIOA, SPI1_NSS_PIN, GPIO_OSPEED_VH);
        gpio_set_ospeed(GPIOB, SPI1_MOSI_PIN, GPIO_OSPEED_VH);
        gpio_set_ospeed(GPIOB, SPI1_MISO_PIN, GPIO_OSPEED_VH);

        // SPI clock on
        RCC_APB2_CLOCK_ER |= SPI1_APB2_CLOCK_ER_VAL;
    }
}

void spi_init(SPI_x *spi, uint8_t mode, uint8_t size, uint8_t use_it)
{
    uint32_t reg;
    volatile uint32_t dummy;

    spi_pins_setup(spi);

    // SPI reset
    spi_reset(spi);

    // SPI off
    spi->CR1 &= ~SPI_CR1_SPI_EN;
        
    if (mode == SPI_RECV_ONLY_SLAVE) {
        // set slave mode(MSTR)
        reg = spi->CR1;
        reg &= ~SPI_CR1_MASTER;

        // set CPOL/CPHA
        reg &= ~(0x03);

        // set Data frame format(8bit/16bit)
        (size == 16) ? (reg |= (1 << 11)) : (reg &= ~(1 << 11));

        // set RXONLY
        reg |= (1 << 10);

        // set Slave NSS mode(SSM/SSI)
        reg &= ~(1 << 9);
        spi->CR1 = reg;

        // reset SSOE (HW의 NSS 핀 출력 off)
        spi->CR2 &= ~(1 << 2);

        if (use_it) {
            // RXNEIE, ERRIE(OVR) set
            spi->CR2 |= SPI_CR2_RXNEI_EN | SPI_CR2_ERRI_EN;

            // NVIC spi interrupt enable
            nvic_irq_enable(NVIC_SPI1_IRQN);
            nvic_irq_setprio(NVIC_SPI1_IRQN, 6);
        }
    }
    
    if (mode == SPI_FULL_DUP_MASTER) {
        ;
    }

    // SPI on
    spi->CR1 |= SPI_CR1_SPI_EN;

    // Clean data register
    dummy= spi->DR;
    (void)dummy;
}

void spi_write(SPI_x *spi, uint16_t data)
{
    ;
}

void spi_read(SPI_x *spi, uint16_t *data)
{
    ;
}

void spi_deinit(SPI_x *spi)
{
    uint32_t reg;

    // SPI interrupt disable
    reg = spi->CR2;
    reg &= ~SPI_CR2_RXNEI_EN;
    reg &= ~SPI_CR2_ERRI_EN;
    spi->CR2 = reg;

    // SPI off
    reg = spi->CR1;
    reg &= ~SPI_CR1_SPI_EN;
    spi->CR1 = reg;

    // wait busy
    reg = spi->SR;
    while (spi->SR & SPI_SR_BSY);

    // SPI reset
    spi_reset(spi);

    // SPI clock off
    if (spi == SPI1) {
        RCC_APB2_CLOCK_ER &= ~SPI1_APB2_CLOCK_ER_VAL;
    }

    // NVIC disable irq
    nvic_irq_disable(NVIC_SPI1_IRQN);
}

void spi_regist_rx_callback(void (*func)(SPI_x *, uint8_t))
{
    spi_rx_callback = func;
}

void spi_regist_ovr_callback(void (*func)(SPI_x *, uint8_t))
{
    spi_ovr_callback = func;
}