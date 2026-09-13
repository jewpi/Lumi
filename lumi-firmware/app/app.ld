MEMORY
{
    FLASH (rx) : ORIGIN = 0x08010000, LENGTH = 0x00070000
    RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}

SECTIONS
{
    .isr_vector :
    {
        . = ALIGN(4);
        KEEP(*(.isr_vector))
        . = ALIGN(4);
    } > FLASH

    .text :
    {
        _start_text = .;
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
        _end_text = .;
    } > FLASH

    /* C 표준 라이브러리가 사용하는 section. */
    .ARM.exidx :
    {
        . = ALIGN(4);
        __exidx_start = .;
        *(.ARM.exidx* .gnu.linkonce.armexidx.*)
        __exidx_end = .;
        . = ALIGN(4);
    } > FLASH

    _stored_data = .;

    .data : AT (_stored_data)
    {
        _start_data = .;
        KEEP(*(.data*))
        . = ALIGN(4);
        _end_data = .;
    } > RAM

    .bss :
    {
        _start_bss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _end_bss = .;
    } > RAM

    /* _sbrk(malloc/sprintf 내부 호출)가 힙의 시작점을 찾기 위해 필요한 심볼 */
    . = ALIGN(4);
    _end = .;    /* 표준 라이브러리용 */
    end = .;     /* 일부 툴체인 호환용 */
}

END_STACK = ORIGIN(RAM) + LENGTH(RAM);