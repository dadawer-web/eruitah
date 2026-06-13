package com.example.consumer.config;

import feign.Logger;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Feign 全局配置类
 *
 * 可以配置：
 *   - 日志级别（NONE/BASIC/HEADERS/FULL）
 *   - 请求拦截器（添加统一请求头）
 *   - 编解码器
 *   - 超时时间
 */
@Configuration
public class FeignConfig {

    /**
     * Feign 日志级别
     *   NONE: 不记录（默认）
     *   BASIC: 记录请求方法、URL、响应状态码、执行时间
     *   HEADERS: 在 BASIC 基础上，记录请求和响应的头信息
     *   FULL: 记录所有，包括头信息、体信息、元数据
     */
    @Bean
    public Logger.Level feignLoggerLevel() {
        return Logger.Level.FULL;
    }
}
