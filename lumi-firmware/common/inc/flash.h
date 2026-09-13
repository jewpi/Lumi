#ifndef __FLASH_H__
#define __FLASH_H__

#include <stdint.h>

typedef struct FLASH_INTERFACE {
    uint32_t ACR;
    uint32_t KEYR;
    uint32_t OPTKEYR;
    uint32_t SR;
    uint32_t CR;
    uint32_t OPTCR;
} FLASH_interface;

#define FLASH ((FLASH_interface *)0x40023C00)

// FLASH register setting
#define FLASH_ACR_ENABLE_DATA_CACHE (1 << 10)
#define FLASH_ACR_ENABLE_INST_CACHE (1 << 9)
#define FLASH_ACR_ENABLE_PREFETCH   (1 << 8)
#define FLASH_ACR_RESET_DATA_CACHE  (1 << 12)
#define FLASH_ACR_RESET_INST_CACHE  (1 << 11)


#define FLASH_UNLOCK_KEY1 0x45670123
#define FLASH_UNLOCK_KEY2 0xCDEF89AB

// FLASH interface register setting
#define FLASH_CR_LOCK   (1 << 31)
#define FLASH_SR_BSY    (1 << 16)
#define FLASH_CR_SER    (1 << 1)
#define FLASH_CR_PG     (1 << 0)
#define FLASH_CR_STRT   (1 << 16)
#define FLASH_SR_PGSERR (1 << 7)
#define FLASH_SR_PGPERR (1 << 6)
#define FLASH_SR_PGAERR (1 << 5)
#define FLASH_SR_WRPERR (1 << 4)


/* FLASH interface prototypes */
void flash_init(void);
void flash_lock(void);
void flash_unlock(void);
int8_t flash_erase(uint8_t sector_num);
int8_t flash_write_word(uint32_t start_addr, uint32_t data);
void flash_cache_flush(void);

#endif