import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import {
  ArrowRight,
  BookOpenText,
  Brain,
  Cards,
  ChatsCircle,
  CheckCircle,
  Database,
  DeviceMobile,
  DownloadSimple,
  Gauge,
  GearSix,
  GitBranch,
  GithubLogo,
  ImageSquare,
  ListChecks,
  Monitor,
  Moon,
  PaperPlaneTilt,
  Play,
  PlugsConnected,
  Sparkle,
  Sun,
  UploadSimple,
  XCircle,
} from "@phosphor-icons/react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP, ScrollTrigger);

type ThemeChoice = "dark" | "light" | "system";
type WorkbenchTab = "branch" | "import" | "skills" | "settings";
type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

const GITHUB_URL = "https://github.com/q2955161835-debug/lang-drill-agent";
const DOWNLOAD_URL =
  "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v0.1.0/Lang.Drill.Agent_0.1.0_x64-setup.exe";

const THEME_LABEL: Record<ThemeChoice, string> = {
  dark: "深色",
  light: "浅色",
  system: "跟随系统",
};

const GALAXY_TERMS = [
  "achieve",
  "believe",
  "growth",
  "knowledge",
  "focus",
  "sustainable",
  "efficient",
  "strategy",
  "analyze",
  "evaluate",
  "progress",
  "commitment",
  "appropriate",
  "relevant",
  "challenge",
  "mastery",
  "review",
  "practice",
  "context",
  "output",
  "努力",
  "成长",
  "可能性",
  "挑战",
  "自信",
  "理解",
  "表现",
  "达成",
  "持续",
  "目标",
  "学ぶ",
  "進む",
  "集中",
  "分析",
  "習得",
  "練習",
  "復習",
  "挑戦",
  "語彙",
  "文脈",
];

const FLOW_WORDS = [
  { term: "achieve", pos: "v.", meaning: "達成する" },
  { term: "challenge", pos: "n.", meaning: "挑戦" },
  { term: "appropriate", pos: "adj.", meaning: "適切な" },
  { term: "efficient", pos: "adj.", meaning: "効率的な" },
  { term: "commitment", pos: "n.", meaning: "コミットメント" },
  { term: "focus", pos: "n. v.", meaning: "集中する" },
  { term: "sustainable", pos: "adj.", meaning: "持続可能な" },
  { term: "analyze", pos: "v.", meaning: "分析する" },
  { term: "relevant", pos: "adj.", meaning: "関連性のある" },
];

const QUESTION_SETS = [
  { title: "TOEIC Vocabulary Set", count: "20 questions", icon: BookOpenText },
  { title: "JLPT N2 Set", count: "20 questions", icon: Cards },
  { title: "English Grammar Set", count: "15 questions", icon: ListChecks },
  { title: "Reading Comprehension", count: "15 questions", icon: BookOpenText },
  { title: "Listening Practice", count: "10 questions", icon: DeviceMobile },
];

const DRILL_TYPES = [
  { title: "Vocabulary", count: "4 questions" },
  { title: "Fill in the Blank", count: "4 questions" },
  { title: "Reading", count: "3 questions" },
  { title: "Listening", count: "2 questions" },
  { title: "Sentence Reorder", count: "3 questions" },
];

const QUESTION_PREVIEWS = [
  {
    title: "Vocabulary",
    prompt: "Q. Which word means “達成する”?",
    options: ["A. assess", "B. achieve", "C. approach", "D. advertise"],
    selected: 1,
  },
  {
    title: "Fill in the Blank",
    prompt: "The team worked together to ___ the goal.",
    options: ["A. achieve", "B. achieved", "C. achieving", "D. achieves"],
    selected: 0,
  },
  {
    title: "Reading",
    prompt: "Q. What is the main idea of the passage?",
    options: ["A.", "B.", "C.", "D."],
    selected: 1,
  },
  {
    title: "Listening",
    prompt: "Q. What is the speaker mainly talking about?",
    options: ["A.", "B.", "C.", "D."],
    selected: 1,
  },
  {
    title: "Sentence Reorder",
    prompt: "正しい順に並べ替えなさい。",
    options: ["彼は", "毎日", "英語を", "勉強します"],
    selected: -1,
  },
];

const CHAT_SEED: ChatMessage[] = [
  {
    role: "assistant",
    text: "把截图词表拖到右侧导入区，确认词条后我会先生成完整题组，再逐题推进。",
  },
  {
    role: "user",
    text: "用这些词给我来几道四级语境题。",
  },
  {
    role: "assistant",
    text: "已创建演示题组。下面是第 1 题，答完后会自动进入下一题。",
  },
];

const SESSION_ROWS = [
  { date: "今天", title: "截图词表练习：achieve", progress: "8/12", active: true },
  { date: "昨天", title: "CJT4 阅读语境", progress: "18/18", active: false },
  { date: "06-30", title: "错题复盘", progress: "12/12", active: false },
];

const SKILL_ROWS = [
  {
    name: "Multi Search Engine",
    state: "已启用",
    body: "生成可审计搜索入口，内置联网检索仍由权限控制。",
  },
  {
    name: "skill1",
    state: "已启用",
    body: "示例拓展技能槽位，用于展示可开关的本地能力。",
  },
  {
    name: "skill2",
    state: "待启用",
    body: "预留给文档解析、外部题库或复习计划扩展。",
  },
];

const GALAXY_WORDS = Array.from({ length: 260 }, (_, index) => {
  const side = index % 2 === 0 ? "left" : "right";
  const local = Math.floor(index / 2);
  const arm = local % 5;
  const ring = Math.floor(local / 5);
  const angle = local * 0.34 + arm * 1.22;
  const radius = 12 + ring * 1.95 + arm * 1.9;
  const left = 50 + Math.cos(angle) * radius * 1.42;
  const top = 50 + Math.sin(angle) * radius * 0.58;
  const font = 9 + ((local + arm) % 6) * 1.65;
  return {
    side,
    word: GALAXY_TERMS[index % GALAXY_TERMS.length],
    style: cssVars({
      "--x": `${Math.max(-8, Math.min(108, left))}%`,
      "--y": `${Math.max(3, Math.min(97, top))}%`,
      "--r": `${-18 + ((local * 17) % 36)}deg`,
      "--s": `${font}px`,
      "--o": `${0.34 + ((local * 13) % 42) / 100}`,
      "--d": `${(local % 11) * -0.48}s`,
    }),
  };
});

const GALAXY_PARTICLES = Array.from({ length: 520 }, (_, index) => {
  const side = index % 2 === 0 ? "left" : "right";
  const local = Math.floor(index / 2);
  const angle = local * 0.21 + (local % 7) * 0.72;
  const radius = 8 + (local % 130) * 0.5;
  const left = 50 + Math.cos(angle) * radius * 1.72;
  const top = 50 + Math.sin(angle) * radius * 0.64;
  return {
    side,
    style: cssVars({
      "--x": `${Math.max(-10, Math.min(110, left))}%`,
      "--y": `${Math.max(2, Math.min(98, top))}%`,
      "--o": `${0.2 + ((local * 19) % 58) / 100}`,
      "--d": `${(local % 13) * -0.36}s`,
      "--size": `${1 + (local % 3) * 0.7}px`,
    }),
  };
});

function cssVars(vars: Record<string, string | number>): CSSProperties {
  return vars as CSSProperties;
}

function App() {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(() => {
    if (typeof window === "undefined") {
      return "dark";
    }
    const stored = window.localStorage.getItem("langdrill-demo-theme");
    return stored === "light" || stored === "dark" || stored === "system" ? stored : "dark";
  });
  const [activeTab, setActiveTab] = useState<WorkbenchTab>("import");
  const [messages, setMessages] = useState<ChatMessage[]>(CHAT_SEED);
  const [draft, setDraft] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [importParsed, setImportParsed] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const applyTheme = () => {
      const resolved = themeChoice === "system" ? (media.matches ? "dark" : "light") : themeChoice;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.themeChoice = themeChoice;
      window.localStorage.setItem("langdrill-demo-theme", themeChoice);
    };

    applyTheme();
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [themeChoice]);

  useGSAP(
    () => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      if (reduceMotion) {
        gsap.set(".reveal, .stream-word, .stream-question, .drill-output-card", {
          autoAlpha: 1,
          x: 0,
          y: 0,
          scale: 1,
        });
        return;
      }

      gsap.from(".hero-copy > *", {
        autoAlpha: 0,
        y: 18,
        filter: "blur(7px)",
        duration: 0.82,
        stagger: 0.08,
        ease: "power3.out",
      });

      gsap.from(".hero-product-frame", {
        autoAlpha: 0,
        y: 42,
        scale: 0.985,
        duration: 0.95,
        delay: 0.18,
        ease: "power3.out",
      });

      gsap.to(".galaxy-word", {
        x: (index) => (index % 2 === 0 ? 44 : -44),
        y: (index) => (index % 3 === 0 ? -28 : 24),
        rotation: (index) => (index % 2 === 0 ? 8 : -8),
        scrollTrigger: {
          trigger: ".hero",
          start: "top top",
          end: "bottom top",
          scrub: 0.7,
        },
      });

      gsap.to(".galaxy-particle", {
        y: (index) => (index % 2 === 0 ? -20 : 18),
        autoAlpha: (index) => 0.28 + (index % 5) * 0.1,
        scrollTrigger: {
          trigger: ".hero",
          start: "top top",
          end: "bottom top",
          scrub: 0.9,
        },
      });

      const stream = gsap.timeline({
        scrollTrigger: {
          trigger: ".stream-panel",
          start: "top 78%",
          end: "bottom 38%",
          scrub: 1,
        },
      });

      stream
        .fromTo(
          ".stream-word",
          { autoAlpha: 0, x: -84, y: 10 },
          { autoAlpha: 1, x: 0, y: 0, stagger: 0.04, ease: "power3.out" },
        )
        .to(".stream-word", {
          x: (index) => 220 + index * 8,
          y: (index) => -42 + index * 16,
          stagger: 0.035,
          ease: "power2.inOut",
        })
        .fromTo(
          ".stream-core",
          { scale: 0.86, boxShadow: "0 0 20px rgba(110, 124, 255, 0.28)" },
          { scale: 1.08, boxShadow: "0 0 58px rgba(110, 124, 255, 0.78)", ease: "power2.inOut" },
          "<0.2",
        )
        .fromTo(
          ".stream-question",
          { autoAlpha: 0, x: 120, scale: 0.96 },
          { autoAlpha: 1, x: 0, scale: 1, stagger: 0.07, ease: "power3.out" },
          "<0.16",
        )
        .fromTo(
          ".drill-output-card",
          { autoAlpha: 0, y: 26, scale: 0.96 },
          { autoAlpha: 1, y: 0, scale: 1, stagger: 0.07, ease: "power3.out" },
          ">-0.06",
        );

      ScrollTrigger.batch(".reveal", {
        start: "top 84%",
        once: true,
        onEnter: (elements) => {
          gsap.fromTo(
            elements,
            { autoAlpha: 0, y: 22, filter: "blur(6px)" },
            {
              autoAlpha: 1,
              y: 0,
              filter: "blur(0px)",
              duration: 0.75,
              stagger: 0.06,
              ease: "power3.out",
            },
          );
        },
      });

      window.requestAnimationFrame(() => ScrollTrigger.refresh());

      return () => {
        ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
      };
    },
    { scope: rootRef },
  );

  const cycleTheme = () => {
    setThemeChoice((current) => {
      if (current === "dark") {
        return "light";
      }
      if (current === "light") {
        return "system";
      }
      return "dark";
    });
  };

  const handleDemoSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed) {
      return;
    }

    setMessages((current) => [
      ...current,
      { role: "user", text: trimmed },
      {
        role: "assistant",
        text:
          "我是展示站的固定模拟回复。真实学习请启动 Lang Drill Agent，本页只演示三栏工作台、截图导入、题卡、分支和拓展 Skills 的交互。",
      },
    ]);
    setDraft("");
  };

  return (
    <div className="site" ref={rootRef}>
      <SiteHeader themeChoice={themeChoice} onThemeCycle={cycleTheme} />
      <main>
        <HeroSection />
        <FlowSection />
        <QuestionTypesSection />
        <AgentDemoSection
          activeTab={activeTab}
          answer={answer}
          draft={draft}
          importParsed={importParsed}
          leftOpen={leftOpen}
          messages={messages}
          rightOpen={rightOpen}
          onAnswer={setAnswer}
          onDraftChange={setDraft}
          onImportParsed={setImportParsed}
          onLeftOpen={setLeftOpen}
          onRightOpen={setRightOpen}
          onSubmit={handleDemoSubmit}
          onTabChange={setActiveTab}
        />
        <InstallSection />
      </main>
      <footer className="site-footer">
        <span>Lang Drill Agent</span>
        <span>Vocabulary in. Exam drills out.</span>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">
          GitHub <ArrowRight size={15} />
        </a>
      </footer>
    </div>
  );
}

function SiteHeader({ themeChoice, onThemeCycle }: { themeChoice: ThemeChoice; onThemeCycle: () => void }) {
  return (
    <header className="site-header">
      <a className="brand" href="#top" aria-label="Lang Drill Agent">
        <span className="brand-mark">
          <img className="brand-logo brand-logo-light" src="./assets/logo-light.png" alt="" />
          <img className="brand-logo brand-logo-dark" src="./assets/logo-dark.png" alt="" />
        </span>
        <span>Lang Drill Agent</span>
      </a>
      <nav className="site-nav" aria-label="Primary">
        <a href="#features">Features</a>
        <a href="#flow">How it works</a>
        <a href="#skills">Skills</a>
        <a href="#demo">Demo</a>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">
          GitHub
        </a>
      </nav>
      <div className="header-actions">
        <button className="theme-button" type="button" onClick={onThemeCycle} aria-label={`主题：${THEME_LABEL[themeChoice]}`}>
          {themeChoice === "dark" ? <Moon size={16} /> : themeChoice === "light" ? <Sun size={16} /> : <Monitor size={16} />}
        </button>
        <a className="download-button" href={DOWNLOAD_URL}>
          <DownloadSimple size={16} />
          Download
        </a>
      </div>
    </header>
  );
}

function HeroSection() {
  return (
    <section className="hero" id="top">
      <WordGalaxy />
      <div className="hero-copy">
        <h1>Lang Drill Agent</h1>
        <p className="hero-kicker">Words become drills</p>
        <p className="hero-body">
          Unify vocabulary learning and exam practice.
          <br />
          From any source → intelligent drills → real results.
        </p>
        <div className="hero-actions">
          <a className="hero-button secondary" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GithubLogo size={22} weight="fill" />
            GitHub
          </a>
          <a className="hero-button primary" href={DOWNLOAD_URL}>
            <DownloadSimple size={20} />
            Download
          </a>
        </div>
      </div>
      <div className="hero-product-frame reveal">
        <ProductPipelinePanel />
      </div>
    </section>
  );
}

function WordGalaxy() {
  return (
    <div className="galaxy" aria-hidden="true">
      <div className="galaxy-cluster galaxy-left">
        {GALAXY_PARTICLES.filter((particle) => particle.side === "left").map((particle, index) => (
          <span className="galaxy-particle" style={particle.style} key={`left-dot-${index}`} />
        ))}
        {GALAXY_WORDS.filter((word) => word.side === "left").map((word, index) => (
          <span className="galaxy-word" style={word.style} key={`left-word-${index}`}>
            {word.word}
          </span>
        ))}
      </div>
      <div className="galaxy-cluster galaxy-right">
        {GALAXY_PARTICLES.filter((particle) => particle.side === "right").map((particle, index) => (
          <span className="galaxy-particle" style={particle.style} key={`right-dot-${index}`} />
        ))}
        {GALAXY_WORDS.filter((word) => word.side === "right").map((word, index) => (
          <span className="galaxy-word" style={word.style} key={`right-word-${index}`}>
            {word.word}
          </span>
        ))}
      </div>
    </div>
  );
}

function ProductPipelinePanel() {
  return (
    <div className="pipeline-window">
      <div className="pipeline-topbar">
        <span className="mini-brand">
          <span className="brand-mark small">
            <img className="brand-logo brand-logo-light" src="./assets/logo-light.png" alt="" />
            <img className="brand-logo brand-logo-dark" src="./assets/logo-dark.png" alt="" />
          </span>
          Lang Drill Agent
        </span>
        <div className="window-controls">
          <button type="button" aria-label="Dark mode">
            <Moon size={14} />
          </button>
          <button type="button" aria-label="Settings">
            <GearSix size={14} />
          </button>
          <button type="button" aria-label="Menu">
            <span className="hamburger" />
          </button>
        </div>
      </div>
      <div className="pipeline-body">
        <IconRail />
        <div className="pipeline-grid">
          <VocabularyColumn />
          <GenerateColumn />
          <OutputColumn />
        </div>
      </div>
    </div>
  );
}

function IconRail() {
  const icons = [Sparkle, Cards, ChatsCircle, Brain, ListChecks, Database, GearSix];
  return (
    <aside className="icon-rail" aria-label="Demo rail">
      {icons.map((Icon, index) => (
        <button className={index === 1 ? "active" : ""} type="button" key={`rail-${index}`} aria-label={`Rail item ${index + 1}`}>
          <Icon size={17} />
        </button>
      ))}
    </aside>
  );
}

function VocabularyColumn() {
  return (
    <section className="pipeline-panel vocab-panel">
      <PanelTitle number="1" title="Vocabulary" subtitle="Import & collect words" />
      <div className="word-input">
        <span>Add word...</span>
        <button type="button">Add</button>
      </div>
      <div className="vocab-list">
        {FLOW_WORDS.map((word) => (
          <div className="vocab-row" key={word.term}>
            <strong>{word.term}</strong>
            <span>{word.pos}</span>
            <em>{word.meaning}</em>
          </div>
        ))}
      </div>
      <small>1,248 words</small>
    </section>
  );
}

function GenerateColumn() {
  return (
    <section className="pipeline-panel generate-panel">
      <PanelTitle number="2" title="Generate" subtitle="AI creates exam-style questions" />
      <div className="generation-map">
        <div className="map-word-list">
          {FLOW_WORDS.slice(0, 7).map((word) => (
            <span key={`map-${word.term}`}>{word.term}</span>
          ))}
        </div>
        <div className="star-core">
          <Sparkle size={34} weight="fill" />
        </div>
        <div className="type-stack">
          {DRILL_TYPES.map((type) => (
            <div className="type-card" key={type.title}>
              <strong>{type.title}</strong>
              <span>{type.count}</span>
              <ArrowRight size={14} />
            </div>
          ))}
        </div>
      </div>
      <div className="generating-bar">
        <span>Generating...</span>
        <i />
      </div>
    </section>
  );
}

function OutputColumn() {
  return (
    <section className="pipeline-panel output-panel">
      <PanelTitle number="3" title="Output" subtitle="Drills ready to practice" />
      <div className="set-list">
        {QUESTION_SETS.map((set) => {
          const Icon = set.icon;
          return (
            <article className="set-card" key={set.title}>
              <Icon size={21} />
              <div>
                <strong>{set.title}</strong>
                <span>{set.count}</span>
              </div>
              <ArrowRight size={15} />
            </article>
          );
        })}
      </div>
      <small>5 sets · 80 questions</small>
    </section>
  );
}

function PanelTitle({ number, title, subtitle }: { number: string; title: string; subtitle: string }) {
  return (
    <div className="panel-title">
      <span>{number}</span>
      <div>
        <strong>{title}</strong>
        <small>{subtitle}</small>
      </div>
    </div>
  );
}

function FlowSection() {
  return (
    <section className="flow-section" id="flow">
      <h2 className="reveal">From words to drills. Automatically.</h2>
      <div className="stream-panel reveal">
        <div className="step-label collect">
          <span>1</span>
          <strong>Collect</strong>
          <small>Import words from anywhere</small>
        </div>
        <div className="step-label transform">
          <span>2</span>
          <strong>Transform</strong>
          <small>AI turns words into exam-style questions</small>
        </div>
        <div className="step-label practice">
          <span>3</span>
          <strong>Practice</strong>
          <small>Drills ready to strengthen your skills</small>
        </div>
        <div className="stream-source">
          <BookOpenText size={42} />
        </div>
        <div className="stream-words">
          {["believe", "努力", "growth", "挑战", "knowledge"].map((word) => (
            <span className="stream-word" key={word}>
              {word}
            </span>
          ))}
        </div>
        <div className="stream-core">
          <Sparkle size={46} weight="fill" />
        </div>
        <div className="stream-questions">
          {["Vocabulary", "Blank", "Reading"].map((question) => (
            <div className="stream-question" key={question}>
              <Cards size={15} />
              <span>{question}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function QuestionTypesSection() {
  return (
    <section className="question-section" id="features">
      <div className="section-title reveal">
        <div>
          <h2>Practice. Review. Improve.</h2>
          <p>Multiple question types. Real exam experience.</p>
        </div>
        <a href="#demo">
          See all question types
          <ArrowRight size={17} />
        </a>
      </div>
      <div className="question-grid">
        {QUESTION_PREVIEWS.map((question) => (
          <QuestionPreviewCard question={question} key={question.title} />
        ))}
      </div>
    </section>
  );
}

function QuestionPreviewCard({
  question,
}: {
  question: {
    title: string;
    prompt: string;
    options: string[];
    selected: number;
  };
}) {
  return (
    <article className="question-preview reveal">
      <h3>{question.title}</h3>
      {question.title === "Listening" ? <Waveform /> : null}
      <p>{question.prompt}</p>
      <div className={question.title === "Sentence Reorder" ? "reorder-list" : "preview-options"}>
        {question.options.map((option, index) => (
          <span className={index === question.selected ? "selected" : ""} key={`${question.title}-${option}`}>
            {option}
          </span>
        ))}
      </div>
    </article>
  );
}

function Waveform() {
  return (
    <div className="waveform" aria-hidden="true">
      {Array.from({ length: 34 }, (_, index) => (
        <i style={cssVars({ "--h": `${8 + ((index * 7) % 26)}px` })} key={`wave-${index}`} />
      ))}
    </div>
  );
}

function AgentDemoSection({
  activeTab,
  answer,
  draft,
  importParsed,
  leftOpen,
  messages,
  rightOpen,
  onAnswer,
  onDraftChange,
  onImportParsed,
  onLeftOpen,
  onRightOpen,
  onSubmit,
  onTabChange,
}: {
  activeTab: WorkbenchTab;
  answer: string | null;
  draft: string;
  importParsed: boolean;
  leftOpen: boolean;
  messages: ChatMessage[];
  rightOpen: boolean;
  onAnswer: (answer: string) => void;
  onDraftChange: (draft: string) => void;
  onImportParsed: (parsed: boolean) => void;
  onLeftOpen: (open: boolean) => void;
  onRightOpen: (open: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onTabChange: (tab: WorkbenchTab) => void;
}) {
  return (
    <section className="agent-demo-section" id="demo">
      <div className="section-title reveal">
        <div>
          <h2>Explore the actual Agent workbench.</h2>
          <p>Same three-column product structure: status, chat and right workbench.</p>
        </div>
      </div>
      <div className={`agent-preview-shell reveal ${leftOpen ? "left-open" : "left-closed"} ${rightOpen ? "right-open" : "right-closed"}`}>
        <DemoLeftRail open={leftOpen} onToggle={() => onLeftOpen(!leftOpen)} />
        <DemoChatMain answer={answer} draft={draft} messages={messages} onAnswer={onAnswer} onDraftChange={onDraftChange} onSubmit={onSubmit} />
        <DemoRightRail
          activeTab={activeTab}
          importParsed={importParsed}
          open={rightOpen}
          onImportParsed={onImportParsed}
          onTabChange={onTabChange}
          onToggle={() => onRightOpen(!rightOpen)}
        />
      </div>
    </section>
  );
}

function DemoLeftRail({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <aside className="demo-left-rail">
      <div className="rail-top">
        <div className="brand-lockup">
          <img className="agent-logo agent-logo-light" src="./assets/logo-light.png" alt="" />
          <img className="agent-logo agent-logo-dark" src="./assets/logo-dark.png" alt="" />
          {open ? <strong>Lang Drill Agent</strong> : null}
        </div>
        <button className="rail-toggle" type="button" onClick={onToggle} aria-label={open ? "折叠左栏" : "展开左栏"}>
          <ArrowRight size={15} />
        </button>
      </div>
      {open ? (
        <>
          <div className="daily-panel">
            <div className="agent-panel-title">
              <Gauge size={18} />
              今日学习
            </div>
            <div className="metric-row">
              <div>
                <span>题目完成</span>
                <strong>8 / 12</strong>
              </div>
              <div>
                <span>正确率</span>
                <strong>84%</strong>
              </div>
            </div>
            <div className="thin-progress">
              <span style={cssVars({ width: "67%" })} />
            </div>
            <div className="word-progress-row">
              <Sparkle size={18} weight="fill" />
              <div>
                <strong>11 个截图词条</strong>
                <span>achieve, challenge, appropriate...</span>
              </div>
            </div>
            <button className="quick-start-button primary" type="button">
              快速开始
            </button>
          </div>
          <div className="session-list">
            {SESSION_ROWS.map((session) => (
              <button className={`session-link ${session.active ? "active" : ""}`} type="button" key={session.title}>
                <span>{session.date}</span>
                <strong>{session.title}</strong>
                <small>{session.progress}</small>
              </button>
            ))}
          </div>
          <button className="settings-button" type="button">
            <GearSix size={18} />
            设置
          </button>
        </>
      ) : (
        <div className="closed-icons">
          <Gauge size={19} />
          <BookOpenText size={19} />
          <GearSix size={19} />
        </div>
      )}
    </aside>
  );
}

function DemoChatMain({
  answer,
  draft,
  messages,
  onAnswer,
  onDraftChange,
  onSubmit,
}: {
  answer: string | null;
  draft: string;
  messages: ChatMessage[];
  onAnswer: (answer: string) => void;
  onDraftChange: (draft: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="demo-chat-main">
      <div className="long-panel compact">
        <div>
          <span className="eyebrow">Current Session</span>
          <h3>截图词表练习：achieve</h3>
          <p>从截图词条生成考试式题组，并把作答、讲解和掌握度写入同一个学习状态。</p>
        </div>
        <div className="score-stack">
          <StatCard label="题目" value="8/12" />
          <StatCard label="词汇" value="11" />
          <StatCard label="正确率" value="84%" />
          <StatCard label="上下文" value="18%" />
        </div>
      </div>
      <div className="message-stream">
        {messages.map((message, index) => (
          <div className={`agent-message ${message.role}`} key={`${message.role}-${index}-${message.text}`}>
            <div className="avatar">{message.role === "assistant" ? <Sparkle size={18} weight="fill" /> : "我"}</div>
            <div className="bubble">{message.text}</div>
          </div>
        ))}
        <ActiveQuestionCard answer={answer} onAnswer={onAnswer} />
      </div>
      <form className="chat-composer" onSubmit={onSubmit}>
        <button type="button" aria-label="上传文件">
          <UploadSimple size={18} />
        </button>
        <input
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="问问 Lang Drill Agent，或粘贴 3 个以上词条..."
        />
        <button type="submit" aria-label="发送">
          <PaperPlaneTilt size={18} weight="fill" />
        </button>
      </form>
    </section>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ActiveQuestionCard({ answer, onAnswer }: { answer: string | null; onAnswer: (answer: string) => void }) {
  const options = ["A. assess", "B. achieve", "C. approach", "D. advertise"];
  return (
    <article className="question-dock">
      <div className="question-head">
        <Cards size={18} />
        <strong>当前题 · CET-4 语境选择</strong>
        <span>1 / 12</span>
      </div>
      <p>The team worked together to ___ the goal before Friday.</p>
      <div className="options">
        {options.map((option) => {
          const selected = answer === option;
          const correct = option.includes("achieve");
          return (
            <button
              className={`${selected ? "selected" : ""} ${selected && correct ? "correct" : ""} ${
                selected && !correct ? "wrong" : ""
              }`}
              type="button"
              onClick={() => onAnswer(option)}
              key={option}
            >
              {selected && correct ? <CheckCircle size={17} /> : selected ? <XCircle size={17} /> : <span />}
              {option}
            </button>
          );
        })}
      </div>
      {answer ? <div className="answer-note">{answer.includes("achieve") ? "正确。achieve 表示达成目标。" : "正确答案是 B. achieve。"}</div> : null}
    </article>
  );
}

function DemoRightRail({
  activeTab,
  importParsed,
  open,
  onImportParsed,
  onTabChange,
  onToggle,
}: {
  activeTab: WorkbenchTab;
  importParsed: boolean;
  open: boolean;
  onImportParsed: (parsed: boolean) => void;
  onTabChange: (tab: WorkbenchTab) => void;
  onToggle: () => void;
}) {
  return (
    <aside className="demo-right-rail">
      <button className="right-toggle" type="button" onClick={onToggle} aria-label={open ? "折叠右栏" : "展开右栏"}>
        <ArrowRight size={15} />
      </button>
      {open ? (
        <>
          <div className="right-tabs" role="tablist" aria-label="右侧工作台">
            <RailTab active={activeTab === "branch"} icon={<GitBranch size={16} />} label="分支" onClick={() => onTabChange("branch")} />
            <RailTab active={activeTab === "import"} icon={<ImageSquare size={16} />} label="截图" onClick={() => onTabChange("import")} />
            <RailTab active={activeTab === "skills"} icon={<PlugsConnected size={16} />} label="Skills" onClick={() => onTabChange("skills")} />
            <RailTab active={activeTab === "settings"} icon={<GearSix size={16} />} label="设置" onClick={() => onTabChange("settings")} />
          </div>
          <div className="right-panel" id="skills">
            {activeTab === "branch" ? <BranchPanel /> : null}
            {activeTab === "import" ? <ImportPanel parsed={importParsed} onParsed={onImportParsed} /> : null}
            {activeTab === "skills" ? <SkillsPanel /> : null}
            {activeTab === "settings" ? <SettingsPanel /> : null}
          </div>
        </>
      ) : (
        <div className="closed-icons">
          <GitBranch size={19} />
          <ImageSquare size={19} />
          <PlugsConnected size={19} />
        </div>
      )}
    </aside>
  );
}

function RailTab({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button className={active ? "active" : ""} type="button" onClick={onClick}>
      {icon}
      <span>{label}</span>
    </button>
  );
}

function BranchPanel() {
  return (
    <div className="panel-stack">
      <div className="reference-card">
        <span>引用当前题</span>
        <p>The team worked together to ___ the goal before Friday.</p>
      </div>
      <textarea defaultValue="解释 achieve 和 accomplish 在四级语境题中的区别。" />
      <button className="inline-primary" type="button">
        <ChatsCircle size={18} />
        创建分支
      </button>
    </div>
  );
}

function ImportPanel({ parsed, onParsed }: { parsed: boolean; onParsed: (parsed: boolean) => void }) {
  return (
    <div className="panel-stack">
      <div className="drop-zone">
        <ImageSquare size={25} />
        <strong>拖入截图或文件</strong>
        <span>选择后先进入待解析队列</span>
      </div>
      <button className="inline-action" type="button" onClick={() => onParsed(true)}>
        <Play size={18} />
        解析文本
      </button>
      {parsed ? (
        <>
          <div className="parsed-text">achieve v. 達成する{"\n"}challenge n. 挑戦{"\n"}appropriate adj. 適切な</div>
          <div className="parsed-words">
            {FLOW_WORDS.slice(0, 5).map((word) => (
              <div key={word.term}>
                <strong>{word.term}</strong>
                <span>
                  {word.pos} {word.meaning}
                </span>
              </div>
            ))}
          </div>
          <button className="inline-primary" type="button">
            导入并开始练习
          </button>
        </>
      ) : (
        <p className="hint">点击解析文本后展示可编辑词条卡，导入动作会放在结果区底部。</p>
      )}
    </div>
  );
}

function SkillsPanel() {
  return (
    <div className="panel-stack">
      <div className="skill-highlight">
        <Database size={18} />
        <div>
          <strong>内置联网检索</strong>
          <span>始终可见，实际调用受权限控制。</span>
        </div>
      </div>
      {SKILL_ROWS.map((skill) => (
        <div className="skill-card" key={skill.name}>
          <div>
            <strong>{skill.name}</strong>
            <span>{skill.body}</span>
          </div>
          <small>{skill.state}</small>
        </div>
      ))}
    </div>
  );
}

function SettingsPanel() {
  return (
    <div className="panel-stack settings-preview">
      <label>
        Provider
        <select defaultValue="mimo">
          <option value="mimo">Xiaomi MiMo</option>
          <option value="openai">OpenAI GPT</option>
          <option value="deepseek">DeepSeek</option>
        </select>
      </label>
      <label>
        Model
        <select defaultValue="mimo-v2.5">
          <option value="mimo-v2.5">mimo-v2.5</option>
          <option value="deepseek-chat">deepseek-chat</option>
        </select>
      </label>
      <label>
        Base URL
        <input defaultValue="https://api.example.com/v1" />
      </label>
      <div className="permission-list">
        <span>截图导入</span>
        <span>学习数据库写入</span>
        <span>联网功能</span>
      </div>
    </div>
  );
}

function InstallSection() {
  return (
    <section className="install-section reveal">
      <div>
        <h2>Download the local workbench.</h2>
        <p>Windows desktop app runs the same Web experience with a local FastAPI backend and SQLite learning database.</p>
      </div>
      <div className="install-actions">
        <a className="hero-button primary" href={DOWNLOAD_URL}>
          <DownloadSimple size={19} />
          Download
        </a>
        <a className="hero-button secondary" href={GITHUB_URL} target="_blank" rel="noreferrer">
          <GithubLogo size={20} weight="fill" />
          GitHub
        </a>
      </div>
    </section>
  );
}

export default App;
