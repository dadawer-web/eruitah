package com.chat.ai.exception;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public enum ErrorCode {

    BAD_REQUEST(400, "请求参数错误"),
    INTERNAL_ERROR(500, "服务器内部错误"),
    AI_SERVICE_ERROR(7003, "AI服务调用失败"),
    RATE_LIMIT_EXCEEDED(8001, "请求过于频繁，请稍后再试"),
    STRUCTURED_OUTPUT_PARSE_FAILED(8002, "结构化输出解析失败");

    private final Integer code;
    private final String message;
}
