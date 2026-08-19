# Multi-stage: build with node, serve the static bundle with nginx.
# nginx over `vite preview` deliberately: a static file server has no node
# runtime to crash mid-demo, restarts instantly, and serves the SPA fallback
# for deep links (/applications/:id) via try_files.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
