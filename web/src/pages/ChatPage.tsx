import React, { useState, useEffect, useRef } from 'react';
import styled from 'styled-components';
import { useUser } from '../context/UserContext';

const ChatContainer = styled.div`
  display: flex;
  height: 100vh;
  background-color: #f0f2f5;
`;

const Sidebar = styled.div`
  width: 300px;
  background-color: white;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
`;

const UserInfo = styled.div`
  padding: 20px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #fafafa;
`;

const UserDetails = styled.div`
  h3 { margin: 0; color: #333; }
  p { margin: 5px 0 0 0; color: #666; font-size: 14px; }
`;

const LogoutButton = styled.button`
  padding: 8px 16px;
  background-color: #ff4d4f;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  
  &:hover {
    background-color: #ff7875;
  }
`;

const ChatTabs = styled.div`
  display: flex;
  border-bottom: 1px solid #e8e8e8;
`;

const Tab = styled.button<{ active: boolean }>`
  flex: 1;
  padding: 12px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 16px;
  color: ${props => props.active ? '#1890ff' : '#666'};
  border-bottom: 2px solid ${props => props.active ? '#1890ff' : 'transparent'};
  
  &:hover {
    color: #1890ff;
  }
`;

const ChatList = styled.div`
  flex: 1;
  overflow-y: auto;
`;

const ChatItem = styled.div<{ active: boolean }>`
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  display: flex;
  align-items: center;
  background-color: ${props => props.active ? '#e6f7ff' : 'white'};
  
  &:hover {
    background-color: #f5f5f5;
  }
`;

const Avatar = styled.div`
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background-color: #1890ff;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  margin-right: 12px;
`;

const OnlineStatus = styled.div<{ online: boolean }>`
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: ${props => props.online ? '#52c41a' : '#ccc'};
  position: absolute;
  top: 0;
  right: 0;
  border: 2px solid white;
`;

const AvatarContainer = styled.div`
  position: relative;
`;

const ChatInfo = styled.div`
  flex: 1;
`;

const ChatName = styled.div`
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
`;

const LastMessage = styled.div`
  font-size: 14px;
  color: #999;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const MainChat = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: #fafafa;
`;

const ChatHeader = styled.div`
  padding: 20px;
  background-color: white;
  border-bottom: 1px solid #e8e8e8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
`;

const ChatTitle = styled.h2`
  margin: 0;
  color: #333;
  font-size: 18px;
`;

const MessageArea = styled.div`
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background-color: #fafafa;
`;

const MessageList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const Message = styled.div<{ isSelf: boolean }>`
  display: flex;
  flex-direction: ${props => props.isSelf ? 'row-reverse' : 'row'};
  align-items: flex-end;
  gap: 12px;
  max-width: 70%;
  margin-left: ${props => props.isSelf ? 'auto' : '0'};
`;

const MessageContent = styled.div<{ isSelf: boolean }>`
  background-color: ${props => props.isSelf ? '#1890ff' : 'white'};
  color: ${props => props.isSelf ? 'white' : '#333'};
  padding: 12px 16px;
  border-radius: 8px;
  word-wrap: break-word;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
`;

const MessageTime = styled.div`
  font-size: 12px;
  color: #999;
  margin-top: 4px;
  text-align: right;
`;

const InputArea = styled.div`
  padding: 20px;
  background-color: white;
  border-top: 1px solid #e8e8e8;
  display: flex;
  gap: 12px;
  align-items: flex-end;
`;

const TextArea = styled.textarea`
  flex: 1;
  min-height: 60px;
  max-height: 120px;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  resize: none;
  font-size: 16px;
  font-family: inherit;
  
  &:focus {
    outline: none;
    border-color: #1890ff;
  }
`;

const SendButton = styled.button`
  padding: 12px 24px;
  background-color: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  
  &:hover {
    background-color: #40a9ff;
  }
  
  &:disabled {
    background-color: #ccc;
    cursor: not-allowed;
  }
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
`;

const Actions = styled.div`
  padding: 12px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  gap: 8px;
`;

const ActionButton = styled.button`
  padding: 8px 12px;
  background-color: #f0f0f0;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  
  &:hover {
    background-color: #e0e0e0;
  }
`;

const Modal = styled.div<{ visible: boolean }>`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: ${props => props.visible ? 'flex' : 'none'};
  align-items: center;
  justify-content: center;
  z-index: 1000;
`;

const ModalContent = styled.div`
  background: white;
  border-radius: 8px;
  padding: 24px;
  width: 90%;
  max-width: 400px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
`;

const ModalTitle = styled.h3`
  margin-top: 0;
  margin-bottom: 20px;
  color: #333;
`;

const ModalInput = styled.input`
  width: 100%;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 16px;
  margin-bottom: 16px;
  
  &:focus {
    outline: none;
    border-color: #1890ff;
  }
`;

const ModalButton = styled.button`
  padding: 8px 16px;
  margin-right: 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
`;

const PrimaryButton = styled(ModalButton)`
  background-color: #1890ff;
  color: white;
  
  &:hover {
    background-color: #40a9ff;
  }
`;

const SecondaryButton = styled(ModalButton)`
  background-color: #f0f0f0;
  color: #666;
  
  &:hover {
    background-color: #e0e0e0;
  }
`;

const ChatPage: React.FC = () => {
  const { user, friends, groups, messages, logout, addFriend, createGroup, sendMessage } = useUser();
  const [activeTab, setActiveTab] = useState<'friends' | 'groups'>('friends');
  const [selectedChat, setSelectedChat] = useState<number | null>(null);
  const [messageText, setMessageText] = useState<string>('');
  const [showAddFriendModal, setShowAddFriendModal] = useState<boolean>(false);
  const [showCreateGroupModal, setShowCreateGroupModal] = useState<boolean>(false);
  const [friendIdToAdd, setFriendIdToAdd] = useState<string>('');
  const [groupName, setGroupName] = useState<string>('');
  const [groupDesc, setGroupDesc] = useState<string>('');
  const messageEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selectedChat, messages]);

  // 处理发送消息
  const handleSendMessage = () => {
    if (!messageText.trim() || !selectedChat) return;
    
    sendMessage(selectedChat, messageText.trim(), activeTab === 'friends' ? 'friend' : 'group');
    setMessageText('');
  };

  // 处理添加好友
  const handleAddFriend = async () => {
    const friendId = parseInt(friendIdToAdd, 10);
    if (!isNaN(friendId)) {
      const success = await addFriend(friendId);
      if (success) {
        setShowAddFriendModal(false);
        setFriendIdToAdd('');
      }
    }
  };

  // 处理创建群组
  const handleCreateGroup = async () => {
    if (!groupName.trim() || !groupDesc.trim()) return;
    
    // 这里简化处理，实际应该从好友列表中选择成员
    const success = await createGroup(groupName, groupDesc, []);
    if (success) {
      setShowCreateGroupModal(false);
      setGroupName('');
      setGroupDesc('');
    }
  };

  // 获取选中的聊天名称
  const getSelectedChatName = (): string => {
    if (!selectedChat) return '';
    
    if (activeTab === 'friends') {
      const friend = friends.find(f => f.id === selectedChat);
      return friend?.name || '';
    } else {
      const group = groups.find(g => g.id === selectedChat);
      return group?.name || '';
    }
  };

  return (
    <ChatContainer>
      <Sidebar>
        <UserInfo>
          <UserDetails>
            <h3>{user.name}</h3>
            <p>ID: {user.id}</p>
          </UserDetails>
          <LogoutButton onClick={logout}>退出</LogoutButton>
        </UserInfo>
        
        <Actions>
          <ActionButton onClick={() => setShowAddFriendModal(true)}>添加好友</ActionButton>
          <ActionButton onClick={() => setShowCreateGroupModal(true)}>创建群组</ActionButton>
        </Actions>
        
        <ChatTabs>
          <Tab active={activeTab === 'friends'} onClick={() => setActiveTab('friends')}>好友</Tab>
          <Tab active={activeTab === 'groups'} onClick={() => setActiveTab('groups')}>群组</Tab>
        </ChatTabs>
        
        <ChatList>
          {activeTab === 'friends' ? (
            friends.map(friend => (
              <ChatItem
                key={friend.id}
                active={selectedChat === friend.id}
                onClick={() => setSelectedChat(friend.id)}
              >
                <AvatarContainer>
                  <Avatar>{friend.name.charAt(0)}</Avatar>
                  <OnlineStatus online={friend.onlineStatus} />
                </AvatarContainer>
                <ChatInfo>
                  <ChatName>{friend.name}</ChatName>
                  <LastMessage>
                    {messages.get(friend.id)?.slice(-1)[0]?.content || '无消息'}
                  </LastMessage>
                </ChatInfo>
              </ChatItem>
            ))
          ) : (
            groups.map(group => (
              <ChatItem
                key={group.id}
                active={selectedChat === group.id}
                onClick={() => setSelectedChat(group.id)}
              >
                <Avatar>👥</Avatar>
                <ChatInfo>
                  <ChatName>{group.name}</ChatName>
                  <LastMessage>{group.desc}</LastMessage>
                </ChatInfo>
              </ChatItem>
            ))
          )}
        </ChatList>
      </Sidebar>
      
      <MainChat>
        {selectedChat ? (
          <>
            <ChatHeader>
              <ChatTitle>{getSelectedChatName()}</ChatTitle>
            </ChatHeader>
            
            <MessageArea>
              <MessageList>
                {messages.get(selectedChat)?.map(msg => {
                  const isSelf = msg.fromId === user.id;
                  return (
                    <Message key={msg.id} isSelf={isSelf}>
                      <Avatar>{isSelf ? user.name.charAt(0) : 'U'}</Avatar>
                      <MessageContent isSelf={isSelf}>
                        {msg.content}
                        <MessageTime>{msg.time}</MessageTime>
                      </MessageContent>
                    </Message>
                  );
                })}
                <div ref={messageEndRef} />
              </MessageList>
            </MessageArea>
            
            <InputArea>
              <TextArea
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                placeholder="输入消息..."
                onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
              />
              <SendButton onClick={handleSendMessage}>
                发送
              </SendButton>
            </InputArea>
          </>
        ) : (
          <EmptyState>
            <h3>请选择一个好友或群组开始聊天</h3>
          </EmptyState>
        )}
      </MainChat>

      {/* 添加好友模态框 */}
      <Modal visible={showAddFriendModal}>
        <ModalContent>
          <ModalTitle>添加好友</ModalTitle>
          <ModalInput
            type="number"
            placeholder="输入好友ID"
            value={friendIdToAdd}
            onChange={(e) => setFriendIdToAdd(e.target.value)}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <SecondaryButton onClick={() => setShowAddFriendModal(false)}>取消</SecondaryButton>
            <PrimaryButton onClick={handleAddFriend}>添加</PrimaryButton>
          </div>
        </ModalContent>
      </Modal>

      {/* 创建群组模态框 */}
      <Modal visible={showCreateGroupModal}>
        <ModalContent>
          <ModalTitle>创建群组</ModalTitle>
          <ModalInput
            type="text"
            placeholder="群组名称"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
          />
          <ModalInput
            type="text"
            placeholder="群组描述"
            value={groupDesc}
            onChange={(e) => setGroupDesc(e.target.value)}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <SecondaryButton onClick={() => setShowCreateGroupModal(false)}>取消</SecondaryButton>
            <PrimaryButton onClick={handleCreateGroup}>创建</PrimaryButton>
          </div>
        </ModalContent>
      </Modal>
    </ChatContainer>
  );
};

export default ChatPage;