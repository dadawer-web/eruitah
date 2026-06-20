package com.chat.ai.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.ExchangeBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ 配置 — AIOS 事件总线
 *
 * 声明 aios_exchange (topic 类型)，供 @AiosNotify 切面向其发布事件。
 * C++ 桌面端通过 MQTT 插件订阅 aios.events.user_{userId}.# 接收消息。
 */
@Configuration
public class RabbitEventBusConfig {

    public static final String EXCHANGE_NAME = "amq.topic"; // RabbitMQ MQTT 插件默认交换机

    @Bean
    public TopicExchange aiosExchange() {
        return ExchangeBuilder.topicExchange(EXCHANGE_NAME)
                .durable(true)
                .build();
    }

    @Bean
    public MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
