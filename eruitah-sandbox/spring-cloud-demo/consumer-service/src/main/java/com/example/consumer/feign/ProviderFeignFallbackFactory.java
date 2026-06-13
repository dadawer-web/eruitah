package com.example.consumer.feign;

import feign.hystrix.FallbackFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import java.util.*;

/**
 * Feign 降级工厂类（熔断降级）
 *
 * 当 provider-service 不可用时（超时、异常、宕机），
 * 会触发降级，调用此工厂的 create() 方法返回兜底数据。
 *
 * 降级策略：
 *   - 避免级联故障（一个服务挂了导致整个链路崩溃）
 *   - 返回友好的默认数据，而不是直接报错
 */
@Component
public class ProviderFeignFallbackFactory implements FallbackFactory<ProviderFeignClient> {

    private static final Logger log = LoggerFactory.getLogger(ProviderFeignFallbackFactory.class);

    @Override
    public ProviderFeignClient create(Throwable cause) {
        log.error("🔴 Provider Service 调用失败，触发降级: {}", cause.getMessage());

        return new ProviderFeignClient() {

            @Override
            public Map<String, Object> health() {
                Map<String, Object> fallback = new LinkedHashMap<>();
                fallback.put("status", "DOWN");
                fallback.put("service", "provider-service");
                fallback.put("message", "服务暂时不可用，已降级处理");
                fallback.put("error", cause.getMessage());
                return fallback;
            }

            @Override
            public Map<String, Object> getUser(Long id) {
                Map<String, Object> fallback = new LinkedHashMap<>();
                fallback.put("id", id);
                fallback.put("name", "降级用户");
                fallback.put("message", "Provider 服务不可用，返回默认数据");
                return fallback;
            }

            @Override
            public Map<String, Object> getUsers(int page, int size) {
                Map<String, Object> fallback = new LinkedHashMap<>();
                fallback.put("data", Collections.emptyList());
                fallback.put("message", "Provider 服务不可用，返回空列表");
                return fallback;
            }

            @Override
            public Map<String, Object> createUser(Map<String, Object> user) {
                Map<String, Object> fallback = new LinkedHashMap<>();
                fallback.put("success", false);
                fallback.put("message", "Provider 服务不可用，创建用户失败");
                return fallback;
            }

            @Override
            public Map<String, Object> calculate(Map<String, Integer> params) {
                Map<String, Object> fallback = new LinkedHashMap<>();
                fallback.put("message", "Provider 服务不可用，无法计算");
                return fallback;
            }

            @Override
            public Map<String, String> echo(String message) {
                Map<String, String> fallback = new LinkedHashMap<>();
                fallback.put("message", "降级回显: " + message);
                fallback.put("from", "consumer-service-fallback");
                return fallback;
            }
        };
    }
}
