import { useState, useEffect } from 'react';
import { wsService } from '../utils/WebSocketService';

const useWebSocketStatus = () => {
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');

  useEffect(() => {
    // 初始设置
    setStatus(wsService.getStatus());

    // 监听WebSocket状态变化
    const checkStatus = () => {
      setStatus(wsService.getStatus());
    };

    // 定期检查状态变化
    const intervalId = setInterval(checkStatus, 1000);

    // 组件卸载时清理
    return () => {
      clearInterval(intervalId);
    };
  }, []);

  return status;
};

export default useWebSocketStatus;