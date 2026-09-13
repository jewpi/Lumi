#include <stdint.h>
#include "flash.h"

void flash_init(void)
{
    // 5 waits time, Data/Instruction cache enable, Prefetch enable
	FLASH->ACR |= 5 | FLASH_ACR_ENABLE_DATA_CACHE | FLASH_ACR_ENABLE_INST_CACHE | FLASH_ACR_ENABLE_PREFETCH;
}

void flash_lock(void)
{
    // flash lock 비트에 1 write
    FLASH->CR |= FLASH_CR_LOCK;
}

void flash_unlock(void)
{
    // flash lock 비트 확인
    if (FLASH->CR & FLASH_CR_LOCK) {
        // flash lock을 위한 key 값 write
        FLASH->KEYR = FLASH_UNLOCK_KEY1;
        FLASH->KEYR = FLASH_UNLOCK_KEY2;
    }

    // flash lock 비트 해제까지 대기
    while (FLASH->CR & FLASH_CR_LOCK);
}

int8_t flash_erase(uint8_t sector_num)
{
    if (FLASH->CR & FLASH_CR_LOCK) return -1;

    // flash의 busy 상태 확인
    while (FLASH->SR & FLASH_SR_BSY);

    // error flags clear
    FLASH->SR |= FLASH_SR_PGSERR | FLASH_SR_PGPERR | FLASH_SR_PGAERR | FLASH_SR_WRPERR;

    // flash의 SER 비트를 켜서 sector 삭제 모드 활성화
    FLASH->CR |= FLASH_CR_SER;

    // erase할 sector 설정
    FLASH->CR &= ~(0xf << 3);
    FLASH->CR |= (sector_num << 3);

    // flash의 STRT 비트를 켜서 sector 삭제 시작
    FLASH->CR |= FLASH_CR_STRT;

    // flash의 busy 상태가 해제 될 때 까지 대기
    while (FLASH->SR & FLASH_SR_BSY);

    // 다음 작업을 위해 SER 비트 clear
    FLASH->CR &= ~FLASH_CR_SER;

    if (FLASH->SR & (FLASH_SR_PGSERR | FLASH_SR_PGPERR | FLASH_SR_PGAERR | FLASH_SR_WRPERR)) {
        return -1;
    }
    return 0;
}

int8_t flash_write_word(uint32_t start_addr, uint32_t data)
{
    if (FLASH->CR & FLASH_CR_LOCK) return -1;

    // flash의 busy 상태 확인
    while (FLASH->SR & FLASH_SR_BSY);

    // flash의 PG 비트를 켜서 프로그램 모드 활성화
    FLASH->CR |= FLASH_CR_PG;

    // flash 쓰기 단위 크기 32bit 설정
    FLASH->CR &= ~(0x03 << 8);
    FLASH->CR |= (0x2 << 8);

    // flash 주소에 data wrtie
    *(volatile uint32_t *)start_addr = data;

    // flash의 busy 상태가 해제 될 때 까지 대기
    while (FLASH->SR & FLASH_SR_BSY);

    // 다음 작업을 위해 PG 비트 clear
    FLASH->CR &= ~FLASH_CR_PG;

    if (FLASH->SR & (FLASH_SR_PGSERR | FLASH_SR_PGPERR | FLASH_SR_PGAERR | FLASH_SR_WRPERR)) {
        return -1;
    }
    return 0;
}

void flash_cache_flush(void)
{
    // 1. FLASH Data/Instruction cache disable
	FLASH->ACR &= ~(FLASH_ACR_ENABLE_DATA_CACHE | FLASH_ACR_ENABLE_INST_CACHE);
    __asm__ volatile ("ISB");

    // 2. FLASH cache reset
    FLASH->ACR |= (FLASH_ACR_RESET_DATA_CACHE | FLASH_ACR_RESET_INST_CACHE);
    __asm__ volatile ("ISB");

    FLASH->ACR &= ~(FLASH_ACR_RESET_DATA_CACHE | FLASH_ACR_RESET_INST_CACHE);
    __asm__ volatile ("ISB");

    // 3. FLASH Data/Instruction cache 재활성화
    FLASH->ACR |= (FLASH_ACR_ENABLE_DATA_CACHE | FLASH_ACR_ENABLE_INST_CACHE);
    __asm__ volatile ("ISB");
}