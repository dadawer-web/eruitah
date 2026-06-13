# 🚀 Spring Cloud 微服务示例

## 📖 项目概述

一个完整的 Spring Cloud 微服务示例，演示以下核心能力：

| 组件 | 作用 |
|------|------|
| **Nacos** | 服务注册中心（服务注册与发现） |
| **OpenFeign** | 声明式 HTTP 客户端（远程调用） |
| **LoadBalancer** | 客户端负载均衡（轮询算法） |
| **Gateway** | API 网关（统一入口、路由转发） |
| **Sentinel** | 熔断降级（服务容错保护） |

## 🏗️ 项目结构

```
spring-cloud-demo/
├── pom.xml                           # 父 POM（统一版本管理）
│
├── provider-service/                 # 🔵 服务提供者（端口 8070）
│   ├── pom.xml
│   └── src/main/java/com/example/provider/
│       ├── ProviderApplication.java      # 启动类
│       ├── controller/ProviderController # REST 接口
│       ├── entity/User.java              # 用户实体
│       └── exception/GlobalExceptionHandler # 全局异常处理
│
├── consumer-service/                 # 🟢 服务消费者（端口 8080）
│   ├── pom.xml
│   └── src/main/java/com/example/consumer/
│       ├── ConsumerApplication.java      # 启动类
│       ├── controller/ConsumerController # Web 接口
│       ├── feign/ProviderFeignClient     # Feign 声明式客户端
│       ├── feign/ProviderFeignFallbackFactory # 降级工厂
│       ├── config/FeignConfig            # Feign 配置
│       ├── config/WebConfig              # CORS + 首页配置
│       └── resources/static/index.html   # 前端页面
│
└── gateway-service/                  # 🟡 API 网关（端口 9000）
    ├── pom.xml
    └── src/main/java/com/example/gateway/
        ├── GatewayApplication.java       # 启动类
        └── resources/application.yml     # 路由配置
```

## 🚀 快速启动

### 前置条件
- JDK 1.8+
- Maven 3.6+
- Nacos 2.x（下载地址：https://github.com/alibaba/nacos/releases）

### 步骤 1：启动 Nacos

```bash
# 单机模式启动
sh startup.sh -m standalone

# 访问控制台: http://localhost:8848/nacos
# 默认账号: nacos / nacos
```

### 步骤 2：编译项目

```bash
cd spring-cloud-demo
mvn clean package -DskipTests
```

### 步骤 3：按顺序启动服务

```bash
# 1️⃣ 启动 Provider（先启动被调用方）
java -jar provider-service/target/provider-service-1.0-SNAPSHOT.jar

# 2️⃣ 启动 Consumer
java -jar consumer-service/target/consumer-service-1.0-SNAPSHOT.jar

# 3️⃣ 启动 Gateway（可选）
java -jar gateway-service/target/gateway-service-1.0-SNAPSHOT.jar
```

### 步骤 4：访问前端页面

```
直接访问 Consumer:  http://localhost:8080/
通过 Gateway 访问:  http://localhost:9000/
```

## 🔗 调用链路

```
浏览器请求
    │
    ▼
gateway-service(:9000)     ← 统一入口，路由转发
    │
    ▼
consumer-service(:8080)    ← 业务处理
    │
    ├── Feign 远程调用 ──▶ provider-service(:8070)
    │                          │
    │                          ▼
    │                     返回 JSON 数据
    │
    ▼
返回响应给浏览器
```

## 📋 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/consumer/health-check` | GET | 健康检查 |
| `/api/consumer/users?page=1&size=10` | GET | 用户列表 |
| `/api/consumer/user/{id}` | GET | 查询用户 |
| `/api/consumer/user` | POST | 创建用户 |
| `/api/consumer/calculate?a=10&b=20` | GET | 远程计算 |
| `/api/consumer/echo?message=hello` | GET | 回显测试 |

## 💡 核心知识点

### 1. 服务注册与发现
```java
@EnableDiscoveryClient  // 启动时自动注册到 Nacos
```

### 2. Feign 声明式调用
```java
@FeignClient(name = "provider-service", path = "/api/provider")
public interface ProviderFeignClient {
    @GetMapping("/user/{id}")
    Map<String, Object> getUser(@PathVariable("id") Long id);
}
```

### 3. 熔断降级
```java
// 当 provider 不可用时，返回兜底数据
@Component
public class ProviderFeignFallbackFactory implements FallbackFactory<ProviderFeignClient> { ... }
```

### 4. 网关路由
```yaml
spring.cloud.gateway.routes:
  - id: consumer
    uri: lb://consumer-service    # lb:// 表示负载均衡
    predicates:
      - Path=/api/consumer/**
```

## 📊 版本信息

| 组件 | 版本 |
|------|------|
| Spring Boot | 2.7.5 |
| Spring Cloud | 2021.0.5 |
| Spring Cloud Alibaba | 2021.0.5.0 |
| Nacos | 2.x |
