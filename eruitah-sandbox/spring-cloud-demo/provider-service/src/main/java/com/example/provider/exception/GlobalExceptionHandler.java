package com.example.provider.exception;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import java.util.*;

/**
 * 全局异常处理器
 * 统一捕获 Controller 层异常，返回标准错误响应
 *
 * @RestControllerAdvice = @ControllerAdvice + @ResponseBody
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    /**
     * 处理参数异常
     */
    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Map<String, Object> handleIllegalArgument(IllegalArgumentException e) {
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("code", 400);
        error.put("message", "参数错误: " + e.getMessage());
        error.put("timestamp", System.currentTimeMillis());
        return error;
    }

    /**
     * 处理所有未捕获异常（兜底）
     */
    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Map<String, Object> handleException(Exception e) {
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("code", 500);
        error.put("message", "服务器内部错误: " + e.getMessage());
        error.put("timestamp", System.currentTimeMillis());
        return error;
    }
}
