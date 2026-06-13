package com.example.provider.controller;

import org.springframework.web.bind.annotation.*;
import java.util.*;

/**
 * 服务提供者 - REST 接口
 *
 * 提供完整的 CRUD 接口，供消费者通过 Feign 远程调用。
 * 这是微服务架构中的"被调用方"。
 */
@RestController
@RequestMapping("/api/provider")
public class ProviderController {

    // 模拟数据库（内存存储）
    private static final Map<Long, Map<String, Object>> userDB = new LinkedHashMap<>();
    static {
        // 初始化一些测试数据
        Map<String, Object> user1 = new HashMap<>();
        user1.put("id", 1L);
        user1.put("name", "张三");
        user1.put("age", 28);
        user1.put("email", "zhangsan@example.com");
        userDB.put(1L, user1);

        Map<String, Object> user2 = new HashMap<>();
        user2.put("id", 2L);
        user2.put("name", "李四");
        user2.put("age", 32);
        user2.put("email", "lisi@example.com");
        userDB.put(2L, user2);

        Map<String, Object> user3 = new HashMap<>();
        user3.put("id", 3L);
        user3.put("name", "王五");
        user3.put("age", 25);
        user3.put("email", "wangwu@example.com");
        userDB.put(3L, user3);
    }

    /**
     * 健康检查接口
     * GET /api/provider/health
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> result = new HashMap<>();
        result.put("status", "UP");
        result.put("service", "provider-service");
        result.put("port", 8070);
        result.put("timestamp", System.currentTimeMillis());
        return result;
    }

    /**
     * 获取单个用户信息
     * GET /api/provider/user/{id}
     */
    @GetMapping("/user/{id}")
    public Map<String, Object> getUser(@PathVariable Long id) {
        Map<String, Object> user = userDB.get(id);
        if (user == null) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "用户不存在");
            error.put("id", id);
            return error;
        }
        // 添加来源标记
        Map<String, Object> result = new HashMap<>(user);
        result.put("source", "provider-service");
        return result;
    }

    /**
     * 获取用户列表（分页）
     * GET /api/provider/users?page=1&size=10
     */
    @GetMapping("/users")
    public Map<String, Object> getUsers(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size) {

        List<Map<String, Object>> allUsers = new ArrayList<>(userDB.values());

        // 简单分页
        int from = Math.min((page - 1) * size, allUsers.size());
        int to = Math.min(from + size, allUsers.size());
        List<Map<String, Object>> pageUsers = allUsers.subList(from, to);

        Map<String, Object> result = new HashMap<>();
        result.put("data", pageUsers);
        result.put("total", allUsers.size());
        result.put("page", page);
        result.put("size", size);
        result.put("source", "provider-service");
        return result;
    }

    /**
     * 创建用户
     * POST /api/provider/user
     */
    @PostMapping("/user")
    public Map<String, Object> createUser(@RequestBody Map<String, Object> user) {
        Long id = userDB.size() + 1L;
        user.put("id", id);
        user.put("createdAt", new Date().toString());
        userDB.put(id, user);

        Map<String, Object> result = new HashMap<>();
        result.put("success", true);
        result.put("message", "用户创建成功");
        result.put("user", user);
        result.put("source", "provider-service");
        return result;
    }

    /**
     * 计算接口（演示带参数的 POST 请求）
     * POST /api/provider/calculate
     */
    @PostMapping("/calculate")
    public Map<String, Object> calculate(@RequestBody Map<String, Integer> params) {
        int a = params.getOrDefault("a", 0);
        int b = params.getOrDefault("b", 0);

        Map<String, Object> result = new HashMap<>();
        result.put("a", a);
        result.put("b", b);
        result.put("sum", a + b);
        result.put("multiply", a * b);
        result.put("source", "provider-service");
        return result;
    }

    /**
     * 回显接口
     * GET /api/provider/echo?message=hello
     */
    @GetMapping("/echo")
    public Map<String, String> echo(@RequestParam String message) {
        Map<String, String> result = new HashMap<>();
        result.put("message", message);
        result.put("from", "provider-service");
        result.put("timestamp", String.valueOf(System.currentTimeMillis()));
        return result;
    }
}
