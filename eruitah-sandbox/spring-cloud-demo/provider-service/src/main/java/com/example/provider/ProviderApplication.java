package com.example.provider;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

/**
 * 服务提供者启动类
 *
 * @EnableDiscoveryClient：启用服务注册与发现
 *   - 启动时自动将本服务注册到 Nacos
 *   - 其他服务可通过服务名 "provider-service" 发现本服务
 */
@SpringBootApplication
@EnableDiscoveryClient
public class ProviderApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProviderApplication.class, args);
        System.out.println("========================================");
        System.out.println("  ✅ Provider Service 启动成功！");
        System.out.println("  📋 已注册到 Nacos: provider-service");
        System.out.println("  🌐 REST 接口: http://localhost:8070");
        System.out.println("========================================");
    }
}
