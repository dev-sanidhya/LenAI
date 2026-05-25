FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
# Use npm install (not ci) so the build works whether or not a lock file is committed.
# In a stricter CI pipeline this should be `npm ci` against a committed lockfile.
RUN npm install --legacy-peer-deps --no-audit --no-fund

COPY . .

ARG VITE_API_URL=http://localhost:8000
ARG VITE_API_KEY=dev-api-key-change-in-production
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_API_KEY=${VITE_API_KEY}

RUN npm run build

FROM nginx:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
