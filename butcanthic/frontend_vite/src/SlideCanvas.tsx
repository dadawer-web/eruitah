import React, { useRef, useEffect, useState, useCallback } from 'react';
import { CANVAS_WIDTH, CANVAS_HEIGHT, SlidePage, SlideComponent, DesignSystem } from './types';

function renderComponent(comp: SlideComponent, design: DesignSystem): React.ReactNode {
  const pal = design.palette;
  const fonts = design.fonts;
  const ts = design.type_scale;
  const radius = design.radius;
  const t = comp.type;

  if (t === 'heading') {
    return (
      <div key={comp.content} style={{ fontSize: ts.body * 1.3, fontFamily: fonts.display, fontWeight: 700, margin: '16px 0 8px', color: pal.text }}>
        {comp.content}
      </div>
    );
  }

  if (t === 'text') {
    return (
      <div key={comp.content?.slice(0, 40)} style={{ fontSize: ts.body, lineHeight: 1.6, margin: '8px 0', color: pal.text }}>
        {comp.content}
      </div>
    );
  }

  if (t === 'bullet_list') {
    return (
      <ul key="bl" style={{ fontSize: ts.body, lineHeight: 1.8, margin: '8px 0', paddingLeft: 32, color: pal.text }}>
        {(comp.items || []).map((item, i) => (
          <li key={i} style={{ margin: '4px 0' }}>{item}</li>
        ))}
      </ul>
    );
  }

  if (t === 'code') {
    return (
      <div key={comp.content?.slice(0, 40)} style={{ background: '#1e1e2e', borderRadius: radius, padding: 20, margin: '12px 0', overflow: 'auto' }}>
        {comp.language && (
          <div style={{ fontSize: ts.body * 0.5, color: '#888', marginBottom: 4, fontFamily: fonts.display }}>{comp.language}</div>
        )}
        <pre style={{ margin: 0, fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace', fontSize: ts.body * 0.7, whiteSpace: 'pre-wrap', wordWrap: 'break-word', color: '#cdd6f4', lineHeight: 1.5 }}>
          {comp.content}
        </pre>
      </div>
    );
  }

  if (t === 'image') {
    return (
      <div key={comp.image_url} style={{ margin: '12px 0', textAlign: 'center' }}>
        <img src={comp.image_url} style={{ maxWidth: '100%', maxHeight: 400, borderRadius: radius, objectFit: 'contain' as const }} />
      </div>
    );
  }

  if (t === 'divider') {
    return <hr key="div" style={{ border: 'none', borderTop: `2px solid ${pal.accent}33`, margin: '20px 0' }} />;
  }

  if (t === 'card') {
    const cardAccent = comp.accent || pal.accent;
    return (
      <div key={comp.content?.slice(0, 40)} style={{ background: `${cardAccent}11`, borderLeft: `4px solid ${cardAccent}`, borderRadius: radius, padding: 20, margin: '12px 0', fontSize: ts.body, lineHeight: 1.6 }}>
        {comp.content}
      </div>
    );
  }

  if (t === 'two_column') {
    return (
      <div key="2col" style={{ display: 'flex', gap: 40, margin: '12px 0' }}>
        <div style={{ flex: 1, fontSize: ts.body, lineHeight: 1.6 }}>{comp.content}</div>
        <div style={{ flex: 1, fontSize: ts.body, lineHeight: 1.6 }}>
          {(comp.items || []).map((item, i) => (
            <div key={i} style={{ margin: '4px 0' }}>{item}</div>
          ))}
        </div>
      </div>
    );
  }

  return null;
}

function SlideRenderer({ slide, design }: { slide: SlidePage; design: DesignSystem }) {
  const pal = design.palette;
  const fonts = design.fonts;
  const ts = design.type_scale;
  const radius = design.radius;
  const layout = slide.layout;

  const fill: React.CSSProperties = {
    width: CANVAS_WIDTH,
    height: CANVAS_HEIGHT,
    background: pal.bg,
    color: pal.text,
    fontFamily: fonts.body,
    padding: '80px 120px',
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
    overflow: 'hidden',
  };

  if (layout === 'cover') {
    return (
      <div style={fill}>
        {slide.eyebrow && (
          <div style={{ fontSize: ts.body * 0.6, textTransform: 'uppercase', letterSpacing: 4, color: pal.accent, marginBottom: 16, fontWeight: 600 }}>
            {slide.eyebrow}
          </div>
        )}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
          <div style={{ fontSize: ts.hero, fontFamily: fonts.display, fontWeight: 700, lineHeight: 1.1, marginBottom: 24 }}>
            {slide.title}
          </div>
          {slide.subtitle && (
            <div style={{ fontSize: ts.body, color: pal.accent, fontWeight: 400 }}>{slide.subtitle}</div>
          )}
        </div>
      </div>
    );
  }

  if (layout === 'section') {
    return (
      <div style={fill}>
        {slide.eyebrow && (
          <div style={{ fontSize: ts.body * 0.6, textTransform: 'uppercase', letterSpacing: 4, color: pal.accent, marginBottom: 16, fontWeight: 600 }}>
            {slide.eyebrow}
          </div>
        )}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ fontSize: ts.hero * 0.7, fontFamily: fonts.display, fontWeight: 700, textAlign: 'center', lineHeight: 1.2 }}>
            {slide.title}
          </div>
        </div>
      </div>
    );
  }

  if (layout === 'closing') {
    return (
      <div style={fill}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
          <div style={{ fontSize: ts.hero * 0.8, fontFamily: fonts.display, fontWeight: 700 }}>
            {slide.title}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={fill}>
      {slide.eyebrow && (
        <div style={{ fontSize: ts.body * 0.6, textTransform: 'uppercase', letterSpacing: 4, color: pal.accent, marginBottom: 16, fontWeight: 600 }}>
          {slide.eyebrow}
        </div>
      )}
      {slide.title && (
        <div style={{ fontSize: ts.body * 1.8, fontFamily: fonts.display, fontWeight: 700, marginBottom: 40, lineHeight: 1.2 }}>
          {slide.title}
        </div>
      )}
      {slide.subtitle && (
        <div style={{ fontSize: ts.body, color: pal.accent, marginBottom: 24 }}>{slide.subtitle}</div>
      )}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'row', gap: 32 }}>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          {(slide.components || []).map((comp, i) => (
            <React.Fragment key={i}>{renderComponent(comp, design)}</React.Fragment>
          ))}
        </div>
        {slide.image_url && (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <img src={slide.image_url} style={{ maxWidth: '100%', maxHeight: '100%', borderRadius: radius, objectFit: 'contain' as const }} />
          </div>
        )}
      </div>
    </div>
  );
}

export function SlideCanvas({ slide, design }: { slide: SlidePage; design: DesignSystem }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);

  const updateScale = useCallback(() => {
    if (!containerRef.current) return;
    const parent = containerRef.current.parentElement;
    if (!parent) return;
    const w = parent.clientWidth - 48;
    const h = parent.clientHeight - 48;
    const s = Math.min(w / CANVAS_WIDTH, h / CANVAS_HEIGHT, 1);
    setScale(s);
  }, []);

  useEffect(() => {
    updateScale();
    const ro = new ResizeObserver(updateScale);
    if (containerRef.current?.parentElement) ro.observe(containerRef.current.parentElement);
    window.addEventListener('resize', updateScale);
    return () => { ro.disconnect(); window.removeEventListener('resize', updateScale); };
  }, [updateScale, slide]);

  return (
    <div ref={containerRef} style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `scale(${scale})`, transformOrigin: 'center', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <SlideRenderer slide={slide} design={design} />
    </div>
  );
}
