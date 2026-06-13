package com.example.consumer.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web 配置类
 *
 * 1. CORS 跨域配置：允许前端从不同端口/域名调用 API
 * 2. 首页重定向：访问 / 自动跳转到 index.html
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    /**
     * 配置 CORS（跨域资源共享）
     * 开发时前端可能在不同端口运行，需要允许跨域请求
     */
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOriginPatterns("*")
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                .allowCredentials(true)
                .maxAge(3600);
    }

    /**
     * 首页重定向
     * 访问 http://localhost:8080/ 自动跳转到 http://localhost:8080/index.html
     */
    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/").setViewName("forward:/index.html");
    }
}
