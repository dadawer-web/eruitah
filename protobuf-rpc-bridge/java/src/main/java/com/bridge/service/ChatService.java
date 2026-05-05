package com.bridge.service;

import com.bridge.proto.ChatProto;

public interface ChatService {
    ChatProto.ChatResponse chat(ChatProto.ChatRequest request);
    ChatProto.GroupChatResponse groupChat(ChatProto.GroupChatRequest request);
    ChatProto.CompanionReadResponse companionRead(ChatProto.CompanionReadRequest request);
    ChatProto.DashboardResponse dashboard(ChatProto.DashboardRequest request);
    ChatProto.DashboardSummaryResponse dashboardSummary(ChatProto.DashboardSummaryRequest request);
    ChatProto.WeeklyReportResponse weeklyReport(ChatProto.WeeklyReportRequest request);
    ChatProto.PdfParseResponse parsePdf(ChatProto.PdfParseRequest request);
    ChatProto.SandboxExecuteResponse sandboxExecute(ChatProto.SandboxExecuteRequest request);
    ChatProto.SandboxTaskResponse sandboxTask(ChatProto.SandboxTaskRequest request);
    ChatProto.SwarmRegisterResponse swarmRegister(ChatProto.SwarmRegisterRequest request);
    ChatProto.SwarmHelpResponse swarmHelp(ChatProto.SwarmHelpRequest request);
    ChatProto.SwarmNodeListResponse swarmNodeList();
}
