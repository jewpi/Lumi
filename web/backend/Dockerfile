FROM python:3.14-slim

WORKDIR /app

# 의존성 먼저 복사 → 코드만 바뀔 때 캐시 재사용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# X-Forwarded-* 를 신뢰할 대역 — 프론트 컨테이너 nginx가 있는 도커 브리지(172.16.0.0/12).
# uvicorn은 --proxy-headers가 기본 켜져 있지만 forwarded_allow_ips 기본값이 127.0.0.1이라
# 172.x에서 온 헤더를 통째로 무시한다 → 스킴이 항상 http로 잡혀 리다이렉트 Location이
# http://로 떨어진다. 런타임 환경과 관계없이 프록시 헤더를 처리할 수 있도록 이미지에 둔다.
ENV FORWARDED_ALLOW_IPS=127.0.0.1,172.16.0.0/12

# SLAM 맵 저장 위치도 같은 이유로 이미지에 싣는다 — EC2의 compose 파일에는 이 변수가
# 없어서, 기본값(BASE_DIR/media/maps = 컨테이너 내부)으로 떨어지면 재배포마다 맵이
# 사라진다. 로봇이 기동 시 1회만 전송하는 데이터라 유실되면 재전송까지 지도가 빈다.
ENV MAP_DIR=/data/maps

# DB는 /data 볼륨에 저장 (compose에서 DB_PATH 주입)
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
