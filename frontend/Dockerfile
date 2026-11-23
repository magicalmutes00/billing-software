# Render-managed backend URL is injected at build time as BACKEND_URL.
# Fall back to /api (same-origin) for local dev where nginx proxies /api.
ARG BACKEND_URL=/api

FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Bake the backend base URL into the Vite build so the frontend knows where to call the API.
RUN BACKEND_URL=${BACKEND_URL} npm run build

FROM nginx:1.27-alpine

# envsubst replaces ${BACKEND_URL} in nginx.conf at startup with the Render backend URL.
RUN apk add --no-cache gettext
COPY nginx.conf /etc/nginx/conf.d/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["sh", "-c", "envsubst '\${BACKEND_URL}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
