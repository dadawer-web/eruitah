package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

/**
 * API 网关启动类
 *
 * Gateway 的核心职责：
 *   1. 统一入口：所有外部请求都经过网关
 *   2. 路由转发：根据路径规则将请求转发到对应的微服务
 *   3. 负载均衡：通过 lb:// 协议实现客户端负载均衡
 *   4. 限流熔断：可以集成 Sentinel 实现限流
 *   5. 跨域处理：统一处理 CORS
 *
 * 注意：Gateway 基于 WebFlux（Netty），不能引入 spring-boot-starter-web
 */
@SpringBootApplication
@EnableDiscoveryClient
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
        System.out.println("========================================");
        System.out.println("  ✅ Gateway Service 启动成功！");
        System.out.println("  🌐 网关入口: http://localhost:9000");
        System.out.println("  📋 已注册到 Nacos: gateway-service");
        System.out.println("========================================");
        System.out.println("  路由规则：");
        System.out.println("    /api/provider/** → provider-service");
        System.out.println("    /api/consumer/** → consumer-service");
        System.out.println("========================================");
    }
}
