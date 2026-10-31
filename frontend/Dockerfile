# Stage 1: build the React app with Node. Only the static output survives.
FROM node:24.22.2-alpine3.24 AS build
WORKDIR /app
# Install from the lock file first, in its own layer, so code changes don't
# re-download every package. npm ci installs exactly what the lock file says.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# Stage 2: a small Nginx image with just the built files. No Node, no
# node_modules and no source code end up in what actually runs.
FROM nginx:1.30.6-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
