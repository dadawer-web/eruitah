package com.example.consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.openfeign.EnableFeignClients;

/**
 * 服务消费者启动类
 *
 * @EnableDiscoveryClient：启用服务发现（从 Nacos 获取服务列表）
 * @EnableFeignClients：启用 OpenFeign 声明式远程调用
 *   - 扫描 @FeignClient 注解的接口
 *   - 自动生成代理实现类，通过 HTTP 调用目标服务
 */
@SpringBootApplication
@EnableDiscoveryClient
@EnableFeignClients
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
        System.out.println("========================================");
        System.out.println("  ✅ Consumer Service 启动成功！");
        System.out.println("  📋 已注册到 Nacos: consumer-service");
        System.out.println("  🌐 Web 接口: http://localhost:8080");
        System.out.println("  🔗 通过 Feign 调用 provider-service");
        System.out.println("========================================");
    }
}
