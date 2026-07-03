import {
  ArrowRight,
  BookOpenText,
  Brain,
  CaretRight,
  ChatCircleText,
  CheckCircle,
  ClipboardText,
  CloudArrowDown,
  Command,
  DownloadSimple,
  GithubLogo,
  GraduationCap,
  Graph,
  Lightning,
  MagicWand,
  Monitor,
  Moon,
  PaperPlaneTilt,
  PlugsConnected,
  Sidebar,
  Sparkle,
  Sun,
  Target,
  UploadSimple
} from "@phosphor-icons/react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { type CSSProperties, type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

type ThemeMode = "system" | "light" | "dark";
type ResolvedTheme = "light" | "dark";
type WorkbenchTab = "branch" | "import" | "settings" | "skills";
type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
};

const GITHUB_URL = "https://github.com/q2955161835-debug/lang-drill-agent";
const DOWNLOAD_URL =
  "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v0.1.0/Lang.Drill.Agent_0.1.0_x64-setup.exe";

const themeLabels: Record<ThemeMode, string> = {
  system: "系统",
  light: "浅色",
  dark: "深色"
};

const galaxyWords = [
  ["context", 12, 18, 0.95, 0],
  ["deliberate", 8, 34, 0.72, -4],
  ["collection", 23, 27, 0.86, -8],
  ["evidence", 16, 58, 0.66, -12],
  ["synonym", 32, 14, 0.62, -16],
  ["contrast", 40, 35, 0.78, -20],
  ["語彙", 83, 18, 0.88, -2],
  ["試験", 90, 34, 1.05, -6],
  ["復習", 78, 51, 0.92, -10],
  ["文脈", 68, 26, 0.74, -14],
  ["理解", 72, 67, 0.66, -18],
  ["間違い", 88, 70, 0.58, -22],
  ["answer", 45, 66, 0.62, -5],
  ["reading", 53, 20, 0.64, -11],
  ["drill", 60, 56, 0.72, -17],
  ["文化", 28, 48, 0.82, -23]
] as const;

const stageWords = [
  "context",
  "deliberate",
  "文化",
  "試験",
  "復習",
  "collocation",
  "evidence",
  "作文",
  "reading",
  "grammar",
  "blank",
  "review"
] as const;

const featureCards = [
  {
    icon: BookOpenText,
    title: "词表不再停在词表",
    text: "截图、粘贴、文件导入后的单词会进入学习库，随后生成考试式语境题，而不是只做释义卡片。"
  },
  {
    icon: Target,
    title: "刷题回到具体词条",
    text: "每道题、每次作答和讲解都写入数据库，错因可以回流到词汇掌握度和后续复习。"
  },
  {
    icon: Brain,
    title: "模型负责讲解，程序负责状态",
    text: "Agent 生成题目和个性化讲解，应用负责题组落库、判分、推进和统计，避免学习记录散在聊天里。"
  }
] as const;

const screenshots = [
  {
    src: "./assets/screenshots/dark-active-question.png",
    title: "吸附题卡",
    text: "当前题留在聊天主线里，作答后自动推进下一题。"
  },
  {
    src: "./assets/screenshots/light-completed-day.png",
    title: "当日学习",
    text: "题目完成、词汇掌握和历史会话按考试范围归档。"
  },
  {
    src: "./assets/screenshots/dark-screenshot-import.png",
    title: "截图导入",
    text: "先解析、再编辑词条，确认后才开始练习。"
  },
  {
    src: "./assets/screenshots/dark-settings-model.png",
    title: "模型配置",
    text: "供应商、模型、视觉能力和思考等级在设置中统一维护。"
  },
  {
    src: "./assets/screenshots/light-mobile-home.png",
    title: "移动视口",
    text: "核心学习面板在窄屏下仍可浏览。"
  }
] as const;

const modelOptions = [
  "OpenAI GPT / gpt-4.1",
  "Claude / claude-sonnet-4",
  "DeepSeek / deepseek-chat",
  "Xiaomi MiMo / mimo-v2.5-pro"
] as const;

const examOptions = ["CET-4 英语四级", "CET-6 英语六级", "CJT4 日语四级", "CFT-4 法语四级"] as const;
const syllabusOptions = ["全国大学英语四、六级考试大纲 2016", "近三年真题摘要", "自定义考试目标"] as const;

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function App() {
  const pageRef = useRef<HTMLDivElement>(null);
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => getSystemTheme());
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    const saved = window.localStorage.getItem("langdrill-site-theme");
    return saved === "light" || saved === "dark" || saved === "system" ? saved : "system";
  });

  const resolvedTheme = themeMode === "system" ? systemTheme : themeMode;

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const syncTheme = () => setSystemTheme(media.matches ? "light" : "dark");
    syncTheme();
    media.addEventListener("change", syncTheme);
    return () => media.removeEventListener("change", syncTheme);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themeMode = themeMode;
    window.localStorage.setItem("langdrill-site-theme", themeMode);
  }, [resolvedTheme, themeMode]);

  useEffect(() => {
    const scrollToHash = () => {
      const targetId = window.location.hash.replace("#", "");
      if (!targetId) {
        return;
      }
      const alignTarget = () => {
        ScrollTrigger.refresh();
        const target = document.getElementById(targetId);
        if (!target) {
          return;
        }
        const header = document.querySelector<HTMLElement>(".site-header");
        const headerOffset = (header?.offsetHeight ?? 56) + 28;
        const top = Math.max(target.getBoundingClientRect().top + window.scrollY - headerOffset, 0);
        window.scrollTo({ top, behavior: "auto" });
      };
      [80, 320, 900].forEach((delay) => window.setTimeout(alignTarget, delay));
    };
    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);
    return () => window.removeEventListener("hashchange", scrollToHash);
  }, []);

  useGSAP(
    () => {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return;
      }

      gsap.from(".hero-copy > *", {
        y: 28,
        opacity: 0,
        duration: 0.9,
        ease: "power3.out",
        stagger: 0.08
      });

      gsap.from(".hero-device", {
        y: 56,
        opacity: 0,
        scale: 0.96,
        duration: 1.1,
        ease: "power3.out",
        delay: 0.2
      });

      const stageTimeline = gsap.timeline({
        scrollTrigger: {
          trigger: ".conversion-stage",
          start: "top 58%",
          end: "bottom 18%",
          scrub: 1
        }
      });

      stageTimeline
        .to(
          ".stage-word",
          {
            x: (index) => -160 + (index % 4) * 38,
            y: (index) => -44 + Math.floor(index / 4) * 34,
            scale: 0.86,
            opacity: 0.92,
            stagger: 0.025,
            ease: "none"
          },
          0
        )
        .to(
          ".stage-flow-line",
          {
            scaleX: 1,
            opacity: 1,
            ease: "none"
          },
          0.08
        )
        .to(
          ".stage-app-window",
          {
            scale: 1.04,
            y: -18,
            ease: "none"
          },
          0.18
        )
        .to(
          ".stage-word",
          {
            x: (index) => 250 + (index % 3) * 35,
            y: (index) => -72 + Math.floor(index / 3) * 28,
            opacity: 0.18,
            stagger: 0.018,
            ease: "none"
          },
          0.42
        )
        .fromTo(
          ".stage-question",
          { x: 250, y: -80, opacity: 0, rotate: -4, scale: 0.92 },
          {
            x: 0,
            y: 0,
            opacity: 1,
            rotate: 0,
            scale: 1,
            stagger: 0.06,
            ease: "none"
          },
          0.54
        )
        .to(
          ".stage-question",
          {
            y: 220,
            x: (index) => (index - 1) * 210,
            rotate: (index) => (index - 1) * 3,
            ease: "none"
          },
          0.72
        );

      gsap.utils.toArray<HTMLElement>(".reveal").forEach((element) => {
        gsap.from(element, {
          y: 44,
          opacity: 0,
          duration: 0.85,
          ease: "power3.out",
          scrollTrigger: {
            trigger: element,
            start: "top 84%",
            toggleActions: "play none none reverse"
          }
        });
      });
    },
    { scope: pageRef }
  );

  return (
    <div ref={pageRef} className="site-shell">
      <SiteHeader themeMode={themeMode} onThemeModeChange={setThemeMode} />
      <main>
        <HeroSection />
        <ConversionStage />
        <PainSection />
        <ScreenshotShowcase />
        <DemoAppSection />
      </main>
      <SiteFooter />
    </div>
  );
}

function SiteHeader({
  themeMode,
  onThemeModeChange
}: {
  themeMode: ThemeMode;
  onThemeModeChange: (mode: ThemeMode) => void;
}) {
  return (
    <header className="site-header">
      <a className="brand-mark" href="#top" aria-label="Lang Drill Agent">
        <img className="brand-logo brand-logo-light" src="./assets/logo-light.png" alt="" />
        <img className="brand-logo brand-logo-dark" src="./assets/logo-dark.png" alt="" />
        <span>Lang Drill Agent</span>
      </a>
      <nav className="site-nav" aria-label="主导航">
        <a href="#flow">闭环</a>
        <a href="#features">功能</a>
        <a href="#screens">界面</a>
        <a href="#demo">前端展示</a>
      </nav>
      <div className="header-actions">
        <ThemeSwitch themeMode={themeMode} onThemeModeChange={onThemeModeChange} />
        <a className="ghost-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
          <GithubLogo weight="fill" />
          GitHub
        </a>
        <a className="solid-button" href={DOWNLOAD_URL}>
          <DownloadSimple weight="bold" />
          Download
        </a>
      </div>
    </header>
  );
}

function ThemeSwitch({
  themeMode,
  onThemeModeChange
}: {
  themeMode: ThemeMode;
  onThemeModeChange: (mode: ThemeMode) => void;
}) {
  const modes: Array<{ mode: ThemeMode; icon: ReactNode }> = [
    { mode: "system", icon: <Monitor weight="bold" /> },
    { mode: "light", icon: <Sun weight="bold" /> },
    { mode: "dark", icon: <Moon weight="bold" /> }
  ];

  return (
    <div className="theme-switch" aria-label="主题切换">
      {modes.map((item) => (
        <button
          key={item.mode}
          type="button"
          className={item.mode === themeMode ? "active" : ""}
          title={themeLabels[item.mode]}
          aria-label={themeLabels[item.mode]}
          onClick={() => onThemeModeChange(item.mode)}
        >
          {item.icon}
        </button>
      ))}
    </div>
  );
}

function HeroSection() {
  return (
    <section id="top" className="hero-section">
      <WordGalaxy />
      <div className="hero-copy">
        <h1>Lang Drill Agent</h1>
        <p>把词表变成题组，把作答变成复习。</p>
        <div className="hero-actions">
          <a className="solid-button large" href="#demo">
            Explore demo <ArrowRight weight="bold" />
          </a>
          <a className="ghost-button large" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GithubLogo weight="fill" />
            GitHub
          </a>
        </div>
      </div>
      <div className="hero-device">
        <MiniWorkspace />
      </div>
    </section>
  );
}

function WordGalaxy() {
  return (
    <div className="word-galaxy" aria-hidden="true">
      <div className="galaxy-ring ring-a" />
      <div className="galaxy-ring ring-b" />
      <div className="galaxy-core" />
      {galaxyWords.map(([text, x, y, scale, delay]) => (
        <span
          key={`${text}-${x}`}
          className="galaxy-word"
          style={
            {
              left: `${x}%`,
              top: `${y}%`,
              "--scale": scale,
              "--delay": `${delay}s`
            } as CSSProperties
          }
        >
          {text}
        </span>
      ))}
    </div>
  );
}

function MiniWorkspace() {
  return (
    <div className="mini-workspace">
      <div className="mini-titlebar">
        <span />
        <span />
        <span />
        <strong>Lang Drill Agent</strong>
      </div>
      <div className="mini-columns">
        <aside className="mini-left">
          <div className="mini-section-title">当日学习</div>
          <strong>8/12 题</strong>
          <div className="meter">
            <i style={{ width: "66%" }} />
          </div>
          {["context", "deliberate", "文化", "試験"].map((word) => (
            <div className="word-row" key={word}>
              <span>{word}</span>
              <small>ready</small>
            </div>
          ))}
        </aside>
        <section className="mini-center">
          <div className="chat-strip user">请把这组词变成四级题。</div>
          <div className="chat-strip assistant">已生成 6 道语境题。</div>
          <div className="question-card active">
            <small>当前题目：第 1 题 / 共 6 题</small>
            <strong>The museum has a large _____ of local paintings.</strong>
            <div className="option-grid">
              <span>A. collection</span>
              <span>B. collision</span>
              <span>C. waterfall</span>
              <span>D. germ</span>
            </div>
          </div>
        </section>
        <aside className="mini-right">
          <div className="mini-section-title">Branch / Import</div>
          <div className="import-row">截图词表</div>
          <div className="import-row">文件文本</div>
          <div className="import-row">分支讲解</div>
        </aside>
      </div>
    </div>
  );
}

function ConversionStage() {
  return (
    <section id="flow" className="conversion-stage">
      <div className="section-heading stage-heading">
        <h2>单词进入工作台，题目带着进度出来。</h2>
        <p>滚动时，词条汇聚到左栏；中间 Agent 组卷；右侧输出题卡，落到下方演示练习区域。</p>
      </div>
      <div className="stage-canvas">
        <div className="stage-flow-line" />
        <div className="stage-word-layer" aria-hidden="true">
          {stageWords.map((word, index) => (
            <span
              key={word}
              className="stage-word"
              style={
                {
                  left: `${8 + (index % 4) * 8}%`,
                  top: `${42 + Math.floor(index / 4) * 10}%`
                } as CSSProperties
              }
            >
              {word}
            </span>
          ))}
        </div>
        <div className="stage-app-window">
          <MiniWorkspace />
        </div>
        <div className="stage-question-layer" aria-hidden="true">
          {["语境填空", "同义改写", "阅读判断"].map((title, index) => (
            <div key={title} className="question-card stage-question">
              <small>
                {index + 1} / 3 · {title}
              </small>
              <strong>
                {index === 0
                  ? "Which word best fits the blank?"
                  : index === 1
                    ? "Rewrite the sentence with the same meaning."
                    : "What does the passage imply?"}
              </strong>
              <div className="option-grid compact">
                <span>A. context</span>
                <span>B. deliberate</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PainSection() {
  return (
    <section id="features" className="pain-section reveal">
      <div className="section-heading">
        <h2>核心痛点：背词和刷题分离。</h2>
        <p>
          Lang Drill Agent 把“导入词表、生成题组、逐题作答、讲解、错题回流”做成同一条学习路径。
        </p>
      </div>
      <div className="feature-grid">
        {featureCards.map((card) => {
          const Icon = card.icon;
          return (
            <article className="feature-card reveal" key={card.title}>
              <span className="feature-icon">
                <Icon weight="duotone" />
              </span>
              <h3>{card.title}</h3>
              <p>{card.text}</p>
            </article>
          );
        })}
      </div>
      <div className="loop-panel reveal">
        <div>
          <h3>从词表到题组的闭环</h3>
          <p>用户不需要在背词软件、题库、笔记和错题本之间来回搬运。</p>
        </div>
        <div className="loop-steps" aria-label="学习闭环">
          <span>导入词表</span>
          <CaretRight weight="bold" />
          <span>考试式组卷</span>
          <CaretRight weight="bold" />
          <span>作答讲解</span>
          <CaretRight weight="bold" />
          <span>复习回流</span>
        </div>
      </div>
    </section>
  );
}

function ScreenshotShowcase() {
  return (
    <section id="screens" className="screens-section">
      <div className="section-heading reveal">
        <h2>真实前端素材，包装成产品展示节奏。</h2>
        <p>这些脱敏截图来自演示数据库，网站里同时保留可交互的三栏工作台模拟器。</p>
      </div>
      <div className="screenshot-rail">
        {screenshots.map((item) => (
          <article className="screenshot-card reveal" key={item.src}>
            <img src={item.src} alt={item.title} loading="lazy" />
            <div>
              <strong>{item.title}</strong>
              <span>{item.text}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function DemoAppSection() {
  return (
    <section id="demo" className="demo-section">
      <div className="section-heading reveal">
        <h2>完整前端展示壳。</h2>
        <p>这里不连接真实后端，保留可探索的模型选择、考试选择、考纲、分支、导入和拓展 Skills 占位。</p>
      </div>
      <div className="demo-frame reveal">
        <DemoWorkbench />
      </div>
    </section>
  );
}

function DemoWorkbench() {
  const [tab, setTab] = useState<WorkbenchTab>("import");
  const [input, setInput] = useState("");
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [model, setModel] = useState<(typeof modelOptions)[number]>(modelOptions[3]);
  const [exam, setExam] = useState<(typeof examOptions)[number]>(examOptions[0]);
  const [syllabus, setSyllabus] = useState<(typeof syllabusOptions)[number]>(syllabusOptions[0]);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: "assistant",
      text:
        "我是 Lang Drill Agent 的产品演示模式。你可以在这里探索三栏界面、模型选择、截图导入、分支和拓展 Skills。"
    }
  ]);
  const streamRef = useRef<HTMLDivElement>(null);

  const currentModelSummary = useMemo(() => {
    const [provider, modelName] = model.split(" / ");
    return `${provider} · ${modelName}`;
  }, [model]);

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) {
      return;
    }
    const baseId = Date.now();
    setMessages((current) => [
      ...current,
      { id: baseId, role: "user", text: trimmed },
      {
        id: baseId + 1,
        role: "assistant",
        text:
          "我是 Lang Drill Agent：一个把词表、题组、作答、讲解和复习连接起来的语言学习 Agent。网页版使用正在开发中，暂不支持真实模型调用，敬请期待。你可以继续在当前网页中探索功能演示。"
      }
    ]);
    setInput("");
  }

  return (
    <div className="workbench-shell">
      <aside className="workbench-left">
        <div className="rail-top">
          <Sidebar weight="bold" />
          <strong>Lang Drill</strong>
        </div>
        <div className="daily-card">
          <div className="daily-card-head">
            <Target weight="bold" />
            <strong>当日学习</strong>
          </div>
          <div className="daily-score">
            <strong>2026-07-03</strong>
            <span>8/12 题</span>
          </div>
          <div className="meter">
            <i style={{ width: "66%" }} />
          </div>
          <small>当日词汇 18/30</small>
          <div className="word-list">
            <span>↳ context</span>
            <span>↳ deliberate</span>
            <span>↳ 試験</span>
          </div>
        </div>
        <button className="new-chat-button" type="button">
          + 新建聊天
        </button>
        <div className="session-group">
          <strong>2026-07-03</strong>
          <button className="session active" type="button">
            截图词表练习：context
          </button>
          <button className="session" type="button">
            阅读语境综合训练
          </button>
        </div>
        <button className="settings-button" type="button" onClick={() => setTab("settings")}>
          <Command weight="bold" />
          设置
        </button>
      </aside>
      <main className="workbench-main">
        <div className="workbench-toolbar">
          <select value={model} onChange={(event) => setModel(event.target.value as (typeof modelOptions)[number])}>
            {modelOptions.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <select value={exam} onChange={(event) => setExam(event.target.value as (typeof examOptions)[number])}>
            {examOptions.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <select
            value={syllabus}
            onChange={(event) => setSyllabus(event.target.value as (typeof syllabusOptions)[number])}
          >
            {syllabusOptions.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="message-stream-demo" ref={streamRef}>
          <div className="context-card">
            <Sparkle weight="duotone" />
            <div>
              <strong>{currentModelSummary}</strong>
              <span>{exam} · {syllabus}</span>
            </div>
          </div>
          {messages.map((message) => (
            <article className={`demo-message ${message.role}`} key={message.id}>
              <div className="demo-avatar">{message.role === "assistant" ? "L" : "你"}</div>
              <p>{message.text}</p>
            </article>
          ))}
          <QuestionDock selectedOption={selectedOption} onSelect={setSelectedOption} />
        </div>
        <form className="chat-composer" onSubmit={submitMessage}>
          <button type="button" aria-label="上传文件">
            <UploadSimple weight="bold" />
          </button>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入学习内容、答案或任何学习请求"
          />
          <button className="send-button" type="submit" aria-label="发送">
            <PaperPlaneTilt weight="fill" />
          </button>
        </form>
      </main>
      <aside className="workbench-right">
        <div className="right-tabs" role="tablist" aria-label="右侧工作台">
          <button className={tab === "branch" ? "active" : ""} type="button" onClick={() => setTab("branch")}>
            分支
          </button>
          <button className={tab === "import" ? "active" : ""} type="button" onClick={() => setTab("import")}>
            导入
          </button>
          <button className={tab === "skills" ? "active" : ""} type="button" onClick={() => setTab("skills")}>
            Skills
          </button>
          <button className={tab === "settings" ? "active" : ""} type="button" onClick={() => setTab("settings")}>
            设置
          </button>
        </div>
        <RightPanel tab={tab} />
      </aside>
    </div>
  );
}

function QuestionDock({
  selectedOption,
  onSelect
}: {
  selectedOption: string | null;
  onSelect: (option: string) => void;
}) {
  const options = ["A. collection", "B. collision", "C. waterfall", "D. germ"];
  return (
    <div className="demo-question-dock">
      <div className="dock-title">
        <CheckCircle weight="bold" />
        <strong>当前题目：第 1 题 / 共 6 题</strong>
      </div>
      <p>The museum has a large _____ of local paintings and old photographs.</p>
      <div className="demo-options">
        {options.map((option) => (
          <button
            key={option}
            className={selectedOption === option ? "selected" : ""}
            type="button"
            onClick={() => onSelect(option)}
          >
            {option}
          </button>
        ))}
      </div>
      {selectedOption && (
        <div className={selectedOption === "A. collection" ? "feedback correct" : "feedback"}>
          {selectedOption === "A. collection"
            ? "正确。collection 可以表示“收藏品、藏品集合”。"
            : "演示判题：正确答案是 A. collection。"}
        </div>
      )}
    </div>
  );
}

function RightPanel({ tab }: { tab: WorkbenchTab }) {
  if (tab === "branch") {
    return (
      <div className="right-panel">
        <h3>分支追问</h3>
        <div className="reference-card">
          <small>引用当前题目</small>
          <strong>The museum has a large _____ of local paintings.</strong>
        </div>
        <textarea placeholder="围绕引用内容追问，例如：为什么不用 collision？" />
        <button className="inline-primary" type="button">
          创建分支
        </button>
      </div>
    );
  }

  if (tab === "skills") {
    return (
      <div className="right-panel">
        <h3>拓展 Skills</h3>
        <SkillCard name="skill1" path="/skills/default/skill1" enabled />
        <SkillCard name="skill2" path="/skills/default/skill2" />
        <SkillCard name="multi-search-engine" path="/skills/search/multi-search-engine" enabled />
      </div>
    );
  }

  if (tab === "settings") {
    return (
      <div className="right-panel">
        <h3>设置演示</h3>
        <label>
          模型供应商
          <select defaultValue="Xiaomi MiMo">
            <option>OpenAI GPT</option>
            <option>Claude</option>
            <option>DeepSeek</option>
            <option>Xiaomi MiMo</option>
          </select>
        </label>
        <label>
          当前考试
          <select defaultValue="CET-4">
            <option>CET-4</option>
            <option>CET-6</option>
            <option>CJT4</option>
            <option>CFT-4</option>
          </select>
        </label>
        <div className="fake-path">
          <small>数据目录</small>
          <code>%APPDATA%\Lang Drill Agent\data</code>
        </div>
      </div>
    );
  }

  return (
    <div className="right-panel">
      <h3>截图 / 文件导入</h3>
      <div className="drop-zone">
        <CloudArrowDown weight="duotone" />
        <strong>拖入截图、PDF、DOCX 或 TXT</strong>
        <span>演示模式不会上传文件。</span>
      </div>
      <div className="vocab-card">
        <span>context</span>
        <small>n. 语境；上下文</small>
      </div>
      <div className="vocab-card">
        <span>復習</span>
        <small>n. 复习</small>
      </div>
      <button className="inline-primary" type="button">
        导入并开始练习
      </button>
    </div>
  );
}

function SkillCard({ name, path, enabled = false }: { name: string; path: string; enabled?: boolean }) {
  return (
    <div className="skill-card">
      <div>
        <strong>{name}</strong>
        <code>{path}</code>
      </div>
      <span className={enabled ? "skill-state on" : "skill-state"}>{enabled ? "开启" : "关闭"}</span>
    </div>
  );
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div>
        <img className="brand-logo brand-logo-light" src="./assets/logo-light.png" alt="" />
        <img className="brand-logo brand-logo-dark" src="./assets/logo-dark.png" alt="" />
        <strong>Lang Drill Agent</strong>
      </div>
      <p>静态展示站点，适合部署到 GitHub Pages。真实学习流程请使用桌面版或本地 Web 版。</p>
      <div className="footer-links">
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">
          <GithubLogo weight="fill" />
          GitHub
        </a>
        <a href={DOWNLOAD_URL}>
          <DownloadSimple weight="bold" />
          Download
        </a>
      </div>
    </footer>
  );
}

export default App;
