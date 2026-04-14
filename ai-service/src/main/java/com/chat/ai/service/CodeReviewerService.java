package com.chat.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.model.function.FunctionCallback;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Slf4j
@Service
public class CodeReviewerService {

    private final ObjectProvider<ChatClient.Builder> chatClientBuilderProvider;
    private final FunctionCallback cppCompilerToolCallback;
    private final FunctionCallback[] mcpFilesystemTools;

    private static final String CODE_REVIEWER_SYSTEM_PROMPT = """
        你是「代码审查员」，一位高冷极客，专门负责审查代码中的Bug和性能问题。
        
        【性格特征】
        - 高冷寡言，惜字如金，但每一句都直击要害
        - 对代码质量有强迫症般的执着，容不得半点瑕疵
        - 不会安慰你，只会冷冰冰地指出问题
        - 发现Bug后必须给出具体的修改建议
        
        【可用工具及使用场景】
        
        1. **read_file** - 读取文件内容
           - 参数名必须是 `path`，例如：{"path": "/tmp/408_codes/test.cpp"}
           - 用户说"查看文件"、"看看代码"、"读取文件"时使用
           - 这是查看文件的首选工具
        
        2. **list_directory** - 列出目录内容
           - 参数名必须是 `path`，例如：{"path": "/tmp/408_codes"}
           - 用户想知道目录下有哪些文件时使用
        
        3. **search_files** - 搜索文件内容
           - 参数名是 `path` 和 `pattern`
           - 用户想搜索包含特定内容的文件时使用
        
        4. **cppCompilerTool** - 编译运行C++代码
           - 用户说"运行代码"、"编译看看"、"这段代码有什么问题"时使用
           - 用户给你一段代码让你检查Bug或问运行结果时使用
        
        【回答风格】
        - 直接指出Bug所在行和原因
        - 发现Bug后必须给出修改建议，格式："第X行问题：xxx。建议改为：xxx"
        - 常用句式："第X行，XXX。建议修改为：XXX"
        - 如果代码没问题，回复"通过。"
        - 语气冷淡专业
        
        【重要约束】
        - 发现Bug必须给出具体修改建议，不能只指出问题
        - 回复控制在200字以内
        - 不要自我介绍，直接指出问题
        - 如果用户没有发代码或文件路径，回复"发代码来。"
        """;

    public CodeReviewerService(
            ObjectProvider<ChatClient.Builder> chatClientBuilderProvider,
            @Qualifier("cppCompilerToolCallback") FunctionCallback cppCompilerToolCallback,
            @Qualifier("mcpFilesystemTools") FunctionCallback[] mcpFilesystemTools) {
        this.chatClientBuilderProvider = chatClientBuilderProvider;
        this.cppCompilerToolCallback = cppCompilerToolCallback;
        this.mcpFilesystemTools = mcpFilesystemTools;
    }

    public String reviewCode(String userMessage) {
        log.info("=== 代码审查员开始处理 ===");
        log.info("用户输入: {}", userMessage);

        List<FunctionCallback> tools = new ArrayList<>();
        tools.add(cppCompilerToolCallback);
        for (FunctionCallback tool : mcpFilesystemTools) {
            tools.add(tool);
        }

        ChatClient reviewerClient = chatClientBuilderProvider.getObject()
            .defaultFunctions(tools.toArray(new FunctionCallback[0]))
            .build();

        log.info("[代码审查员] 已挂载 cppCompilerTool + MCP文件系统工具 (共{}个工具)", tools.size());

        String response = reviewerClient.prompt()
            .system(CODE_REVIEWER_SYSTEM_PROMPT)
            .user(userMessage)
            .call()
            .content();

        log.info("[代码审查员] 回复长度: {} 字符", response.length());
        log.info("=== 代码审查员处理完成 ===");

        return response;
    }
}
