package com.chat.ai.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.model.function.FunctionCallback;
import org.springframework.ai.model.function.FunctionCallbackWrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Description;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

@Slf4j
@Configuration
public class CodeSandboxToolConfig {

    private static final int TIMEOUT_SECONDS = 3;
    private static final String TEMP_DIR = "/tmp";

    public record CodeRequest(String cppCode) {}

    @Bean
    public FunctionCallback cppCompilerToolCallback() {
        return FunctionCallbackWrapper.builder(new CppCompilerFunction())
            .withName("cppCompilerTool")
            .withDescription("C++代码沙盒编译器。当用户发给你一段C++代码让你检查Bug，或者问你代码的运行结果时，你必须调用此工具。将用户的代码传进来，我会帮你编译并运行，返回真实的报错或输出结果给你。")
            .build();
    }

    private static class CppCompilerFunction implements Function<CodeRequest, String> {
        @Override
        public String apply(CodeRequest request) {
            log.info("=== cppCompilerTool 被调用 ===");
            log.info("收到的代码长度: {}", request.cppCode() == null ? 0 : request.cppCode().length());
            
            if (request.cppCode() == null || request.cppCode().trim().isEmpty()) {
                log.warn("代码为空，返回错误");
                return "编译失败：代码为空";
            }

            String fileId = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
            String cppFileName = "cpp_" + fileId + ".cpp";
            String executableName = "cpp_" + fileId;
            
            Path cppFilePath = Paths.get(TEMP_DIR, cppFileName);
            Path executablePath = Paths.get(TEMP_DIR, executableName);

            log.info("临时文件路径: {}", cppFilePath);
            log.info("可执行文件路径: {}", executablePath);

            try {
                Files.writeString(cppFilePath, request.cppCode());
                log.info("代码已写入临时文件");
                
                ProcessBuilder compilePb = new ProcessBuilder(
                    "g++", 
                    cppFilePath.toString(), 
                    "-o", 
                    executablePath.toString()
                );
                compilePb.redirectErrorStream(true);
                
                log.info("开始编译...");
                Process compileProcess = compilePb.start();
                boolean compileFinished = compileProcess.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS);
                
                if (!compileFinished) {
                    compileProcess.destroyForcibly();
                    log.error("编译超时");
                    return "编译超时：编译过程超过 " + TIMEOUT_SECONDS + " 秒";
                }
                
                if (compileProcess.exitValue() != 0) {
                    String compileError = readProcessOutput(compileProcess);
                    log.error("编译失败: {}", compileError);
                    return "编译失败：\n" + compileError;
                }
                
                log.info("编译成功，开始运行...");
                
                ProcessBuilder runPb = new ProcessBuilder(executablePath.toString());
                runPb.redirectErrorStream(true);
                
                Process runProcess = runPb.start();
                boolean runFinished = runProcess.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS);
                
                if (!runFinished) {
                    runProcess.destroyForcibly();
                    log.error("运行超时");
                    return "运行超时：程序执行超过 " + TIMEOUT_SECONDS + " 秒（可能存在死循环）";
                }
                
                String output = readProcessOutput(runProcess);
                log.info("程序运行完成，输出: {}", output);
                
                if (runProcess.exitValue() != 0) {
                    return "程序异常退出（退出码：" + runProcess.exitValue() + "）：\n" + output;
                }
                
                String result = "执行成功，输出结果：\n" + (output.isEmpty() ? "（无输出）" : output);
                log.info("=== cppCompilerTool 执行完成 ===");
                return result;
                
            } catch (Exception e) {
                log.error("沙盒执行异常", e);
                return "沙盒执行异常: " + e.getMessage();
            } finally {
                try {
                    Files.deleteIfExists(cppFilePath);
                    Files.deleteIfExists(executablePath);
                    log.debug("临时文件已清理");
                } catch (Exception ignored) {
                }
            }
        }

        private String readProcessOutput(Process process) throws Exception {
            StringBuilder output = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(process.getInputStream()))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    output.append(line).append("\n");
                }
            }
            return output.toString().trim();
        }
    }
}
