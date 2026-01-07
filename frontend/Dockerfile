# المرحلة 1: البناء (Build Stage)
# 🟢 التغيير هنا: نستخدم نسخة 22 الحديثة
FROM node:22-alpine as build-stage

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# المرحلة 2: التشغيل (Production Stage)
FROM nginx:alpine as production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]