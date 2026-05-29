export interface DesignPalette {
  bg: string;
  text: string;
  accent: string;
}

export interface DesignFonts {
  display: string;
  body: string;
}

export interface DesignTypeScale {
  hero: number;
  body: number;
}

export interface DesignSystem {
  palette: DesignPalette;
  fonts: DesignFonts;
  type_scale: DesignTypeScale;
  radius: number;
}

export interface SlideComponent {
  type: 'heading' | 'text' | 'code' | 'bullet_list' | 'image' | 'divider' | 'card' | 'two_column';
  content?: string;
  items?: string[];
  language?: string;
  image_url?: string;
  accent?: string;
  style?: Record<string, any>;
}

export interface SlidePage {
  layout: 'cover' | 'section' | 'content' | 'two_column' | 'code_focus' | 'image_text' | 'closing';
  title: string;
  subtitle?: string;
  eyebrow?: string;
  components: SlideComponent[];
  notes?: string;
}

export interface SlideMeta {
  title?: string;
  theme?: string;
}

export interface Presentation {
  meta: SlideMeta;
  design: DesignSystem;
  slides: SlidePage[];
}

export const CANVAS_WIDTH = 1920;
export const CANVAS_HEIGHT = 1080;
