package com.bridge.service;

import com.bridge.proto.ChatProto;

public interface ChatService {
    ChatProto.ChatResponse chat(ChatProto.ChatRequest request);
    ChatProto.GroupChatResponse groupChat(ChatProto.GroupChatRequest request);
}
