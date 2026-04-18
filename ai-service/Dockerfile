FROM maven:3.9.6-eclipse-temurin-17 AS build
WORKDIR /app

# 复制 pom.xml 和依赖文件
COPY pom.xml .
COPY src ./src

# 构建项目
RUN mvn clean package -DskipTests

# 使用轻量级的 Java 镜像
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app

# 复制构建好的 jar 文件
COPY --from=build /app/target/ai-service-1.0.0.jar app.jar

# 创建音频存储目录
RUN mkdir -p /tmp/audio

# 暴露端口
EXPOSE 8081

# 运行应用
ENTRYPOINT ["java", "-jar", "app.jar"]