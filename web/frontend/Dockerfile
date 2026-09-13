# --- 빌드 단계 ---
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# 운영은 같은 오리진(nginx)으로 호출 → API_BASE 비우고 WS는 상대경로
ENV VITE_API_BASE=""
ENV VITE_WS_URL="/ws"
ENV VITE_CAMERA_WS_URL="/ws/camera/view/1"
RUN npm run build

# --- 서빙 단계 ---
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
