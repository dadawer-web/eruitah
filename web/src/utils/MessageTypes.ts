// 消息类型常量定义 - 与后端public.hpp中的EnMsgType保持一致
export const MessageType = {
  // 登录相关消息
  LOGIN_MSG: 1,            // 登录消息（值为1）
  LOGIN_MSG_ACK: 2,        // 登录响应消息（值为2）
  LOGINOUT_MSG: 3,         // 注销消息（值为3）
  
  // 注册相关消息
  REG_MSG: 4,              // 注册消息（值为4）
  REG_MSG_ACK: 5,          // 注册响应消息（值为5）
  
  // 聊天相关消息
  ONE_CHAT_MSG: 6,         // 单聊消息（值为6）
  GROUP_CHAT_MSG: 7,       // 群聊消息（值为7）
  
  // 好友相关消息
  ADD_FRIEND_MSG: 8,       // 添加好友消息（值为8）
  ADD_FRIEND_MSG_ACK: 9,   // 添加好友响应消息（值为9）
  
  // 群组相关消息
  CREATE_GROUP_MSG: 10,    // 创建群组消息（值为10）
  ADD_GROUP_MSG: 11,       // 加入群组消息（值为11）
  ADD_GROUP_MSG_ACK: 12    // 加入群组响应消息（值为12）
} as const;

export type MessageType = typeof MessageType[keyof typeof MessageType];

// 消息结构接口
export interface BaseMessage {
  msgid: number;           // 消息ID
  msgtype: MessageType;    // 消息类型
}

// 登录消息接口
export interface LoginMessage extends BaseMessage {
  id: number;              // 用户ID
  password: string;        // 密码
}

// 注册消息接口
export interface RegisterMessage extends BaseMessage {
  id: number;              // 用户ID
  password: string;        // 密码
  name: string;            // 用户名
}

// 单聊消息接口
export interface ChatMessage extends BaseMessage {
  fromid: number;          // 发送者ID
  toid: number;            // 接收者ID
  content: string;         // 消息内容
  msgtype: 6; // 固定为单聊消息类型 (ONE_CHAT_MSG)
}

// 群聊消息接口
export interface GroupChatMessage extends BaseMessage {
  fromid: number;          // 发送者ID
  groupid: number;         // 群组ID
  content: string;         // 消息内容
  msgtype: 7; // 固定为群聊消息类型 (GROUP_CHAT_MSG)
}

// 添加好友消息接口
export interface AddFriendMessage extends BaseMessage {
  userid: number;          // 请求者ID
  friendid: number;        // 被添加好友ID
}

// 创建群组消息接口
export interface CreateGroupMessage extends BaseMessage {
  userid: number;          // 创建者ID
  name: string;            // 群组名称
  desc: string;            // 群组描述
  useridlist: number[];    // 群成员ID列表
}