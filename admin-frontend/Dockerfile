FROM node:20-slim

WORKDIR /app

COPY package*.json ./
# admin-frontend 历史上没保留 package-lock.json，用 npm install。
# 等 lockfile 补齐后可以切回 npm ci。
RUN npm install --no-audit --no-fund

COPY . .

# NEXT_PUBLIC_* 在 build 时烤进客户端 bundle，必须从外部传入。
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_MAIN_SITE_URL=http://localhost:3000
ARG NEXT_PUBLIC_USE_MOCK_EXPERIMENT_DATA=false
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_MAIN_SITE_URL=$NEXT_PUBLIC_MAIN_SITE_URL
ENV NEXT_PUBLIC_USE_MOCK_EXPERIMENT_DATA=$NEXT_PUBLIC_USE_MOCK_EXPERIMENT_DATA

RUN npm run build

ENV NODE_ENV=production
ENV PORT=3001

CMD ["npm", "start"]
