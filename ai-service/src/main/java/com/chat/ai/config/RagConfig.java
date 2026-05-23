package com.chat.ai.config;

import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.context.annotation.Configuration;

import java.util.List;
import java.util.Map;

@Slf4j
@Configuration
@RequiredArgsConstructor
public class RagConfig {

    private final VectorStore vectorStore;

    @PostConstruct
    public void initSeedKnowledge() {
        log.info("Initializing seed knowledge in VectorStore...");
        
        Document tcpDoc = new Document(
            "TCP粘包问题详解\n\n" +
            "一、什么是TCP粘包？\n" +
            "TCP粘包是指发送方发送的多个数据包，到接收方时粘连在一起，变成一个大的数据包。这不是TCP协议的bug，而是TCP协议的特性。\n\n" +
            "二、粘包产生的原因\n" +
            "1. 发送方原因：Nagle算法会将多个小数据包合并发送，提高传输效率。\n" +
            "2. 接收方原因：接收方的TCP缓冲区中，多个数据包被一起读出。\n\n" +
            "三、解决方案\n" +
            "1. 固定长度：每个消息固定长度，不够补空格或特殊字符。\n" +
            "2. 分隔符：在消息末尾添加特殊分隔符，如换行符。\n" +
            "3. 长度字段：在消息头部添加长度字段，标识消息长度。\n" +
            "4. 应用层协议：设计完整的应用层协议，如HTTP的Content-Length。\n\n" +
            "四、考研重点\n" +
            "TCP是面向字节流的协议，不保留消息边界；UDP是面向消息的协议，保留消息边界。这是TCP粘包问题的根本原因。",
            Map.of("source", "408考研-计算机网络", "topic", "TCP粘包", "difficulty", "中等")
        );

        Document treeDoc = new Document(
            "二叉树遍历详解\n\n" +
            "一、四种遍历方式\n" +
            "1. 前序遍历（先序遍历）：根 -> 左 -> 右\n" +
            "2. 中序遍历：左 -> 根 -> 右\n" +
            "3. 后序遍历：左 -> 右 -> 根\n" +
            "4. 层序遍历：按层从上到下，从左到右\n\n" +
            "二、递归实现\n" +
            "前序：访问根节点 -> 递归左子树 -> 递归右子树\n" +
            "中序：递归左子树 -> 访问根节点 -> 递归右子树\n" +
            "后序：递归左子树 -> 递归右子树 -> 访问根节点\n\n" +
            "三、非递归实现（使用栈）\n" +
            "前序：根节点入栈，循环：弹出并访问，右子节点入栈，左子节点入栈\n" +
            "中序：一路向左入栈，弹出访问，转向右子树\n" +
            "后序：需要记录上次访问的节点，判断右子树是否已访问\n\n" +
            "四、考研重点题型\n" +
            "1. 给定前序+中序，求后序\n" +
            "2. 给定后序+中序，求前序\n" +
            "3. 注意：前序+后序不能唯一确定一棵二叉树\n\n" +
            "五、时间复杂度\n" +
            "所有遍历方式的时间复杂度都是O(n)，空间复杂度为O(h)，h为树高。",
            Map.of("source", "408考研-数据结构", "topic", "二叉树遍历", "difficulty", "基础")
        );

        Document processDoc = new Document(
            "进程与线程的区别\n\n" +
            "一、基本概念\n" +
            "进程：是资源分配的基本单位，拥有独立的地址空间。\n" +
            "线程：是CPU调度的基本单位，共享所属进程的资源。\n\n" +
            "二、主要区别\n" +
            "1. 地址空间：进程独立，线程共享\n" +
            "2. 通信方式：进程需要IPC，线程可直接读写\n" +
            "3. 开销：进程创建/切换开销大，线程开销小\n" +
            "4. 安全性：进程间隔离，线程间可能相互影响\n\n" +
            "三、考研重点\n" +
            "1. 进程的三态模型：就绪、运行、阻塞\n" +
            "2. 进程同步：信号量、管程\n" +
            "3. 死锁条件：互斥、请求与保持、不剥夺、循环等待",
            Map.of("source", "408考研-操作系统", "topic", "进程线程", "difficulty", "基础")
        );

        try {
            vectorStore.add(List.of(tcpDoc, treeDoc, processDoc));
            log.info("Initialized VectorStore with {} seed knowledge documents", 3);
        } catch (Exception e) {
            log.warn("⚠️ Failed to initialize seed knowledge in VectorStore (Redis may be unavailable): {}", e.getMessage());
            log.warn("Application will start without seed knowledge. RAG search will work once Redis is available.");
        }
    }
}
/**
 * 启动时：RagConfig 添加 3 个种子文档 → VectorStore
上传时：RagService 上传真实文档 → 同一个 VectorStore（追加，不是替换）
检索时：similaritySearch() 返回所有相关文档（种子 + 真实文档）
 */