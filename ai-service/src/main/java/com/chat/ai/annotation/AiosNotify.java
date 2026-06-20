package com.chat.ai.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * AIOS 全局事件通知注解（无侵入式 AOP）
 *
 * 标记在 Service 方法上，方法成功返回后自动向 RabbitMQ 事件总线推送通知，
 * 驱动前端 C++ 桌宠弹出气泡提示。
 *
 * Routing Key: aios.events.user_{userId}.{source}
 * Payload: {"action": "notify", "message": "..."}
 *
 * 用法:
 *   @AiosNotify(source = "farm_service", successMsg = "番茄成熟啦，快来收割！")
 *   public void harvestCrops(Long userId, Long plotId) { ... }
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AiosNotify {

    /** 事件来源模块（如 "farm_service", "knowledge_base", "ai_service"） */
    String source();

    /** 方法成功返回后的提醒文本，会显示在桌宠气泡中 */
    String successMsg();
}
