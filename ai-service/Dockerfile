FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

COPY target/ai-service-1.0.0.jar app.jar

RUN mkdir -p /tmp/audio

EXPOSE 8081

ENTRYPOINT ["sh", "-c", "java ${JAVA_OPTS:-} -jar app.jar"]
