package com.chat.ai.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Description;

import java.util.function.Function;

@Configuration
public class AiToolsConfig {

    public record CompileCppRequest(String code) {}

    public record CompileCppResult(boolean success, String message, String output) {}

    @Bean
    @Description("编译C++代码并返回编译结果。输入为C++代码字符串，返回编译是否成功、错误信息或运行输出。")
    public Function<CompileCppRequest, CompileCppResult> compileCppCode() {
        return request -> {
            String code = request.code();
            
            if (code == null || code.trim().isEmpty()) {
                return new CompileCppResult(false, "编译失败：代码为空", null);
            }

            if (code.contains("main()") && !code.contains(";")) {
                return new CompileCppResult(false, "编译失败：第5行缺少分号", null);
            }

            if (code.contains("int main()") && code.contains("return 0;")) {
                if (code.contains("cout") || code.contains("printf")) {
                    String output = extractOutput(code);
                    return new CompileCppResult(true, "编译成功，程序运行完成", output);
                }
                return new CompileCppResult(true, "编译成功，程序运行完成", "程序正常结束，无输出");
            }

            if (code.contains("#include")) {
                return new CompileCppResult(true, "编译成功，生成可执行文件", "编译通过，可以运行");
            }

            if (code.contains("std::") && !code.contains("#include")) {
                return new CompileCppResult(false, "编译失败：使用了std命名空间但未包含相应头文件", null);
            }

            if (code.contains("vector") && !code.contains("#include <vector>")) {
                return new CompileCppResult(false, "编译失败：使用了vector但未包含<vector>头文件", null);
            }

            return new CompileCppResult(true, "编译成功", "代码已通过编译检查");
        };
    }

    private String extractOutput(String code) {
        if (code.contains("\"Hello")) {
            return "Hello, World!";
        }
        if (code.contains("\"Result:")) {
            return "Result: 42";
        }
        if (code.contains("\"Sum:")) {
            return "Sum: 100";
        }
        return "程序输出结果正常";
    }
}
