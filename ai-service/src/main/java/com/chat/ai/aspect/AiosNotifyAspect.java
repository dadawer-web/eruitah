package com.chat.ai.aspect;

import com.chat.ai.annotation.AiosNotify;
import com.chat.ai.config.RabbitEventBusConfig;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.HashMap;
import java.util.Map;

/**
 * AIOS 事件通知切面 — 无侵入式 AOP
 *
 * 拦截所有标记了 @AiosNotify 的方法，在方法成功返回后（@AfterReturning），
 * 自动向 RabbitMQ 的 aios_exchange 推送 notify 事件，驱动前端 C++ 桌宠弹出气泡。
 *
 * 动态路由键: aios.events.user_{userId}.{source}
 * userId 提取策略（按优先级）:
 *   1. 方法参数中名为 "userId" / "user_id" / "uid" 的参数值
 *   2. 第一个 Long / Integer / String 类型的参数
 *   3. 兜底值 "anonymous"
 */
@Slf4j
@Aspect
@Component
public class AiosNotifyAspect {

    private final RabbitTemplate rabbitTemplate;

    public AiosNotifyAspect(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @AfterReturning("@annotation(aiosNotify)")
    public void afterAiosNotify(JoinPoint joinPoint, AiosNotify aiosNotify) {
        String source = aiosNotify.source();
        String successMsg = aiosNotify.successMsg();

        // 提取 userId
        Object userId = extractUserId(joinPoint);
        String routingKey = "aios.events.user_" + userId + "." + source;

        // 发布 notify 事件
        publishEvent(routingKey, source, successMsg);
    }

    // ── 事件发布 ──

    private void publishEvent(String routingKey, String source, String message) {
        try {
            Map<String, Object> payload = new HashMap<>();
            payload.put("action", "notify");
            payload.put("source", source);
            payload.put("msg", message);
            payload.put("timestamp", System.currentTimeMillis());

            // 直接发送 Map，由 Jackson2JsonMessageConverter 序列化一次为 JSON 对象
            // 避免先 toJson 再被 converter 二次序列化为 JSON 字符串（双重编码）
            rabbitTemplate.convertAndSend(
                    RabbitEventBusConfig.EXCHANGE_NAME,
                    routingKey,
                    payload
            );

            log.debug("[AiosNotify] → {}: action=notify, msg={}", routingKey, message);

        } catch (Exception e) {
            // 发布失败不阻断业务
            log.error("[AiosNotify] 事件发布失败 (routingKey={}): {}", routingKey, e.getMessage());
        }
    }

    // ── userId 智能提取 ──

    private Object extractUserId(JoinPoint joinPoint) {
        MethodSignature signature = (MethodSignature) joinPoint.getSignature();
        Method method = signature.getMethod();
        Parameter[] parameters = method.getParameters();
        Object[] args = joinPoint.getArgs();

        // 策略 1: 从方法参数名中查找 userId / user_id / uid
        for (int i = 0; i < parameters.length; i++) {
            String paramName = parameters[i].getName().toLowerCase();
            if (paramName.equals("userid") || paramName.equals("user_id") || paramName.equals("uid")) {
                return args[i];
            }
        }

        // 策略 2: 第一个 Long / Integer / String 类型的参数
        for (Object arg : args) {
            if (arg instanceof Long || arg instanceof Integer || arg instanceof String) {
                return arg;
            }
        }

        // 策略 3: 兜底
        return "anonymous";
    }
}
