// ANSI 색상 코드 정의
#define ANSI_RESET          "\x1b[0m"
#define ANSI_TEXT_BLACK     "\x1b[30m"
#define ANSI_TEXT_RED       "\x1b[31m"
#define ANSI_TEXT_GREEN     "\x1b[32m"
#define ANSI_TEXT_YELLOW    "\x1b[33m"
#define ANSI_TEXT_BLUE      "\x1b[34m"
#define ANSI_TEXT_MAGENTA   "\x1b[35m"
#define ANSI_TEXT_CYAN      "\x1b[36m"
#define ANSI_TEXT_WHITE     "\x1b[37m"

// 배경 색상
#define ANSI_BG_RED         "\x1b[41m"
#define ANSI_BG_GREEN       "\x1b[42m"

#define LOG_INFO(fmt, ...)  printf("[" ANSI_TEXT_WHITE "INFO" ANSI_RESET "] " fmt "\r\n", ##__VA_ARGS__)
#define LOG_BOOT(fmt, ...)  printf("[" ANSI_TEXT_CYAN "BOOT" ANSI_RESET "] " fmt "\r\n", ##__VA_ARGS__)
#define LOG_OTA(fmt, ...)   printf("[" ANSI_TEXT_MAGENTA "OTA " ANSI_RESET "] " fmt "\r\n", ##__VA_ARGS__)
#define LOG_OK(fmt, ...)    printf("[" ANSI_TEXT_GREEN " OK " ANSI_RESET "] " fmt "\r\n", ##__VA_ARGS__)
#define LOG_WARN(fmt, ...)  printf("[" ANSI_TEXT_YELLOW "WARN" ANSI_RESET "] " fmt "\r\n", ##__VA_ARGS__)
#define LOG_ERROR(fmt, ...) printf("[" ANSI_TEXT_WHITE ANSI_BG_RED "ERR " ANSI_RESET "] " fmt "\r\n", ##__VA_ARGS__)