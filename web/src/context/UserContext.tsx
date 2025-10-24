import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { tcpService } from '../utils/TcpService';
import { MessageType } from '../utils/MessageTypes';

// 用户信息接口
interface UserInfo {
  id: number;
  name: string;
  isLogin: boolean;
}

// 好友列表项接口
interface FriendItem {
  id: number;
  name: string;
  onlineStatus: boolean;
}

// 群组列表项接口
interface GroupItem {
  id: number;
  name: string;
  desc: string;
}

// 消息项接口
interface MessageItem {
  id: number;
  fromId: number;
  toId: number;
  content: string;
  time: string;
  type: 'friend' | 'group';
}

// 上下文接口
interface UserContextType {
  user: UserInfo;
  friends: FriendItem[];
  groups: GroupItem[];
  messages: Map<number, MessageItem[]>; // key为好友ID或群组ID
  setUser: (user: UserInfo) => void;
  setFriends: (friends: FriendItem[]) => void;
  setGroups: (groups: GroupItem[]) => void;
  addMessage: (id: number, message: MessageItem, type: 'friend' | 'group') => void;
  updateFriendStatus: (userId: number, online: boolean) => void;
  login: (id: number, password: string) => Promise<boolean>;
  register: (id: number, name: string, password: string) => Promise<boolean>;
  logout: () => void;
  addFriend: (friendId: number) => Promise<boolean>;
  createGroup: (name: string, desc: string, userIds: number[]) => Promise<boolean>;
  sendMessage: (id: number, content: string, type: 'friend' | 'group') => void;
}

// 创建上下文
const UserContext = createContext<UserContextType | undefined>(undefined);

// 上下文提供者组件
export const UserProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserInfo>({ id: 0, name: '', isLogin: false });
  const [friends, setFriends] = useState<FriendItem[]>([]);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [messages, setMessages] = useState<Map<number, MessageItem[]>>(new Map());

  // 初始化WebSocket连接和消息处理
  useEffect(() => {
    // 连接WebSocket
    tcpService.connect().catch(error => {
      console.error('WebSocket连接失败:', error);
    });

    // 处理登录响应
    tcpService.onMessage(MessageType.LOGIN_MSG_ACK, (data) => {
      if (data.error === 0) {
        // 登录成功
        setUser({
          id: data.userid,
          name: data.name,
          isLogin: true
        });
        
        // 更新好友列表
        if (data.friends) {
          const friendList: FriendItem[] = data.friends.map((friend: any) => ({
            id: friend.userid,
            name: friend.name,
            onlineStatus: friend.onlineStatus
          }));
          setFriends(friendList);
        }
        
        // 更新群组列表
        if (data.groups) {
          const groupList: GroupItem[] = data.groups.map((group: any) => ({
            id: group.groupid,
            name: group.name,
            desc: group.desc
          }));
          setGroups(groupList);
        }
        
        // 加载离线消息
        if (data.offlinemessages) {
          data.offlinemessages.forEach((msg: any) => {
            // 处理离线消息
            handleReceivedMessage(msg);
          });
        }
      }
    });

    // 处理注册响应
    tcpService.onMessage(MessageType.REG_MSG_ACK, (_data) => {
      // 注册响应已在register函数中处理
    });

    // 处理单聊消息
    tcpService.onMessage(MessageType.ONE_CHAT_MSG, (data) => {
      handleReceivedMessage(data);
    });

    // 处理群聊消息
    tcpService.onMessage(MessageType.GROUP_CHAT_MSG, (data) => {
      handleReceivedMessage(data);
    });

    // 处理添加好友响应
    tcpService.onMessage(MessageType.ADD_FRIEND_MSG_ACK, (data) => {
      if (data.error === 0 && data.friend) {
        setFriends(prev => [...prev, {
          id: data.friend.userid,
          name: data.friend.name,
          onlineStatus: data.friend.onlineStatus
        }]);
      }
    });

    // 处理创建群组响应
    tcpService.onMessage(MessageType.ADD_GROUP_MSG_ACK, (data) => {
      if (data.error === 0 && data.group) {
        setGroups(prev => [...prev, {
          id: data.group.groupid,
          name: data.group.name,
          desc: data.group.desc
        }]);
      }
    });

    // 组件卸载时清理
    return () => {
      tcpService.disconnect();
    };
  }, []);

  // 处理接收到的消息
  const handleReceivedMessage = (message: any) => {
    if (message.msgtype === MessageType.ONE_CHAT_MSG) {
      // 单聊消息
      const fromId = message.fromid;
      const msg: MessageItem = {
        id: message.msgid || Date.now(),
        fromId: fromId,
        toId: message.toid,
        content: message.content,
        time: new Date().toLocaleString(),
        type: 'friend'
      };
      
      addMessage(fromId, msg, 'friend');
    } else if (message.msgtype === MessageType.GROUP_CHAT_MSG) {
      // 群聊消息
      const groupId = message.groupid;
      const msg: MessageItem = {
        id: message.msgid || Date.now(),
        fromId: message.fromid,
        toId: groupId,
        content: message.content,
        time: new Date().toLocaleString(),
        type: 'group'
      };
      
      addMessage(groupId, msg, 'group');
    }
  };

  // 添加消息到对应聊天
  const addMessage = (id: number, message: MessageItem, _type: 'friend' | 'group') => {
    setMessages(prev => {
      const newMessages = new Map(prev);
      const chatMessages = newMessages.get(id) || [];
      newMessages.set(id, [...chatMessages, message]);
      return newMessages;
    });
  };

  // 更新好友在线状态
  const updateFriendStatus = (userId: number, online: boolean) => {
    setFriends(prev => 
      prev.map(friend => 
        friend.id === userId ? { ...friend, onlineStatus: online } : friend
      )
    );
  };

  // 登录方法
  const login = (id: number, password: string): Promise<boolean> => {
    return new Promise((resolve) => {
      const loginHandler = (data: any) => {
        tcpService.offMessage(MessageType.LOGIN_MSG_ACK);
        resolve(data.error === 0);
      };

      tcpService.onMessage(MessageType.LOGIN_MSG_ACK, loginHandler);

      tcpService.send({
        msgid: Date.now(),
        msgtype: MessageType.LOGIN_MSG,
        id,
        password
      } as any);
    });
  };

  // 注册方法
  const register = (id: number, name: string, password: string): Promise<boolean> => {
    return new Promise((resolve) => {
      const registerHandler = (data: any) => {
        tcpService.offMessage(MessageType.REG_MSG_ACK);
        resolve(data.error === 0);
      };

      tcpService.onMessage(MessageType.REG_MSG_ACK, registerHandler);

      tcpService.send({
        msgid: Date.now(),
        msgtype: MessageType.REG_MSG,
        id,
        name,
        password
      } as any);
    });
  };

  // 注销方法
  const logout = () => {
    setUser({ id: 0, name: '', isLogin: false });
    setFriends([]);
    setGroups([]);
    setMessages(new Map());
    tcpService.disconnect();
  };

  // 添加好友方法
  const addFriend = (friendId: number): Promise<boolean> => {
    return new Promise((resolve) => {
      const handler = (data: any) => {
        tcpService.offMessage(MessageType.ADD_FRIEND_MSG_ACK);
        resolve(data.error === 0);
      };

      tcpService.onMessage(MessageType.ADD_FRIEND_MSG_ACK, handler);

      tcpService.send({
        msgid: Date.now(),
        msgtype: MessageType.ADD_FRIEND_MSG,
        userid: user.id,
        friendid: friendId
      } as any);
    });
  };

  // 创建群组方法
  const createGroup = (name: string, desc: string, userIds: number[]): Promise<boolean> => {
    return new Promise((resolve) => {
      const handler = (data: any) => {
        tcpService.offMessage(MessageType.ADD_GROUP_MSG_ACK);
        resolve(data.error === 0);
      };

      tcpService.onMessage(MessageType.ADD_GROUP_MSG_ACK, handler);

      tcpService.send({
        msgid: Date.now(),
        msgtype: MessageType.CREATE_GROUP_MSG,
        userid: user.id,
        name,
        desc,
        useridlist: userIds
      } as any);
    });
  };

  // 发送消息方法
  const sendMessage = (id: number, content: string, type: 'friend' | 'group') => {
    const msgid = Date.now();
    
    if (type === 'friend') {
      // 发送单聊消息
      tcpService.send({
        msgid,
        msgtype: MessageType.ONE_CHAT_MSG,
        fromid: user.id,
        toid: id,
        content
      } as any);
      
      // 添加到本地消息列表
      const msg: MessageItem = {
        id: msgid,
        fromId: user.id,
        toId: id,
        content,
        time: new Date().toLocaleString(),
        type: 'friend'
      };
      addMessage(id, msg, 'friend');
    } else {
      // 发送群聊消息
      tcpService.send({
        msgid,
        msgtype: MessageType.GROUP_CHAT_MSG,
        fromid: user.id,
        groupid: id,
        content
      } as any);
      
      // 添加到本地消息列表
      const msg: MessageItem = {
        id: msgid,
        fromId: user.id,
        toId: id,
        content,
        time: new Date().toLocaleString(),
        type: 'group'
      };
      addMessage(id, msg, 'group');
    }
  };

  const contextValue: UserContextType = {
    user,
    friends,
    groups,
    messages,
    setUser,
    setFriends,
    setGroups,
    addMessage,
    updateFriendStatus,
    login,
    register,
    logout,
    addFriend,
    createGroup,
    sendMessage
  };

  return (
    <UserContext.Provider value={contextValue}>
      {children}
    </UserContext.Provider>
  );
};

// 自定义Hook，方便使用上下文
export const useUser = () => {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};