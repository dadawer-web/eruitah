from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class DesignPalette(BaseModel):
    bg: str = Field(
        "#f7f5f0",
        description="画布背景色 (hex)。映射为 CSS 变量 --osd-bg。示例: '#f7f5f0' (暖白), '#0a0e14' (深色)",
    )
    text: str = Field(
        "#1a1814",
        description="正文文字颜色 (hex)。映射为 CSS 变量 --osd-text。示例: '#1a1814' (深棕), '#e6edf3' (浅灰)",
    )
    accent: str = Field(
        "#6d4cff",
        description="强调色 (hex)。映射为 CSS 变量 --osd-accent。用于 eyebrow、链接、高亮元素。示例: '#6d4cff' (紫), '#6ee7ff' (青)",
    )


class DesignFonts(BaseModel):
    display: str = Field(
        'Georgia, "Times New Roman", serif',
        description="标题/展示字体栈。映射为 CSS 变量 --osd-font-display。用于 h1/h2 和封面大标题。示例: 'Georgia, serif' (经典), '\"JetBrains Mono\", monospace' (极客)",
    )
    body: str = Field(
        '-apple-system, BlinkMacSystemFont, "Inter", system-ui, sans-serif',
        description="正文/界面字体栈。映射为 CSS 变量 --osd-font-body。用于段落、列表、标签。示例: 'system-ui, sans-serif' (通用), '\"Inter\", sans-serif' (现代)",
    )


class DesignTypeScale(BaseModel):
    hero: int = Field(
        168,
        description="封面标题字号 (px)。映射为 CSS 变量 --osd-size-hero。范围: 120-200。示例: 168 (经典), 196 (大号), 132 (紧凑)",
    )
    body: int = Field(
        36,
        description="正文字号 (px)。映射为 CSS 变量 --osd-size-body。范围: 24-40。示例: 36 (标准), 28 (紧凑), 34 (舒适)",
    )


class DesignSystem(BaseModel):
    palette: DesignPalette = Field(
        default_factory=DesignPalette,
        description="调色板。3 个核心颜色，分别映射为 --osd-bg / --osd-text / --osd-accent",
    )
    fonts: DesignFonts = Field(
        default_factory=DesignFonts,
        description="字体栈。display 用于标题，body 用于正文，分别映射为 --osd-font-display / --osd-font-body",
    )
    type_scale: DesignTypeScale = Field(
        default_factory=DesignTypeScale,
        description="字号体系。hero 用于封面大标题，body 用于正文，分别映射为 --osd-size-hero / --osd-size-body",
    )
    radius: int = Field(
        12,
        description="全局圆角半径 (px)。映射为 CSS 变量 --osd-radius。用于卡片、代码块、按钮等。示例: 12 (柔和), 6 (锐利), 16 (圆润)",
    )


class SlideMeta(BaseModel):
    title: Optional[str] = Field(
        None,
        description="演示文稿标题。显示在浏览器标签和幻灯片浏览器中。示例: 'How LLMs Work'",
    )
    theme: Optional[str] = Field(
        None,
        description="主题标识符。用于将幻灯片分组到不同主题。示例: 'light', 'dark', 'brand'",
    )


class SlideComponent(BaseModel):
    type: Literal[
        "heading",
        "text",
        "code",
        "bullet_list",
        "image",
        "divider",
        "card",
        "two_column",
    ] = Field(
        ...,
        description=(
            "组件类型。"
            "heading: 小节标题，content 为标题文字；"
            "text: 普通段落，content 为文本；"
            "code: 代码块，content 为代码，language 为语言名；"
            "bullet_list: 无序列表，items 为列表项数组；"
            "image: 图片，image_url 为图片地址；"
            "divider: 水平分隔线；"
            "card: 卡片容器，content 为内容，accent 为边框强调色；"
            "two_column: 双栏布局，content 为左栏文本，items 为右栏内容列表"
        ),
    )
    content: str = Field(
        "",
        description="组件的主要内容。对于 heading/text/card/two_column 为文本内容，对于 code 为代码内容",
    )
    items: Optional[List[str]] = Field(
        None,
        description="列表项数组。仅 bullet_list 和 two_column 使用。bullet_list 的每一项为一个列表条目；two_column 的 items 为右栏内容列表",
    )
    language: Optional[str] = Field(
        None,
        description="代码语言标识。仅 code 组件使用。示例: 'python', 'sql', 'typescript', 'bash'",
    )
    image_url: Optional[str] = Field(
        None,
        description="图片 URL。仅 image 组件使用。支持相对路径和绝对 URL",
    )
    accent: Optional[str] = Field(
        None,
        description="强调色 (hex)。仅 card 组件使用。用于卡片左边框和背景色。示例: '#6d4cff'",
    )
    style: Optional[Dict[str, Any]] = Field(
        None,
        description="额外 CSS 样式覆盖。键为 CSS 属性名（camelCase），值为 CSS 值。示例: {'marginTop': 40, 'maxWidth': 1500}",
    )


class SlidePage(BaseModel):
    layout: Literal[
        "cover",
        "section",
        "content",
        "two_column",
        "code_focus",
        "image_text",
        "closing",
    ] = Field(
        "content",
        description=(
            "页面布局类型。"
            "cover: 封面页，居中大标题 + eyebrow + subtitle，无 components；"
            "section: 章节分隔页，居中大标题，无 components；"
            "content: 标准内容页，标题 + components 列表（最常用）；"
            "two_column: 双栏内容页，components 中使用 two_column 组件；"
            "code_focus: 代码展示页，突出代码块；"
            "image_text: 图文混排页；"
            "closing: 结尾页，居中致谢文字，无 components"
        ),
    )
    title: str = Field(
        "",
        description=(
            "页面标题。对于 cover/section/closing 为居中大标题；"
            "对于 content 等为左上角标题。"
            "使用 design.fonts.display 字体渲染"
        ),
    )
    subtitle: Optional[str] = Field(
        None,
        description="副标题。仅 cover 布局使用，显示在标题下方，使用 accent 颜色",
    )
    eyebrow: Optional[str] = Field(
        None,
        description=(
            "标题上方的小标签。全大写、宽字距、accent 颜色。"
            "用于标注章节或分类。示例: 'A field guide · 2026', 'Definition', 'Attention'"
        ),
    )
    components: List[SlideComponent] = Field(
        default_factory=list,
        description=(
            "页面组件列表。仅在 content/two_column/code_focus/image_text 布局中使用。"
            "cover/section/closing 布局应设为空数组。"
            "每页建议 2-5 个组件"
        ),
    )
    notes: Optional[str] = Field(
        None,
        description="演讲者备注。不显示在幻灯片上，仅在演示者模式中可见",
    )
    image_prompt: str = Field(
        ...,
        description=(
            "配图关键词（极其重要，必须严格包含此字段！）。"
            "如果该页适合配图（封面、过渡页或举例页），请提供简短的纯英文画面描述关键词，如 'cyberpunk city', 'business meeting'。"
            "如果纯代码页或绝对不需要配图，必须填写字符串 'none'。"
            "绝对不允许省略此字段或设为 null！"
        ),
    )
    image_search_keyword: str = Field(
        "",
        description=(
            "【极其重要】用于在图库搜索配图的英文关键词。必须是具象的名词组合，最多3个词。"
            "绝对禁止使用抽象名词（如：Strategy, Development, Summary, AI, Teamwork）。"
            "必须转化为具体的视觉元素！示例：'Chess board king', 'People high five office', 'Glowing charts screen'"
        ),
    )
    image_visual_description: str = Field(
        "",
        description=(
            "对当前页面配图的详细画面描述，用于辅助判断图文相关性。"
            "示例：'一只发光的机械手触碰全息网络图，深蓝色背景，科技感十足'"
        ),
    )
    image_url: Optional[str] = Field(
        None,
        description="自动生成的配图 URL。由系统根据 image_search_keyword 自动注入，不需要 AI 填写",
    )


class Presentation(BaseModel):
    meta: SlideMeta = Field(
        default_factory=SlideMeta,
        description="演示文稿元数据。包含标题和主题标识",
    )
    design: DesignSystem = Field(
        default_factory=DesignSystem,
        description=(
            "设计系统。定义全局视觉风格，产生 8 个 CSS 变量: "
            "--osd-bg, --osd-text, --osd-accent, "
            "--osd-font-display, --osd-font-body, "
            "--osd-size-hero, --osd-size-body, --osd-radius。"
            "所有页面共享此设计系统"
        ),
    )
    slides: List[SlidePage] = Field(
        ...,
        description=(
            "幻灯片页面列表。对应 open-slide 的 Page[]。"
            "每个元素代表一页 1920x1080 的幻灯片。"
            "建议 5-15 页。第一页应为 cover 布局，最后一页应为 closing 布局"
        ),
    )
