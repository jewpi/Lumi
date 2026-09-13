#ifndef __DMA_H__
#define __DMA_H__

#include <stdint.h>

typedef struct DMA_STREAM_X {
    uint32_t CR;     // 0x00 : Stream x configuration register
    uint32_t NDTR;   // 0x04 : Stream x number of data register
    uint32_t PAR;    // 0x08 : Stream x peripheral address register
    uint32_t M0AR;   // 0x0C : Stream x memory 0 address register
    uint32_t M1AR;   // 0x10 : Stream x memory 1 address register (Double buffer용)
    uint32_t FCR;    // 0x14 : Stream x FIFO control register
} DMA_Stream_x;

typedef struct DMA_X {
    uint32_t LISR;        // 0x00 : Low interrupt status register (Stream 0~3)
    uint32_t HISR;        // 0x04 : High interrupt status register (Stream 4~7)
    uint32_t LIFCR;       // 0x08 : Low interrupt flag clear register (Stream 0~3)
    uint32_t HIFCR;       // 0x0C : High interrupt flag clear register (Stream 4~7)
    DMA_Stream_x S[8];    // 0x10 ~ 0xCF : Stream 0 ~ Stream 7 레지스터 배열
} DMA_x;

#define DMA1_BASE    0x40026000U
#define DMA2_BASE    0x40026400U

#define DMA1         ((DMA_x *) DMA1_BASE)
#define DMA2         ((DMA_x *) DMA2_BASE)

#define DMA_LISR_TEIF1       (0x1U << 9)
#define DMA_LISR_TCIF1       (0x1U << 11)
#define DMA_LIFCR_CTCIF1     (0x1U << 11)
#define DMA_LIFCR_CHTIF1     (0x1U << 10)
#define DMA_LIFCR_CTEIF1     (0x1U << 9)
#define DMA_LIFCR_CDMEIF1    (0x1U << 8)
#define DMA_LIFCR_CFEIF1     (0x1U << 6)


#define DMA_SxCR_EN          (0x1U << 0)   // Bit 0  : Stream Enable
#define DMA_SxCR_TEIE        (0x1U << 2)   // Bit 2  : Transfer error interrupt enable
#define DMA_SxCR_TCIE        (0x1U << 4)   // Bit 4  : Transfer complete interrupt enable
#define DMA_SxCR_CIRC        (0x1U << 8)   // Bit 8  : Circular Mode
#define DMA_SxCR_MINC        (0x1U << 10)  // Bit 10 : Memory Increment Mode
#define DMA_SxCR_DIR_Pos     (6U)          // Bit 6 ~ 7   : Memory to peripheral
#define DMA_SxCR_CHSEL_Pos   (25U)         // Bit 25 ~ 27 : Channel Selection Position

#endif