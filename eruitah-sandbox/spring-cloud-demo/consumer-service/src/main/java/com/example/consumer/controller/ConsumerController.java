package com.example.consumer.controller;

import com.example.consumer.feign.ProviderFeignClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.*;
import java.util.*;

/**
 * 服务消费者 - Web 接口
 *
 * 这是面向前端/客户端的接口层（BFF - Backend For Frontend）。
 * 本身不处理复杂业务逻辑，通过 FeignClient 调用下游服务获取数据。
 *
 * 典型调用链路：
 *   浏览器/网关 → consumer-service(:8080) → provider-service(:8070)
 */
@RestController
@RequestMapping("/api/consumer")
public class ConsumerController {

    private static final Logger log = LoggerFactory.getLogger(ConsumerController.class);

    /**
     * 注入 Feign 客户端（Spring 自动注入代理实现类）
     */
    private final ProviderFeignClient providerFeignClient;

    public ConsumerController(ProviderFeignClient providerFeignClient) {
        this.providerFeignClient = providerFeignClient;
    }

    /**
     * 综合健康检查（检查自身 + 下游服务）
     * GET /api/consumer/health-check
     */
    @GetMapping("/health-check")
    public Map<String, Object> healthCheck() {
        log.info("📋 执行健康检查...");
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("consumer", "consumer-service (UP)");

        // 通过 Feign 远程调用 provider 的健康检查
        Map<String, Object> providerHealth = providerFeignClient.health();
        result.put("provider", providerHealth);

        return result;
    }

    /**
     * 获取用户信息（Feign 远程调用）
     * GET /api/consumer/user/{id}
     */
    @GetMapping("/user/{id}")
    public Map<String, Object> getUser(@PathVariable Long id) {
        log.info("📋 获取用户信息: id={}", id);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("caller", "consumer-service");
        result.put("user", providerFeignClient.getUser(id));
        return result;
    }

    /**
     * 获取用户列表（Feign 远程调用 + 分页参数传递）
     * GET /api/consumer/users?page=1&size=5
     */
    @GetMapping("/users")
    public Map<String, Object> getUsers(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size) {
        log.info("📋 获取用户列表: page={}, size={}", page, size);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("caller", "consumer-service");
        result.put("users", providerFeignClient.getUsers(page, size));
        return result;
    }

    /**
     * 创建用户（Feign POST 远程调用）
     * POST /api/consumer/user
     * Body: {"name": "李四", "age": 25, "email": "lisi@example.com"}
     */
    @PostMapping("/user")
    public Map<String, Object> createUser(@RequestBody Map<String, Object> user) {
        log.info("📋 创建用户: {}", user);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("caller", "consumer-service");
        result.put("createResult", providerFeignClient.createUser(user));
        return result;
    }

    /**
     * 计算接口（Feign 远程调用）
     * GET /api/consumer/calculate?a=10&b=20
     *
     * 注意：consumer 用 GET 接收参数，内部转 POST 调用 provider
     */
    @GetMapping("/calculate")
    public Map<String, Object> calculate(@RequestParam int a, @RequestParam int b) {
        log.info("📋 计算: a={}, b={}", a, b);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("caller", "consumer-service");

        Map<String, Integer> params = new HashMap<>();
        params.put("a", a);
        params.put("b", b);
        result.put("calculation", providerFeignClient.calculate(params));
        return result;
    }

    /**
     * 回显接口（Feign 远程调用）
     * GET /api/consumer/echo?message=hello
     */
    @GetMapping("/echo")
    public Map<String, Object> echo(@RequestParam String message) {
        log.info("📋 回显: message={}", message);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("caller", "consumer-service");
        result.put("echo", providerFeignClient.echo(message));
        return result;
    }
}
