# 빌드 도구 설정
CROSS_COMPILE = arm-none-eabi-
CC = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy

# 디렉토리 설정
BUILD_DIR = build
COMMON_DIR = common
APP_DIR = app
BL_DIR = bootloader

# ===== uC/OS-II 디렉토리 경로 정의 =====
UCOS_DIR       = $(APP_DIR)/src/uCOS-II
UCOS_SRC_DIR   = $(UCOS_DIR)/Source
UCOS_PORT_DIR  = $(UCOS_DIR)/Ports

# 공통 컴파일 플래그
CFLAGS = -mcpu=cortex-m4 -mthumb -g -ggdb -Wall -Wno-main -Wstack-usage=200 -ffreestanding

# ===== [추가] 하드웨어 FPU 활성화 플래그 =====
FPU_FLAGS = -mfloat-abi=hard -mfpu=fpv4-sp-d16

# CFLAGS에 FPU 플래그 적용
CFLAGS += $(FPU_FLAGS)

# ===== uC/OS-II 헤더 인클루드 패스 추가 =====
CFLAGS += -I$(COMMON_DIR)/inc -I$(APP_DIR)/inc -I$(BL_DIR)/inc \
          -I$(UCOS_SRC_DIR) -I$(UCOS_PORT_DIR)

# 공통 링크 플래그
LDFLAGS = -Wl,-gc-sections -mcpu=cortex-m4 -mthumb -nostartfiles
LDFLAGS += --specs=nano.specs -lc -lm -lnosys -u _printf_float

# ===== [수정] 링크 단계에도 하드웨어 FPU 플래그 전달 =====
LDFLAGS += $(FPU_FLAGS)

# 파일 목록 자동 생성
SRCS_COMMON = $(wildcard $(COMMON_DIR)/src/*.c)
SRCS_BL     = $(wildcard $(BL_DIR)/src/*.c)

# ===== uC/OS-II 소스 파일 리스트 빌드 대상에 추가 =====
SRCS_APP    = $(wildcard $(APP_DIR)/src/*.c)
SRCS_UCOS_CORE = $(wildcard $(UCOS_SRC_DIR)/*.c)
SRCS_UCOS_PORT = $(wildcard $(UCOS_PORT_DIR)/*.c) \
                 $(wildcard $(UCOS_PORT_DIR)/*.S)

# 빌드 타겟
all: $(BUILD_DIR)/image.bin
	cp $^ /mnt/c/wsl2\ workspace/image.bin

$(BUILD_DIR)/image.bin: $(BUILD_DIR)/bootloader.bin $(BUILD_DIR)/app.bin
	cat $(BUILD_DIR)/bootloader.bin $(BUILD_DIR)/app.bin > $@

$(BUILD_DIR)/app.bin: $(BUILD_DIR)/app.elf
	$(OBJCOPY) -O binary $< $@

$(BUILD_DIR)/bootloader.bin: $(BUILD_DIR)/bootloader.elf
	$(OBJCOPY) -O binary --pad-to=0x08010000 --gap-fill=0xFF $< $@

# ===== app.elf 빌드 규칙 =====
$(BUILD_DIR)/app.elf: $(SRCS_COMMON) $(SRCS_APP) $(SRCS_UCOS_CORE) $(SRCS_UCOS_PORT) $(APP_DIR)/app.ld | $(BUILD_DIR)
	$(CC) $(CFLAGS) $(SRCS_COMMON) $(SRCS_APP) $(SRCS_UCOS_CORE) $(SRCS_UCOS_PORT) -o $@ $(LDFLAGS) -Wl,-Map=$(BUILD_DIR)/app.map -T $(APP_DIR)/app.ld

# ===== bootloader.elf 빌드 규칙 =====
$(BUILD_DIR)/bootloader.elf: $(SRCS_COMMON) $(SRCS_BL) $(BL_DIR)/bootloader.ld | $(BUILD_DIR)
	$(CC) $(CFLAGS) $(SRCS_COMMON) $(SRCS_BL) -o $@ $(LDFLAGS) -Wl,-Map=$(BUILD_DIR)/bootloader.map -T $(BL_DIR)/bootloader.ld

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)
	rm -rf /mnt/c/wsl2\ workspace/image.bin