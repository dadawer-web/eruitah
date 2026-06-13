package com.example.consumer.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

/**
 * Feign 声明式客户端接口
 *
 * @FeignClient 核心属性：
 *   - name="provider-service"：目标服务名（对应 Nacos 注册名）
 *   - path="/api/provider"：统一路径前缀
 *   - fallbackFactory：熔断降级工厂类（服务不可用时的兜底逻辑）
 *
 * 工作原理：
 *   1. Spring 启动时扫描此接口，生成动态代理类
 *   2. 调用方法时，代理类从 Nacos 获取 provider-service 实例列表
 *   3. 通过 LoadBalancer 选择实例（默认轮询），发起 HTTP 请求
 *   4. 自动将 JSON 响应反序列化为 Java 对象
 */
@FeignClient(
    name = "provider-service",
    path = "/api/provider",
    fallbackFactory = ProviderFeignFallbackFactory.class
)
public interface ProviderFeignClient {

    /**
     * 调用 provider 的健康检查
     */
    @GetMapping("/health")
    Map<String, Object> health();

    /**
     * 获取用户信息
     * @PathVariable 必须指定 value，Feign 需要知道路径参数名
     */
    @GetMapping("/user/{id}")
    Map<String, Object> getUser(@PathVariable("id") Long id);

    /**
     * 获取用户列表
     */
    @GetMapping("/users")
    Map<String, Object> getUsers(
        @RequestParam("page") int page,
        @RequestParam("size") int size
    );

    /**
     * 创建用户（POST 请求）
     * @RequestBody 将对象序列化为 JSON 放入请求体
     */
    @PostMapping("/user")
    Map<String, Object> createUser(@RequestBody Map<String, Object> user);

    /**
     * 调用计算接口
     */
    @PostMapping("/calculate")
    Map<String, Object> calculate(@RequestBody Map<String, Integer> params);

    /**
     * 调用回显接口
     */
    @GetMapping("/echo")
    Map<String, String> echo(@RequestParam("message") String message);
}
