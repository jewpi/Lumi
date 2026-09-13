MEMORY
{
	FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 0x00010000
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
		KEEP(*(.text*))
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

	.bss (NOLOAD) :
	{
		_start_bss = .;
		*(.bss*)
		*(COMMON)
		. = ALIGN(4);
		_end_bss = .;
	} > RAM
	. = ALIGN(4);

	/* _sbrk(malloc/sprintf 내부 호출)가 힙의 시작점을 찾기 위해 필요한 심볼 */
    . = ALIGN(4);
    _end = .;    /* 표준 라이브러리용 */
    end = .;     /* 일부 툴체인 호환용 */
}

END_STACK = ORIGIN(RAM) + LENGTH(RAM);
