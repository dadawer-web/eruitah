import React, { useState, useCallback, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { SlideCanvas } from './SlideCanvas';
import { Presentation } from './types';

interface ProgressState {
  progress: number;
  action: string;
  status: 'idle' | 'processing' | 'success' | 'error' | 'timeout';
  logs: Array<{ agent: string; action: string; time: number }>;
}

const INITIAL_PROGRESS: ProgressState = {
  progress: 0,
  action: '',
  status: 'idle',
  logs: [],
};

function ProcessingCenter({ state }: { state: ProgressState }) {
  const logsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [state.logs]);

  const pct = Math.max(0, Math.min(100, state.progress));
  const isError = state.status === 'error' || state.status === 'timeout';
  const isComplete = state.status === 'success';

  let barColor = 'linear-gradient(90deg, #6366f1, #8b5cf6, #a78bfa)';
  if (isComplete) barColor = 'linear-gradient(90deg, #10b981, #34d399)';
  if (isError) barColor = 'linear-gradient(90deg, #ef4444, #f87171)';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      background: '#0f0f1a',
      padding: 40,
      boxSizing: 'border-box',
    }}>
      <div style={{
        width: '100%',
        maxWidth: 560,
        background: '#161625',
        borderRadius: 16,
        border: '1px solid rgba(255,255,255,0.06)',
        padding: 32,
        boxShadow: '0 0 60px rgba(99,102,241,0.08)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: isError ? '#ef444420' : isComplete ? '#10b98120' : '#6366f120',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22,
          }}>
            {isError ? '❌' : isComplete ? '✅' : '⚡'}
          </div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, color: '#e0e0e0' }}>
              {isError ? '处理失败' : isComplete ? '处理完成' : 'AI 处理中心'}
            </div>
            <div style={{ fontSize: 12, color: '#666', marginTop: 2 }}>
              {isError ? state.action : isComplete ? '结果已就绪' : '大模型正在努力工作中...'}
            </div>
          </div>
          <div style={{ marginLeft: 'auto', fontSize: 28, fontWeight: 800, color: isError ? '#ef4444' : isComplete ? '#10b981' : '#8b5cf6' }}>
            {isError ? '!' : `${pct}%`}
          </div>
        </div>

        <div style={{
          width: '100%', height: 10, background: '#1e1e2e',
          borderRadius: 5, overflow: 'hidden', marginBottom: 20,
        }}>
          <div style={{
            height: '100%', borderRadius: 5,
            background: barColor,
            backgroundSize: state.status === 'processing' ? '200% 100%' : '100% 100%',
            width: `${pct}%`,
            transition: 'width 0.5s ease',
            animation: state.status === 'processing' ? 'shimmer 2s linear infinite' : 'none',
          }} />
        </div>

        {state.action && (
          <div style={{
            fontSize: 13, color: '#a0a0b8', marginBottom: 16,
            padding: '10px 14px', background: '#0f0f1a',
            borderRadius: 8, borderLeft: '3px solid #6366f1',
          }}>
            {state.action}
          </div>
        )}

        {state.logs.length > 0 && (
          <div ref={logsRef} style={{
            maxHeight: 200, overflowY: 'auto',
            background: '#0a0a14', borderRadius: 8,
            padding: 12, fontSize: 11, lineHeight: 1.8,
            fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
          }}>
            {state.logs.map((log, i) => (
              <div key={i} style={{ color: '#888', marginBottom: 2 }}>
                <span style={{ color: '#6d4cff' }}>[{log.agent}]</span>{' '}
                <span style={{ color: '#aaa' }}>{log.action}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
}

export function PPTViewer({ initialData }: { initialData?: Presentation }) {
  const [data, setData] = useState<Presentation | null>(initialData || null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [aiInstruction, setAiInstruction] = useState('');
  const [progressState, setProgressState] = useState<ProgressState>(INITIAL_PROGRESS);
  const containerRef = useRef<HTMLDivElement>(null);

  const goNext = useCallback(() => {
    if (data) setCurrentIndex(i => Math.min(i + 1, data.slides.length - 1));
  }, [data]);

  const goPrev = useCallback(() => {
    setCurrentIndex(i => Math.max(i - 1, 0));
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') goNext();
      else if (e.key === 'ArrowLeft') goPrev();
      else if (e.key === 'f' || e.key === 'F') toggleFullscreen();
      else if (e.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [goNext, goPrev, toggleFullscreen]);

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const msg = event.data;
      if (!msg || typeof msg !== 'object') return;

      if (msg.type === 'TASK_PROGRESS') {
        const payload = msg.payload || {};
        setProgressState(prev => {
          const newLogs = [...prev.logs];
          if (payload.agent && payload.action) {
            newLogs.push({ agent: payload.agent, action: payload.action, time: Date.now() });
            if (newLogs.length > 50) newLogs.shift();
          }
          return {
            progress: payload.progress ?? prev.progress,
            action: payload.action ?? prev.action,
            status: payload.status || (payload.progress >= 100 ? 'success' : 'processing'),
            logs: newLogs,
          };
        });
      }

      if (msg.type === 'TASK_START') {
        setProgressState({
          progress: 0,
          action: '任务已提交，等待 Worker 接管...',
          status: 'processing',
          logs: [],
        });
        setData(null);
      }

      if (msg.type === 'RENDER_PPT' && msg.payload) {
        setData(msg.payload);
        setCurrentIndex(0);
        setProgressState(prev => ({ ...prev, status: 'success', progress: 100 }));
      }

      if (msg.type === 'TASK_ERROR') {
        setProgressState(prev => ({
          ...prev,
          status: 'error',
          action: msg.payload?.error || '处理失败',
        }));
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  useEffect(() => {
    window.parent.postMessage({ type: 'PPT_VIEWER_READY' }, '*');
  }, []);

  const handleAISubmit = () => {
    if (!aiInstruction.trim()) return;
    window.parent.postMessage({
      type: 'REWRITE_SLIDE',
      payload: {
        slideIndex: currentIndex,
        instruction: aiInstruction,
      },
    }, '*');
    setAiInstruction('');
  };

  const isProcessing = progressState.status === 'processing';
  const hasData = data && data.slides && data.slides.length > 0;

  if (isProcessing && !hasData) {
    return (
      <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
        <ProcessingCenter state={progressState} />
      </div>
    );
  }

  if (!hasData) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#888', fontSize: 14 }}>
        No PPT data — waiting for presentation...
      </div>
    );
  }

  const slide = data.slides[currentIndex];
  const design = data.design;

  const layoutLabel: Record<string, string> = {
    cover: '封面页', section: '章节页', content: '内容页',
    code_focus: '代码页', closing: '结尾页',
  };

  return (
    <div ref={containerRef} style={{ display: 'flex', flexDirection: 'row', width: '100%', height: '100%', background: '#0f0f1a' }}>

      {isProcessing && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, zIndex: 100,
          padding: '8px 16px', background: '#161625ee',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            flex: 1, height: 6, background: '#1e1e2e', borderRadius: 3, overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', borderRadius: 3,
              background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
              width: `${Math.max(0, Math.min(100, progressState.progress))}%`,
              transition: 'width 0.5s ease',
            }} />
          </div>
          <span style={{ fontSize: 11, color: '#8b5cf6', fontWeight: 600, minWidth: 32 }}>
            {progressState.progress}%
          </span>
          <span style={{ fontSize: 11, color: '#666', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {progressState.action}
          </span>
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', padding: 24 }}>
          <SlideCanvas slide={slide} design={design} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '10px 0', background: '#0f0f1a', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <button onClick={goPrev} disabled={currentIndex <= 0} style={navBtnStyle}>◀</button>
          <span style={{ color: '#aaa', fontSize: 12, fontWeight: 500, letterSpacing: 1 }}>{currentIndex + 1} / {data.slides.length}</span>
          <button onClick={goNext} disabled={currentIndex >= data.slides.length - 1} style={navBtnStyle}>▶</button>
          <div style={{ width: 1, height: 16, background: 'rgba(255,255,255,0.1)', margin: '0 8px' }} />
          <button onClick={toggleFullscreen} style={navBtnStyle}>⛶ 全屏</button>
        </div>
      </div>

      <div style={{ width: 340, flexShrink: 0, background: '#161625', borderLeft: '1px solid rgba(255,255,255,0.1)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px 20px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#e0e0e0', marginBottom: 4 }}>✨ AI Canvas Copilot</div>
          <div style={{ fontSize: 12, color: '#666' }}>第 {currentIndex + 1} 页 · {layoutLabel[slide.layout] || slide.layout}</div>
        </div>

        <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#6d4cff', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>本页摘要</div>
          {slide.title ? (
            <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.6, marginBottom: 4 }}>
              <span style={{ color: '#e0e0e0', fontWeight: 600 }}>{slide.title}</span>
            </div>
          ) : null}
          {slide.subtitle ? (
            <div style={{ fontSize: 12, color: '#888', lineHeight: 1.5 }}>{slide.subtitle}</div>
          ) : null}
          {slide.eyebrow ? (
            <div style={{ fontSize: 11, color: '#6d4cff', marginTop: 4 }}>{slide.eyebrow}</div>
          ) : null}
          {slide.components && slide.components.length > 0 ? (
            <div style={{ fontSize: 11, color: '#555', marginTop: 8 }}>
              包含 {slide.components.length} 个组件
              {slide.components.filter(c => c.type === 'bullet_list').length > 0
                ? ` · ${slide.components.filter(c => c.type === 'bullet_list').reduce((n, c) => n + (c.items?.length || 0), 0)} 个要点`
                : ''}
            </div>
          ) : null}
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '16px 20px', gap: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#6d4cff', textTransform: 'uppercase', letterSpacing: 1 }}>重写指令</div>
          <textarea
            value={aiInstruction}
            onChange={(e) => setAiInstruction(e.target.value)}
            placeholder="例如：把这一页精简为3个要点..."
            style={{
              width: '100%',
              height: 90,
              borderRadius: 8,
              border: '1px solid #2a2a3e',
              background: '#0f0f1a',
              color: '#e0e0e0',
              padding: '12px',
              fontSize: 13,
              resize: 'none',
              outline: 'none',
              boxSizing: 'border-box',
              fontFamily: 'inherit',
              lineHeight: 1.5,
              transition: 'border-color 0.2s',
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = '#6d4cff'; }}
            onBlur={(e) => { e.currentTarget.style.borderColor = '#2a2a3e'; }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAISubmit(); } }}
          />
          <button
            onClick={handleAISubmit}
            disabled={!aiInstruction.trim()}
            style={{
              width: '100%',
              padding: '10px 0',
              borderRadius: 8,
              border: 'none',
              background: aiInstruction.trim() ? '#6d4cff' : '#1e1e30',
              color: aiInstruction.trim() ? '#fff' : '#444',
              fontSize: 13,
              fontWeight: 600,
              cursor: aiInstruction.trim() ? 'pointer' : 'not-allowed',
              transition: 'all 0.2s',
            }}
          >
            ✨ 发送重写指令
          </button>
        </div>

        <div style={{ padding: '10px 20px', borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: 11, color: '#444', textAlign: 'center' }}>
          Enter 发送 · Shift+Enter 换行
        </div>
      </div>
    </div>
  );
}

const navBtnStyle: React.CSSProperties = {
  padding: '4px 14px',
  borderRadius: 6,
  fontSize: 13,
  background: '#2a2a3e',
  color: '#ccc',
  border: '1px solid #3a3a4e',
  cursor: 'pointer',
  transition: 'all 0.15s',
};

export function initPPTViewer(containerId: string, data?: Presentation) {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`PPTViewer: container #${containerId} not found`);
    return;
  }
  const root = createRoot(container);
  root.render(<PPTViewer initialData={data} />);
  return root;
}

(window as any).initPPTViewer = initPPTViewer;
(window as any).PPTViewer = PPTViewer;
