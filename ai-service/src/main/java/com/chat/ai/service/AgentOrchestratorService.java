package com.chat.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.document.Document;
import org.springframework.ai.model.function.FunctionCallback;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

@Slf4j
@Service
public class AgentOrchestratorService {

    private final ObjectProvider<ChatClient.Builder> chatClientBuilderProvider;
    private final VectorStore vectorStore;
    private final FunctionCallback cppCompilerToolCallback;
    private final ExamStateManager examStateManager;
    private final QueryRewriteService queryRewriteService;
    private final HybridRetrievalService hybridRetrievalService;
    private final RerankerService rerankerService;
    private final GraphExamService graphExamService;

    private static final Set<String> EXAM_KEYWORDS = Set.of(
        "刷题", "抽卡", "考考我", "测试", "出题", "做题", "测验", "考试", "练习",
        "出一道", "来一道", "给我出", "出个题", "题目", "考我"
    );

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
        
        你可以使用 cppCompilerTool 工具来编译和运行C++代码，获取真实的编译错误和运行结果。
        
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

    private static final String EXAM_QUESTION_EXTRACTOR_PROMPT = """
        你是一个408考研出题专家。你的任务是从给定的知识材料中，提取出一道高质量的408选择题。
        
        要求：
        1. 必须基于提供的知识材料出题，不能凭空捏造
        2. 题目格式为选择题，包含4个选项(A/B/C/D)
        3. 必须同时给出标准答案和详细解析
        4. 题目要有一定难度，能考察对概念的深入理解
        
        【JSON格式要求 - 极其重要】：
        - 只输出JSON，不要有任何其他文字
        - JSON字符串中不能包含双引号，请用单引号代替或省略
        - JSON字符串中不能包含换行符，请用空格代替
        - 确保JSON格式完全正确，可以被解析器解析
        
        输出格式示例：
        {"question":"TCP建立连接需要几次握手","optionA":"1次","optionB":"2次","optionC":"3次","optionD":"4次","answer":"C","analysis":"TCP采用三次握手建立连接，确保双方收发能力正常。"}
        """;

    private static final String GRADING_SYSTEM_PROMPT = """
        你是一个无情的408判卷机器。你将严格对比用户的回答和标准答案，给出精准的评分与纠错。
        
        评分规则：
        1. 如果用户选择了正确选项且理由充分：90-100分
        2. 如果用户选择了正确选项但理由不充分或有误：70-89分
        3. 如果用户选择了错误选项但分析过程有部分正确：40-69分
        4. 如果用户选择了错误选项且分析完全错误：0-39分
        
        输出格式（严格遵守）：
        【得分】XX/100
        【判定】正确/错误
        【正确答案】X. 选项内容
        【你的分析】用户回答中的亮点或问题
        【详细解析】标准答案的完整解析
        """;

    private static final String EXAM_PRESET_FALLBACK = """
        {"question":"TCP建立连接需要几次握手？","optionA":"1次","optionB":"2次","optionC":"3次","optionD":"4次","answer":"C","analysis":"TCP建立连接采用三次握手（Three-way Handshake）：第一次握手，客户端发送SYN包；第二次握手，服务器返回SYN+ACK包；第三次握手，客户端发送ACK包确认。三次握手确保了双方都具备收发能力，防止已失效的连接请求到达服务器而产生错误。"}
        """;

    private static final String EXAM_PRESET_FALLBACK_2 = """
        {"question":"在二叉树的遍历中，已知前序遍历序列为ABDCE，中序遍历序列为BDAEC，则后序遍历序列为？","optionA":"DBECA","optionB":"DBEAC","optionC":"DBECA","optionD":"DEBCA","answer":"A","analysis":"由前序ABDCE知根为A，中序BDAEC中A左边BD为左子树、右边EC为右子树。左子树前序BD、中序BD，故B为左子树根，D为B的右孩子。右子树前序CE、中序EC，故C为右子树根，E为C的左孩子。因此后序遍历为：左子树DB + 右子树EC + 根A = DBECA。"}
        """;

    public AgentOrchestratorService(
            ObjectProvider<ChatClient.Builder> chatClientBuilderProvider,
            VectorStore vectorStore,
            @Qualifier("cppCompilerToolCallback") FunctionCallback cppCompilerToolCallback,
            ExamStateManager examStateManager,
            QueryRewriteService queryRewriteService,
            HybridRetrievalService hybridRetrievalService,
            RerankerService rerankerService,
            GraphExamService graphExamService) {
        this.chatClientBuilderProvider = chatClientBuilderProvider;
        this.vectorStore = vectorStore;
        this.cppCompilerToolCallback = cppCompilerToolCallback;
        this.examStateManager = examStateManager;
        this.queryRewriteService = queryRewriteService;
        this.hybridRetrievalService = hybridRetrievalService;
        this.rerankerService = rerankerService;
        this.graphExamService = graphExamService;
    }

    public AgentResult processUserQuery(String userMessage) {
        return processUserQuery(null, userMessage);
    }

    public AgentResult processUserQuery(Integer userId, String userMessage) {
        log.info("=== 开始多智能体工作流处理 ===");
        log.info("用户输入: {}, userId: {}", userMessage, userId);

        if (userId != null && examStateManager.isInExamState(userId)) {
            log.info("[ExamSkill] 检测到用户 {} 处于考试状态，路由到判卷工作流", userId);
            String gradingResult = executeGradingWorkflow(userId, userMessage);
            return new AgentResult("技能:判卷", gradingResult, gradingResult);
        }

        if (userId != null && detectExamIntent(userMessage)) {
            log.info("[ExamSkill] 检测到出题意图，路由到出题工作流, userId: {}", userId);
            String examResult = executeExamSkillWorkflow(userId, userMessage);
            return new AgentResult("技能:出题", examResult, examResult);
        }

        String intent = routeIntent(userMessage);
        log.info("[Router] 意图识别结果: {}", intent);

        String draftAnswer = solve(userMessage, intent);
        log.info("[Solver] 初步解答长度: {} 字符", draftAnswer.length());

        String finalAnswer = reflect(userMessage, draftAnswer);
        log.info("[Reflection] 最终答案长度: {} 字符", finalAnswer.length());

        log.info("=== 多智能体工作流处理完成 ===");
        return new AgentResult(intent, draftAnswer, finalAnswer);
    }

    private boolean detectExamIntent(String userMessage) {
        String lowerMessage = userMessage.toLowerCase();
        for (String keyword : EXAM_KEYWORDS) {
            if (lowerMessage.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private String executeExamSkillWorkflow(Integer userId, String userMessage) {
        log.info("[ExamSkill:出题] ========== 开始出题工作流 ==========");
        log.info("[ExamSkill:出题] userId: {}, message: {}", userId, userMessage);

        String graphBasedConcept = null;
        String graphContext = "";
        
        if (userId != null) {
            log.info("[ExamSkill:图谱分析] 开始分析用户 {} 的认知图谱...", userId);
            
            graphBasedConcept = graphExamService.selectNextQuestionConcept(String.valueOf(userId)).orElse(null);
            
            if (graphBasedConcept != null) {
                log.info("[ExamSkill:图谱驱动] ✅ 根据认知图谱选择薄弱考点: {}", graphBasedConcept);
                
                List<GraphExamService.WeakPoint> weakPoints = graphExamService.findWeakPointsForPrerequisiteChain(String.valueOf(userId));
                if (!weakPoints.isEmpty()) {
                    StringBuilder sb = new StringBuilder();
                    sb.append("【图谱分析】用户当前薄弱考点：\n");
                    for (GraphExamService.WeakPoint wp : weakPoints) {
                        sb.append(String.format("- %s (掌握度: %.0f%%, 影响 %d 个后续考点)\n", 
                            wp.conceptName(), wp.score() * 100, wp.impactCount()));
                    }
                    graphContext = sb.toString();
                    log.info("[ExamSkill:图谱上下文] \n{}", graphContext);
                }
            } else {
                log.info("[ExamSkill:图谱分析] 用户暂无图谱数据，将使用RAG知识库出题");
            }
        }

        log.info("[ExamSkill:RAG检索] 开始从知识库召回考题...");
        ExamQuestion question = retrieveQuestionFromKnowledge(userMessage, graphBasedConcept, graphContext);
        log.info("[ExamSkill:出题] ✅ 知识召回完成, 题目: {}", question.question());

        ExamStateManager.ExamContext context = new ExamStateManager.ExamContext(
            question.subject(),
            question.question(),
            question.standardAnswer(),
            question.source()
        );
        examStateManager.enterExamState(userId, context);
        log.info("[ExamSkill:出题] 已为用户 {} 设置考试状态", userId);

        String examPrompt = buildExamPrompt(question);
        if (graphBasedConcept != null) {
            examPrompt += String.format("\n\n🎯 图谱定向：本题针对你的薄弱考点「%s」", graphBasedConcept);
        }
        log.info("[ExamSkill:出题] ========== 出题工作流完成 ==========");
        return examPrompt;
    }

    private ExamQuestion retrieveQuestionFromKnowledge(String userMessage) {
        return retrieveQuestionFromKnowledge(userMessage, null, "");
    }

    private ExamQuestion retrieveQuestionFromKnowledge(String userMessage, String targetConcept) {
        return retrieveQuestionFromKnowledge(userMessage, targetConcept, "");
    }

    private ExamQuestion retrieveQuestionFromKnowledge(String userMessage, String targetConcept, String graphContext) {
        log.info("[ExamSkill:知识召回] 开始从知识库召回考题... 目标考点: {}", targetConcept);

        String effectiveQuery = targetConcept != null ? 
            "请出一道关于" + targetConcept + "的408考研选择题" : userMessage;

        try {
            List<String> subQueries = queryRewriteService.rewriteQuery(effectiveQuery);
            List<Document> candidateDocs = hybridRetrievalService.hybridSearch(subQueries);
            
            String rerankQuery = targetConcept != null ? targetConcept : 
                (subQueries.size() > 1 ? subQueries.get(1) : userMessage);
            log.info("[ExamSkill:知识召回] 使用子问题进行重排: {}", rerankQuery);
            
            List<Document> rerankedDocs = rerankerService.rerank(rerankQuery, candidateDocs);
            log.info("[ExamSkill:知识召回] 工业级混合检索召回 {} 个文档（重排后）", rerankedDocs.size());

            if (!rerankedDocs.isEmpty()) {
                Document topDoc = rerankedDocs.get(0);
                String knowledgeContent = topDoc.getContent();
                String source = (String) topDoc.getMetadata().getOrDefault("source", "408考研综合");
                String topic = (String) topDoc.getMetadata().getOrDefault("topic", "综合");

                String combinedContext = knowledgeContent;
                if (!graphContext.isEmpty()) {
                    combinedContext = graphContext + "\n【RAG知识库】\n" + knowledgeContent;
                    log.info("[ExamSkill:综合出题] 已整合图谱上下文和RAG知识库");
                }

                for (int attempt = 1; attempt <= 2; attempt++) {
                    log.info("[ExamSkill:出题] 第{}次尝试生成题目...", attempt);
                    
                    ChatClient extractorClient = chatClientBuilderProvider.getObject().build();
                    String prompt = "用户请求：" + userMessage + "\n\n";
                    if (targetConcept != null) {
                        prompt += "【重点考点】" + targetConcept + "\n\n";
                    }
                    prompt += "请基于以下综合材料出一道408选择题：\n\n" + combinedContext;
                    
                    String extractionResult = extractorClient.prompt()
                        .system(EXAM_QUESTION_EXTRACTOR_PROMPT)
                        .user(prompt)
                        .call()
                        .content();

                    ExamQuestion parsed = parseExamQuestion(extractionResult, source, topic);
                    if (parsed != null) {
                        log.info("[ExamSkill:出题] 第{}次尝试成功", attempt);
                        return parsed;
                    }
                }
                
                log.warn("[ExamSkill:出题] JSON解析连续失败，使用知识内容直接生成简单题目");
                return createSimpleQuestionFromKnowledge(knowledgeContent, source, topic);
            }
        } catch (Exception e) {
            log.warn("[ExamSkill:知识召回] RAG出题失败: {}", e.getMessage());
        }

        return getPresetQuestion();
    }

    private ExamQuestion createSimpleQuestionFromKnowledge(String knowledgeContent, String source, String topic) {
        String question = "以下关于" + topic + "的说法，哪个是正确的？";
        String optionA = "选项A（请参考知识库内容）";
        String optionB = "选项B（请参考知识库内容）";
        String optionC = "选项C（正确答案）";
        String optionD = "选项D（请参考知识库内容）";
        
        String standardAnswer = String.format("正确答案：C\n选项内容：%s\n详细解析：基于知识库内容，%s",
            optionC, knowledgeContent.length() > 200 ? knowledgeContent.substring(0, 200) + "..." : knowledgeContent);
        
        String questionStem = String.format("%s\nA. %s\nB. %s\nC. %s\nD. %s",
            question, optionA, optionB, optionC, optionD);
        
        return new ExamQuestion(topic, questionStem, standardAnswer, source);
    }

    private ExamQuestion parseExamQuestion(String jsonStr, String source, String topic) {
        try {
            String cleaned = jsonStr.trim();
            if (cleaned.startsWith("```json")) {
                cleaned = cleaned.substring(7);
            }
            if (cleaned.startsWith("```")) {
                cleaned = cleaned.substring(3);
            }
            if (cleaned.endsWith("```")) {
                cleaned = cleaned.substring(0, cleaned.length() - 3);
            }
            cleaned = cleaned.trim();

            int jsonStart = cleaned.indexOf("{");
            int jsonEnd = cleaned.lastIndexOf("}");
            if (jsonStart >= 0 && jsonEnd > jsonStart) {
                cleaned = cleaned.substring(jsonStart, jsonEnd + 1);
            }

            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            mapper.configure(com.fasterxml.jackson.core.JsonParser.Feature.ALLOW_UNQUOTED_CONTROL_CHARS, true);
            mapper.configure(com.fasterxml.jackson.core.JsonParser.Feature.ALLOW_BACKSLASH_ESCAPING_ANY_CHARACTER, true);
            
            var node = mapper.readTree(cleaned);

            String question = node.has("question") ? node.get("question").asText() : "题目解析失败";
            String optionA = node.has("optionA") ? node.get("optionA").asText() : "选项A";
            String optionB = node.has("optionB") ? node.get("optionB").asText() : "选项B";
            String optionC = node.has("optionC") ? node.get("optionC").asText() : "选项C";
            String optionD = node.has("optionD") ? node.get("optionD").asText() : "选项D";
            String answer = node.has("answer") ? node.get("answer").asText() : "A";
            String analysis = node.has("analysis") ? node.get("analysis").asText() : "暂无解析";

            String standardAnswer = String.format("正确答案：%s\n选项内容：%s\n详细解析：%s",
                answer, getOptionContent(answer, optionA, optionB, optionC, optionD), analysis);

            String questionStem = String.format("%s\nA. %s\nB. %s\nC. %s\nD. %s",
                question, optionA, optionB, optionC, optionD);

            return new ExamQuestion(topic, questionStem, standardAnswer, source);
        } catch (Exception e) {
            log.warn("[ExamSkill] 解析出题结果失败: {}, 原始内容前200字符: {}", e.getMessage(), 
                jsonStr.length() > 200 ? jsonStr.substring(0, 200) : jsonStr);
            return null;
        }
    }

    private String getOptionContent(String answer, String a, String b, String c, String d) {
        return switch (answer.toUpperCase()) {
            case "A" -> a;
            case "B" -> b;
            case "C" -> c;
            case "D" -> d;
            default -> "未知";
        };
    }

    private ExamQuestion getPresetQuestion() {
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            boolean useSecond = Math.random() > 0.5;
            String json = useSecond ? EXAM_PRESET_FALLBACK_2 : EXAM_PRESET_FALLBACK;
            var node = mapper.readTree(json);

            String question = node.get("question").asText();
            String optionA = node.get("optionA").asText();
            String optionB = node.get("optionB").asText();
            String optionC = node.get("optionC").asText();
            String optionD = node.get("optionD").asText();
            String answer = node.get("answer").asText();
            String analysis = node.get("analysis").asText();

            String standardAnswer = String.format("正确答案：%s\n选项内容：%s\n详细解析：%s",
                answer, getOptionContent(answer, optionA, optionB, optionC, optionD), analysis);

            String questionStem = String.format("%s\nA. %s\nB. %s\nC. %s\nD. %s",
                question, optionA, optionB, optionC, optionD);

            String subject = useSecond ? "数据结构" : "计算机网络";
            return new ExamQuestion(subject, questionStem, standardAnswer, "408考研-" + subject);
        } catch (Exception e) {
            String fallbackStem = "TCP建立连接需要几次握手？\nA. 1次\nB. 2次\nC. 3次\nD. 4次";
            String fallbackAnswer = "正确答案：C\n选项内容：3次\n详细解析：TCP建立连接采用三次握手。";
            return new ExamQuestion("计算机网络", fallbackStem, fallbackAnswer, "408考研-计算机网络");
        }
    }

    private String buildExamPrompt(ExamQuestion question) {
        return String.format("""
            🎴 智能抽卡 — 408考研挑战卡
            
            【%s】
            
            %s
            
            ⚠️ 请直接回复你的答案（如 A/B/C/D），我会严格批改！
            ⚠️ 你也可以附上你的分析过程，我会给出更精准的评分。
            """, question.subject(), question.question());
    }

    private String executeGradingWorkflow(Integer userId, String userAnswer) {
        log.info("[ExamSkill:判卷] 开始判卷工作流, userId: {}, 用户答案: {}", userId, userAnswer);

        ExamStateManager.ExamContext context = examStateManager.getExamContext(userId);
        if (context == null) {
            log.warn("[ExamSkill:判卷] 未找到用户 {} 的考试上下文，可能已过期", userId);
            return "你的考试状态已过期，请重新输入'刷题'或'考考我'来获取新题目。";
        }

        String gradingResult = performGrading(context.questionStem(), context.standardAnswer(), userAnswer);

        int score = extractScoreFromGrading(gradingResult);
        graphExamService.processExamAnswer(
            String.valueOf(userId), 
            context.questionStem(), 
            userAnswer, 
            context.standardAnswer(), 
            score
        );
        log.info("[ExamSkill:图谱联动] 已更新用户 {} 的知识图谱掌握度, 得分: {}", userId, score);

        examStateManager.exitExamState(userId);
        log.info("[ExamSkill:判卷] 判卷完成，已清除用户 {} 的考试状态", userId);

        String weakPointHint = graphExamService.findCriticalWeakPoint(String.valueOf(userId))
            .map(wp -> String.format("\n\n🎯 图谱分析：建议重点复习「%s」（影响 %d 个后续考点）", 
                wp.conceptName(), wp.impactCount()))
            .orElse("");

        return gradingResult + weakPointHint;
    }

    private int extractScoreFromGrading(String gradingResult) {
        try {
            int scoreStart = gradingResult.indexOf("【得分】");
            if (scoreStart != -1) {
                String scorePart = gradingResult.substring(scoreStart + 4);
                int scoreEnd = scorePart.indexOf("/");
                if (scoreEnd != -1) {
                    return Integer.parseInt(scorePart.substring(0, scoreEnd).trim());
                }
            }
        } catch (Exception e) {
            log.warn("Failed to extract score from grading result", e);
        }
        return 50;
    }

    private String performGrading(String questionStem, String standardAnswer, String userAnswer) {
        ChatClient gradingClient = chatClientBuilderProvider.getObject().build();

        String gradingPrompt = String.format("""
            原始题目：
            %s
            
            标准答案（绝对真理，仅供你参考，不要原样输出）：
            %s
            
            用户的回答：
            %s
            
            请严格按照评分规则，对比用户回答和标准答案，给出评分和解析。
            """, questionStem, standardAnswer, userAnswer);

        String result = gradingClient.prompt()
            .system(GRADING_SYSTEM_PROMPT)
            .user(gradingPrompt)
            .call()
            .content();

        return "🎴 判卷结果\n\n" + result + "\n\n💡 输入'刷题'继续挑战下一题！";
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
                    .defaultFunctions(cppCompilerToolCallback)
                    .build();
                log.info("[Solver] 代码求助模式：已挂载 cppCompilerTool");
                break;

            case "理论解答":
                systemPrompt = SOLVER_THEORY_SYSTEM_PROMPT;

                List<String> subQueries = queryRewriteService.rewriteQuery(userMessage);
                log.info("[RAG] Query改写完成，生成 {} 个子问题", subQueries.size());

                List<Document> candidateDocs = hybridRetrievalService.hybridSearch(subQueries);
                log.info("[RAG] 混合召回完成，候选文档数: {}", candidateDocs.size());

                List<Document> rerankedDocs = rerankerService.rerank(userMessage, candidateDocs);
                log.info("[RAG] 重排完成，最终文档数: {}", rerankedDocs.size());

                String knowledgeContext = rerankedDocs.stream()
                    .map(doc -> {
                        String source = (String) doc.getMetadata().getOrDefault("source_file", "种子知识");
                        return "【来源: " + source + "】\n" + doc.getContent();
                    })
                    .collect(Collectors.joining("\n\n---\n\n"));

                String ragEnhancedPrompt = SOLVER_THEORY_SYSTEM_PROMPT + "\n\n" +
                    "【以下是从知识库中检索到的相关内容（经过混合检索+精排重排），请优先参考】：\n" +
                    knowledgeContext;

                solverClient = chatClientBuilderProvider.getObject()
                    .defaultFunctions("webSearchTool")
                    .build();
                log.info("[Solver] 理论解答模式：工业级混合检索RAG + webSearchTool");

                return solverClient.prompt()
                    .system(ragEnhancedPrompt)
                    .user(userMessage)
                    .call()
                    .content();

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

    private record ExamQuestion(
        String subject,
        String question,
        String standardAnswer,
        String source
    ) {}
}
