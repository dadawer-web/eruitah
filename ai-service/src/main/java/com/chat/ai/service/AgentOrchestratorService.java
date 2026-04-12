package com.chat.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.QuestionAnswerAdvisor;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
public class AgentOrchestratorService {

    private final ObjectProvider<ChatClient.Builder> chatClientBuilderProvider;
    private final VectorStore vectorStore;

    private static final String ROUTER_SYSTEM_PROMPT = """
        你是一个意图识别专家。请分析用户的问题，判断其属于以下哪一类：
        
        1. 代码求助：用户需要编写、调试或理解代码，涉及编程语言、算法实现等
        2. 理论解答：用户询问计算机科学理论知识、考研相关问题、分数线、招生政策、最新资讯等需要查询或搜索的问题
        3. 日常闲聊：用户的问候、闲聊或与学习无关的内容
        
        【重要规则】：
        - 如果问题涉及"分数线"、"招生"、"政策"、"最新"、"今年"、"2024"、"2025"等时效性内容，必须归类为"理论解答"
        - 如果用户在问具体的事实性问题（即使需要联网搜索），归类为"理论解答"
        - 只有纯粹的打招呼、闲聊才归类为"日常闲聊"
        
        请只回复一个词：代码求助、理论解答 或 日常闲聊
        """;

    private static final String SOLVER_CODE_SYSTEM_PROMPT = """
        你是一位资深的编程导师，专门帮助计算机考研学生解决代码问题。
        你可以使用cppCompilerTool工具来编译和运行C++代码，获取真实的编译错误和运行结果。
        当用户给你代码让你检查Bug或问运行结果时，务必调用工具验证。
        请提供清晰的代码解释和实现建议。
        """;

    private static final String SOLVER_THEORY_SYSTEM_PROMPT = """
        你是一位资深的计算机考研辅导老师，精通数据结构、操作系统、计算机网络、数据库等408考试科目。
        
        你可以使用webSearchTool工具来搜索互联网上的最新信息，如最新的分数线、招生政策等实时数据。
        
        请严格基于检索到的知识库内容回答问题。如果知识库中有相关内容，请引用并详细解释。
        如果知识库中没有相关内容，请明确告知用户"知识库中暂无此内容"，然后根据你的知识给出参考答案。
        对于需要实时信息的问题（如分数线、招生政策等），请调用webSearchTool搜索最新信息。
        
        回答格式：
        1. 首先说明是否从知识库中找到了相关内容
        2. 如果有，引用知识库原文并解释
        3. 补充必要的背景知识
        """;

    private static final String SOLVER_CHAT_SYSTEM_PROMPT = """
        你是一个友好的AI学习助手。请用轻松愉快的方式与用户交流，鼓励他们学习。
        """;

    private static final String REVIEWER_SYSTEM_PROMPT = """
        你是一位严格的知识审核员，专门审核关于计算机考研的解答。
        
        【重要规则】你必须只输出最终答案，绝对禁止输出任何审核过程、审核意见、修改说明等内容！
        
        你的职责：
        1. 检查答案的准确性和严谨性
        2. 确保没有概念性错误
        3. 补充可能遗漏的重要知识点
        
        输出要求：
        - 如果答案准确，直接原样输出答案
        - 如果答案有小问题，修正后输出完整答案
        - 如果答案有严重错误，输出正确答案
        
        再次强调：你的输出将直接发送给用户，所以只输出最终答案，不要有任何审核过程的痕迹！
        """;

    public AgentOrchestratorService(ObjectProvider<ChatClient.Builder> chatClientBuilderProvider, VectorStore vectorStore) {
        this.chatClientBuilderProvider = chatClientBuilderProvider;
        this.vectorStore = vectorStore;
    }

    public AgentResult processUserQuery(String userMessage) {
        log.info("=== 开始多智能体工作流处理 ===");
        log.info("用户输入: {}", userMessage);

        String intent = routeIntent(userMessage);
        log.info("[Router] 意图识别结果: {}", intent);

        String draftAnswer = solve(userMessage, intent);
        log.info("[Solver] 初步解答长度: {} 字符", draftAnswer.length());

        String finalAnswer = reflect(userMessage, draftAnswer);
        log.info("[Reflection] 最终答案长度: {} 字符", finalAnswer.length());

        log.info("=== 多智能体工作流处理完成 ===");
        return new AgentResult(intent, draftAnswer, finalAnswer);
    }

    private String routeIntent(String userMessage) {
        log.debug("[Router] 开始意图识别...");
        
        ChatClient routerClient = chatClientBuilderProvider.getObject().build();
        
        String response = routerClient.prompt()
            .system(ROUTER_SYSTEM_PROMPT)
            .user(userMessage)
            .call()
            .content();
        
        String intent = response.trim();
        
        if (!intent.equals("代码求助") && !intent.equals("理论解答") && !intent.equals("日常闲聊")) {
            if (intent.contains("代码") || intent.contains("编程") || intent.contains("程序")) {
                intent = "代码求助";
            } else if (intent.contains("理论") || intent.contains("知识") || intent.contains("概念")) {
                intent = "理论解答";
            } else {
                intent = "日常闲聊";
            }
        }
        
        return intent;
    }

    private String solve(String userMessage, String intent) {
        log.debug("[Solver] 开始解答生成，意图: {}", intent);
        
        ChatClient solverClient;
        String systemPrompt;
        
        switch (intent) {
            case "代码求助":
                systemPrompt = SOLVER_CODE_SYSTEM_PROMPT;
                solverClient = chatClientBuilderProvider.getObject()
                    .defaultFunctions("cppCompilerTool")
                    .build();
                log.info("[Solver] 代码求助模式：已挂载 cppCompilerTool");
                break;
                
            case "理论解答":
                systemPrompt = SOLVER_THEORY_SYSTEM_PROMPT;
                
                List<Document> retrievedDocs = vectorStore.similaritySearch(userMessage);
                log.info("[RAG] 检索到 {} 个相关文档", retrievedDocs.size());
                for (int i = 0; i < retrievedDocs.size(); i++) {
                    Document doc = retrievedDocs.get(i);
                    log.info("[RAG] 文档[{}]: source={}, content长度={}", 
                        i, doc.getMetadata().get("source_file"), doc.getContent().length());
                }
                
                solverClient = chatClientBuilderProvider.getObject()
                    .defaultAdvisors(new QuestionAnswerAdvisor(vectorStore))
                    .defaultFunctions("webSearchTool")
                    .build();
                log.info("[Solver] 理论解答模式：已挂载 RAG + webSearchTool");
                break;
                
            case "日常闲聊":
            default:
                systemPrompt = SOLVER_CHAT_SYSTEM_PROMPT;
                solverClient = chatClientBuilderProvider.getObject().build();
                break;
        }
        
        return solverClient.prompt()
            .system(systemPrompt)
            .user(userMessage)
            .call()
            .content();
    }

    private String reflect(String userMessage, String draftAnswer) {
        log.debug("[Reflection] 开始审查反思...");
        
        ChatClient reviewerClient = chatClientBuilderProvider.getObject().build();
        
        String reviewPrompt = String.format("""
            原始问题：%s
            
            待审核的答案：
            %s
            
            请审核以上答案。
            """, userMessage, draftAnswer);
        
        return reviewerClient.prompt()
            .system(REVIEWER_SYSTEM_PROMPT)
            .user(reviewPrompt)
            .call()
            .content();
    }

    public record AgentResult(
        String intent,
        String draftAnswer,
        String finalAnswer
    ) {}
}
