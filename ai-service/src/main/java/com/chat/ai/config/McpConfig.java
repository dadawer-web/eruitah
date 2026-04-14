package com.chat.ai.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.mcp.client.McpClient;
import org.springframework.ai.mcp.client.McpSyncClient;
import org.springframework.ai.mcp.client.stdio.ServerParameters;
import org.springframework.ai.mcp.client.stdio.StdioClientTransport;
import org.springframework.ai.mcp.spec.McpSchema;
import org.springframework.ai.model.function.FunctionCallback;
import org.springframework.ai.model.function.FunctionCallbackWrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Function;

@Configuration
@Slf4j
public class McpConfig {

    @Bean
    public McpSyncClient mcpSyncClient() {
        log.info("[MCP] 正在初始化 MCP 客户端...");
        
        Path codesDir = Path.of("/tmp/408_codes");
        if (!Files.exists(codesDir)) {
            try {
                Files.createDirectories(codesDir);
                log.info("[MCP] 创建代码目录: {}", codesDir);
            } catch (IOException e) {
                log.warn("[MCP] 无法创建代码目录，MCP文件系统工具可能无法正常工作: {}", e.getMessage());
            }
        }
        
        ServerParameters serverParams = ServerParameters.builder("npx")
            .args("-y", "@modelcontextprotocol/server-filesystem@0.6.2", "/tmp/408_codes")
            .build();
        
        McpSyncClient client = McpClient.sync(new StdioClientTransport(serverParams));
        
        client.initialize();
        log.info("[MCP] MCP 客户端初始化完成");
        
        return client;
    }

    @Bean
    public FunctionCallback[] mcpFilesystemTools(McpSyncClient mcpSyncClient) {
        log.info("[MCP] 正在从 MCP Server 获取工具列表...");
        
        var toolsResult = mcpSyncClient.listTools();
        var tools = toolsResult.tools();
        
        log.info("[MCP] 发现 {} 个 MCP 工具:", tools.size());
        
        FunctionCallback[] toolCallbacks = new FunctionCallback[tools.size()];
        for (int i = 0; i < tools.size(); i++) {
            McpSchema.Tool tool = tools.get(i);
            log.info("[MCP]   - {} : {}", tool.name(), tool.description());
            
            toolCallbacks[i] = FunctionCallbackWrapper.builder(new McpToolFunction(mcpSyncClient, tool.name()))
                .withName(tool.name())
                .withDescription(tool.description())
                .build();
        }
        
        log.info("[MCP] 成功转换 {} 个工具回调", toolCallbacks.length);
        
        return toolCallbacks;
    }

    private static class McpToolFunction implements Function<Map<String, Object>, String> {
        private final McpSyncClient client;
        private final String toolName;

        McpToolFunction(McpSyncClient client, String toolName) {
            this.client = client;
            this.toolName = toolName;
        }

        @Override
        public String apply(Map<String, Object> arguments) {
            log.info("[MCP] 调用工具: {} 参数: {}", toolName, arguments);
            try {
                McpSchema.CallToolRequest request = new McpSchema.CallToolRequest(toolName, arguments);
                var result = client.callTool(request);
                if (result.content() != null && !result.content().isEmpty()) {
                    StringBuilder sb = new StringBuilder();
                    for (var content : result.content()) {
                        if (content instanceof McpSchema.TextContent textContent) {
                            sb.append(textContent.text());
                        }
                    }
                    log.info("[MCP] 工具 {} 返回: {}", toolName, sb.toString());
                    return sb.toString();
                }
                return "工具执行成功，无返回内容";
            } catch (Exception e) {
                log.error("[MCP] 工具 {} 调用失败", toolName, e);
                return "工具调用失败: " + e.getMessage();
            }
        }
    }
}
