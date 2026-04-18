FROM maven:3.9.6-eclipse-temurin-17 AS build
WORKDIR /app

COPY java/pom.xml .
COPY java/src ./src

RUN mvn clean package -DskipTests

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app

COPY --from=build /app/target/protobuf-rpc-bridge-1.0.0.jar app.jar

EXPOSE 9999

ENTRYPOINT ["java", "-jar", "app.jar"]
