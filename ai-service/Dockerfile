FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

ENV TZ=Asia/Shanghai
RUN apk add --no-cache tzdata && cp /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY target/ai-service-1.0.0.jar app.jar

RUN mkdir -p /tmp/audio

EXPOSE 8081 9999

CMD ["java", "-Xms256m", "-Xmx512m", "-jar", "app.jar"]
