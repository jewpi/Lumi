#ifndef __UART_H__
#define __UART_H_

#include <stdint.h>

typedef struct UART_X {
	uint32_t SR;
	uint32_t DR;
	uint32_t BRR;
	uint32_t CR1;
	uint32_t CR2;
	uint32_t CR3;
	uint32_t GTPR;
} UART_x;

#define UART3_BASE 0x40004800

#define UART3 ((UART_x *)UART3_BASE)

#define UART1_PIN_AF (7)
#define UART2_PIN_AF (7)
#define UART3_PIN_AF (7)

#define UART4_PIN_AF (8)
#define UART5_PIN_AF (8)
#define UART6_PIN_AF (8)


#define UART_CR1_UART_ENABLE    (1 << 13)
#define UART_CR1_WORD_LEN       (1 << 12)
#define UART_CR1_PARITY_ENABLED (1 << 10)
#define UART_CR1_PARITY_ODD     (1 << 9)
#define UART_CR1_TX_ENABLE      (1 << 3)
#define UART_CR1_RX_ENABLE      (1 << 2)
#define UART_CR1_RXNEIE			(1 << 5)
#define UART_CR1_TXEIE			(1 << 7)
#define UART_CR1_IDLEIE			(1 << 4)

#define UART_CR2_STOPBITS       (3 << 12)

#define UART_CR3_DMAR			(1 << 6)
#define UART_CR3_DMAT			(1 << 7)

#define UART_SR_TXE             (1 << 7)
#define UART_SR_RXNE            (1 << 5)
#define UART_SR_IDLE			(1 << 4)


void uart_init(UART_x *uart, uint32_t bitrate);	// "bitrate-8-N-1" 고정
void uart3_dma_rx_init(uint8_t *rx_dma_buffer, uint16_t packet_size);
void uart3_dma_tx_init(void);
void uart3_dma_send_packet(uint8_t *tx_buffer, uint16_t length);
void uart_recv_it_onoff(UART_x *uart, uint8_t enable);
void uart_write(UART_x *uart, const char *data);
void uart_deinit(UART_x *uart);

#endif
