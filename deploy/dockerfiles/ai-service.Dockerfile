# Java ai-service runtime-only（只放 jar，不在容器内编译）
FROM eclipse-temurin:17-jre-alpine

WORKDIR /app
ENV TZ=Asia/Shanghai
RUN apk add --no-cache tzdata && cp /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN mkdir -p /tmp/audio

COPY app.jar app.jar

EXPOSE 8081 9999
CMD ["java", "-Xms256m", "-Xmx512m", "-jar", "app.jar"]
