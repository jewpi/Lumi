import serial
import struct
import time

# 라즈베리파이 UART 포트 및 보레이트 설정
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 115200

def main():
    try:
        # UART 시리얼 포트 오픈
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        print(f"Connected to {SERIAL_PORT} at {BAUDRATE} bps")
        print("종료하려면 input 값에 'q'를 입력하세요.\n")
        time.sleep(1)

        while True:
            # 1. Linear X 입력 받기
            user_input = input("Linear X 입력 (m/s) [종료: q]: ").strip()
            if user_input.lower() == 'q':
                break

            try:
                linear_x = float(user_input)
            except ValueError:
                print("❌ 유효한 float 숫자를 입력해주세요.\n")
                continue

            # 2. Angular Z 입력 받기
            user_input = input("Angular Z 입력 (rad/s) [종료: q]: ").strip()
            if user_input.lower() == 'q':
                break

            try:
                angular_z = float(user_input)
            except ValueError:
                print("❌ 유효한 float 숫자를 입력해주세요.\n")
                continue

            # 3. float 2개를 Little-Endian으로 패킹 (8 Byte)
            packet = struct.pack('<ff', linear_x, angular_z)

            # 4. UART 송신
            ser.write(packet)
            print(f" 전송 완료 -> Lin_X: {linear_x:.2f}, Ang_Z: {angular_z:.2f} (8 Bytes)\n")

    except serial.SerialException as e:
        print(f"[ERROR] {e}")

    except KeyboardInterrupt:
        print("\n[STOP] Program terminated by user.")

    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial port closed.")

if __name__ == '__main__':
    main()
