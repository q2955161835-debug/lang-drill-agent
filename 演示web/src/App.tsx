import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import {
  ArrowRight,
  BookOpenText,
  Brain,
  CaretDown,
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

type ThemeChoice = "system" | "light" | "dark";
type WorkbenchTab = "branch" | "import" | "skills" | "settings";
type Message = {
  role: "user" | "assistant";
  text: string;
};

const GITHUB_URL = "https://github.com/q2955161835-debug/lang-drill-agent";
const DOWNLOAD_URL =
  "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v0.1.0/Lang.Drill.Agent_0.1.0_x64-setup.exe";

const THEME_OPTIONS: Array<{ value: ThemeChoice; label: string }> = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

const GALAXY_WORDS = [
  ["achieve", "達成", "focus", "集中", "growth", "成長", "knowledge", "知識"],
  ["challenge", "挑戦", "analyze", "分析", "practice", "練習", "review", "復習"],
  ["efficient", "効率的", "context", "文脈", "mastery", "習得", "progress", "進歩"],
  ["appropriate", "適切", "sustainable", "持続可能", "evaluate", "評価", "question", "問題"],
].flat();

const FLOW_WORDS = [
  { term: "achieve", meaning: "v. 達成する" },
  { term: "challenge", meaning: "n. 挑戦" },
  { term: "appropriate", meaning: "adj. 適切な" },
  { term: "efficient", meaning: "adj. 効率的な" },
  { term: "sustainable", meaning: "adj. 持続可能な" },
];

const QUESTION_CARDS = [
  {
    type: "Fill in the Blank",
    stem: "The team worked together to ___ the goal.",
    answer: "achieve",
  },
  {
    type: "Reading",
    stem: "Which sentence best describes a sustainable plan?",
    answer: "It can continue over time.",
  },
  {
    type: "Synonym",
    stem: "Choose the closest meaning of appropriate.",
    answer: "suitable",
  },
];

const FEATURE_ROWS = [
  {
    title: "词表不再停在收藏夹",
    body: "截图、文本、文件里的词条会进入真实练习会话，生成考试式题组，而不是只停留在静态单词卡。",
    icon: BookOpenText,
  },
  {
    title: "刷题结果回流到复习",
    body: "每次作答都写入学习状态，错题、掌握度、讲解和后续题目可以围绕同一批词持续推进。",
    icon: ListChecks,
  },
  {
    title: "模型负责讲解，程序负责进度",
    body: "Agent 生成题目和讲解，数据库负责落库、判分和统计，避免学习记录散落在聊天上下文里。",
    icon: Brain,
  },
];

const SCREENSHOTS = [
  {
    src: "./assets/screenshots/dark-active-question.png",
    title: "当前题吸附卡",
    body: "中栏聊天和题卡在同一学习流里推进。",
  },
  {
    src: "./assets/screenshots/dark-screenshot-import-parsed.png",
    title: "截图词表导入",
    body: "OCR 后先编辑词条，再确认导入。",
  },
  {
    src: "./assets/screenshots/light-completed-day.png",
    title: "当日学习同步",
    body: "题目完成和词汇掌握保持同一口径。",
  },
  {
    src: "./assets/screenshots/light-settings-model.png",
    title: "模型配置",
    body: "供应商、模型、视觉能力和上下文容量集中管理。",
  },
  {
    src: "./assets/screenshots/dark-settings-skills.png",
    title: "拓展 Skills",
    body: "内置联网和可选拓展能力分开展示。",
  },
  {
    src: "./assets/screenshots/light-mobile-home.png",
    title: "移动视口",
    body: "主流程保留响应式浏览能力。",
  },
];

const DEMO_SESSIONS = [
  { date: "今天", label: "CET-4 截图词表", done: "8/12", words: "11 词" },
  { date: "昨天", label: "CJT4 阅读语境", done: "18/18", words: "67 词" },
  { date: "06-30", label: "错题复盘", done: "12/12", words: "55 词" },
];

const INITIAL_MESSAGES: Message[] = [
  {
    role: "assistant",
    text: "把截图词表拖进右侧导入区，确认词条后我会生成完整题组，并逐题讲解。",
  },
  {
    role: "user",
    text: "用这些词给我来几道四级语境题。",
  },
  {
    role: "assistant",
    text: "已创建演示题组。下面先看第 1 题，答完后会自动推进下一题。",
  },
];

const SKILL_PLACEHOLDERS = [
  {
    id: "skill1",
    name: "skill1",
    path: "~/LangDrill/skills/skill1",
    state: "已启用",
    body: "生成可审计搜索入口和学习材料索引。",
  },
  {
    id: "skill2",
    name: "skill2",
    path: "~/LangDrill/skills/skill2",
    state: "待启用",
    body: "为后续文档解析、外部题库或复习计划扩展预留。",
  },
];

const QUESTION_OPTIONS = ["A. assess", "B. achieve", "C. approach", "D. advertise"];

function isThemeChoice(value: string | null): value is ThemeChoice {
  return value === "system" || value === "light" || value === "dark";
}

function cssVars(vars: Record<string, string | number>): CSSProperties {
  return vars as CSSProperties;
}

function App() {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(() => {
    if (typeof window === "undefined") {
      return "system";
    }
    const stored = window.localStorage.getItem("langdrill-demo-theme");
    return isThemeChoice(stored) ? stored : "system";
  });
  const [activeTab, setActiveTab] = useState<WorkbenchTab>("skills");
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [draft, setDraft] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);

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

    return () => {
      media.removeEventListener("change", applyTheme);
    };
  }, [themeChoice]);

  useGSAP(
    () => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      if (reduceMotion) {
        gsap.set(".reveal, .flow-word, .generated-question, .question-flight", {
          autoAlpha: 1,
          x: 0,
          y: 0,
        });
        return;
      }

      gsap.from(".hero-copy > *", {
        autoAlpha: 0,
        y: 18,
        filter: "blur(6px)",
        stagger: 0.08,
        duration: 0.8,
        ease: "power3.out",
      });

      gsap.to(".galaxy-word", {
        x: (index) => (index % 2 === 0 ? 90 : -90),
        y: (index) => (index % 3 === 0 ? -60 : 48),
        rotation: (index) => (index % 2 === 0 ? 8 : -8),
        scrollTrigger: {
          trigger: ".hero",
          start: "top top",
          end: "bottom top",
          scrub: 1,
        },
      });

      const workflowTimeline = gsap.timeline({
        scrollTrigger: {
          trigger: ".workflow-demo",
          start: "top 75%",
          end: "bottom 40%",
          scrub: 1,
        },
      });

      workflowTimeline
        .fromTo(
          ".flow-word",
          { autoAlpha: 0, x: -110, y: 12, scale: 0.96 },
          { autoAlpha: 1, x: 0, y: 0, scale: 1, stagger: 0.05, ease: "power3.out" },
        )
        .to(".flow-word", {
          x: 245,
          y: (index) => -38 + index * 18,
          stagger: 0.04,
          ease: "power2.inOut",
        })
        .fromTo(
          ".generated-question",
          { autoAlpha: 0, x: 140, scale: 0.96 },
          { autoAlpha: 1, x: 0, scale: 1, stagger: 0.08, ease: "power3.out" },
          "<0.15",
        )
        .fromTo(
          ".question-flight",
          { autoAlpha: 0, y: -36, scale: 0.96 },
          { autoAlpha: 1, y: 0, scale: 1, stagger: 0.08, ease: "power3.out" },
          ">-0.1",
        );

      ScrollTrigger.batch(".reveal", {
        start: "top 82%",
        once: true,
        onEnter: (elements) => {
          gsap.fromTo(
            elements,
            { autoAlpha: 0, y: 22, filter: "blur(5px)" },
            {
              autoAlpha: 1,
              y: 0,
              filter: "blur(0px)",
              duration: 0.75,
              stagger: 0.08,
              ease: "power3.out",
            },
          );
        },
      });

      return () => {
        ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
      };
    },
    { scope: rootRef },
  );

  const cycleTheme = () => {
    setThemeChoice((current) => {
      if (current === "system") {
        return "light";
      }
      if (current === "light") {
        return "dark";
      }
      return "system";
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
          "我是 Lang Drill Agent 的展示版模拟回复。网页版使用正在开发中，暂不支持真实模型调用，敬请期待。你可以在当前网页中探索三栏工作台、题卡、截图导入、设置和拓展 Skills。",
      },
    ]);
    setDraft("");
  };

  return (
    <div className="app" ref={rootRef}>
      <SiteHeader themeChoice={themeChoice} onThemeCycle={cycleTheme} />
      <main>
        <HeroSection />
        <WorkflowSection />
        <FeatureSection />
        <DemoSection
          activeTab={activeTab}
          answer={answer}
          draft={draft}
          messages={messages}
          onAnswer={setAnswer}
          onDraftChange={setDraft}
          onSubmit={handleDemoSubmit}
          onTabChange={setActiveTab}
          themeChoice={themeChoice}
          onThemeCycle={cycleTheme}
        />
        <ScreenshotsSection />
        <InstallSection />
      </main>
      <SiteFooter />
    </div>
  );
}

function SiteHeader({
  themeChoice,
  onThemeCycle,
}: {
  themeChoice: ThemeChoice;
  onThemeCycle: () => void;
}) {
  const themeLabel = THEME_OPTIONS.find((option) => option.value === themeChoice)?.label ?? "跟随系统";

  return (
    <header className="site-header">
      <a className="brand-link" href="#top" aria-label="Lang Drill Agent 首页">
        <span className="brand-mark">
          <img className="brand-logo brand-logo-light" src="./assets/logo-light.png" alt="" />
          <img className="brand-logo brand-logo-dark" src="./assets/logo-dark.png" alt="" />
        </span>
        <span>Lang Drill Agent</span>
      </a>
      <nav className="site-nav" aria-label="主导航">
        <a href="#workflow">Workflow</a>
        <a href="#features">Features</a>
        <a href="#demo">Demo</a>
        <a href="#screens">Screens</a>
      </nav>
      <div className="header-actions">
        <button className="icon-button" type="button" onClick={onThemeCycle} aria-label={`主题：${themeLabel}`}>
          {themeChoice === "system" ? <Monitor size={18} /> : themeChoice === "light" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <a className="button ghost-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
          <GithubLogo size={18} />
          GitHub
        </a>
        <a className="button primary-button" href={DOWNLOAD_URL}>
          <DownloadSimple size={18} />
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
        <p className="hero-subtitle">Words become drills</p>
        <p className="hero-body">
          把背词截图、文本词表和文件材料变成考试式题组，让“记住单词”和“会做题”进入同一个闭环。
        </p>
        <div className="hero-actions">
          <a className="button primary-button" href={DOWNLOAD_URL}>
            <DownloadSimple size={20} />
            Download
          </a>
          <a className="button quiet-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GithubLogo size={20} />
            GitHub
          </a>
        </div>
      </div>
      <div className="hero-stage reveal">
        <MiniWorkbench variant="hero" />
      </div>
    </section>
  );
}

function WordGalaxy() {
  return (
    <div className="word-galaxy" aria-hidden="true">
      {GALAXY_WORDS.map((word, index) => {
        const side = index % 2 === 0 ? -1 : 1;
        const orbit = 1 + (index % 4);
        const top = 16 + ((index * 11) % 68);
        const left = side < 0 ? 4 + ((index * 7) % 31) : 62 + ((index * 5) % 29);
        const delay = (index % 9) * -0.7;

        return (
          <span
            className="galaxy-word"
            key={`${word}-${index}`}
            style={cssVars({
              "--top": `${top}%`,
              "--left": `${left}%`,
              "--orbit": orbit,
              "--delay": `${delay}s`,
            })}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
}

function MiniWorkbench({ variant }: { variant: "hero" | "workflow" }) {
  return (
    <div className={`mini-workbench mini-workbench-${variant}`}>
      <div className="mini-topbar">
        <span className="mini-brand">
          <Sparkle size={16} weight="fill" />
          Lang Drill Agent
        </span>
        <span className="mini-topbar-actions">
          <Moon size={15} />
          <GearSix size={15} />
        </span>
      </div>
      <div className="mini-grid">
        <aside className="mini-panel mini-left">
          <div className="mini-panel-title">
            <span>1</span>
            Vocabulary
          </div>
          <div className="mini-input-row">
            <span>Add word...</span>
            <button type="button">Add</button>
          </div>
          <div className="word-stack">
            {FLOW_WORDS.map((word) => (
              <div className="flow-word" key={word.term}>
                <strong>{word.term}</strong>
                <span>{word.meaning}</span>
              </div>
            ))}
          </div>
        </aside>
        <section className="mini-panel mini-center">
          <div className="mini-panel-title">
            <span>2</span>
            Generate
          </div>
          <div className="generator-core">
            <Sparkle size={30} weight="fill" />
          </div>
          <div className="generator-lines">
            <span />
            <span />
            <span />
          </div>
          <p>AI creates exam-style questions</p>
        </section>
        <aside className="mini-panel mini-right">
          <div className="mini-panel-title">
            <span>3</span>
            Output
          </div>
          {QUESTION_CARDS.map((question) => (
            <div className="generated-question" key={question.type}>
              <Cards size={16} />
              <div>
                <strong>{question.type}</strong>
                <span>{question.answer}</span>
              </div>
              <ArrowRight size={15} />
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}

function WorkflowSection() {
  return (
    <section className="workflow-section" id="workflow">
      <div className="section-heading reveal">
        <h2>从词条到题组，不再断层</h2>
        <p>单词汇入左侧学习状态，经中栏组卷，再从右侧输出为可作答题卡。</p>
      </div>
      <div className="workflow-demo">
        <MiniWorkbench variant="workflow" />
        <div className="practice-strip">
          {QUESTION_CARDS.map((question, index) => (
            <article className="question-flight" key={question.type}>
              <span className="question-index">0{index + 1}</span>
              <p>{question.type}</p>
              <strong>{question.stem}</strong>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureSection() {
  return (
    <section className="feature-section" id="features">
      <div className="section-heading reveal">
        <h2>核心痛点很简单：背词和刷题分离</h2>
        <p>Lang Drill Agent 把导入、出题、作答、讲解、复盘和统计放进同一个本地学习工作台。</p>
      </div>
      <div className="feature-rows">
        {FEATURE_ROWS.map((feature, index) => {
          const Icon = feature.icon;
          return (
            <article className="feature-row reveal" key={feature.title}>
              <span className="feature-number">0{index + 1}</span>
              <Icon size={28} />
              <div>
                <h3>{feature.title}</h3>
                <p>{feature.body}</p>
              </div>
            </article>
          );
        })}
      </div>
      <div className="concept-band reveal">
        <img src="./assets/concept-langdrill-site.png" alt="Lang Drill Agent 视觉概念图" />
        <div>
          <h3>动态银河是叙事，不是装饰</h3>
          <p>
            英语和日语词条像粒子一样聚集到工作台，随后被转换为题目输出，直接表达产品的学习闭环。
          </p>
        </div>
      </div>
    </section>
  );
}

function DemoSection({
  activeTab,
  answer,
  draft,
  messages,
  onAnswer,
  onDraftChange,
  onSubmit,
  onTabChange,
  themeChoice,
  onThemeCycle,
}: {
  activeTab: WorkbenchTab;
  answer: string | null;
  draft: string;
  messages: Message[];
  onAnswer: (answer: string) => void;
  onDraftChange: (draft: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onTabChange: (tab: WorkbenchTab) => void;
  themeChoice: ThemeChoice;
  onThemeCycle: () => void;
}) {
  return (
    <section className="demo-section" id="demo">
      <div className="section-heading reveal">
        <h2>完整三栏工作台展示</h2>
        <p>这是静态网站里的前端模拟器，保留主应用布局和控件，不连接真实后端。</p>
      </div>
      <div className="demo-shell reveal">
        <DemoSidebar />
        <DemoMain
          answer={answer}
          draft={draft}
          messages={messages}
          onAnswer={onAnswer}
          onDraftChange={onDraftChange}
          onSubmit={onSubmit}
        />
        <DemoWorkbench activeTab={activeTab} onTabChange={onTabChange} />
      </div>
      <div className="demo-toolbar reveal">
        <label>
          Provider
          <select defaultValue="mimo">
            <option value="mimo">Xiaomi MiMo</option>
            <option value="openai">OpenAI GPT</option>
            <option value="deepseek">DeepSeek</option>
            <option value="claude">Claude</option>
          </select>
        </label>
        <label>
          Model
          <select defaultValue="mimo-v2.5">
            <option value="mimo-v2.5">mimo-v2.5</option>
            <option value="gpt-4.1">gpt-4.1</option>
            <option value="deepseek-chat">deepseek-chat</option>
          </select>
        </label>
        <label>
          Exam
          <select defaultValue="cet4">
            <option value="cet4">英语四级 CET-4</option>
            <option value="cet6">英语六级 CET-6</option>
            <option value="cjt4">日语四级 CJT4</option>
          </select>
        </label>
        <label>
          Syllabus
          <select defaultValue="cet-2016">
            <option value="cet-2016">全国大学英语四、六级考试大纲 2016</option>
            <option value="cjt-2024">大学日语四级考试大纲 2024</option>
            <option value="custom">自定义考试</option>
          </select>
        </label>
        <button className="button quiet-button" type="button" onClick={onThemeCycle}>
          {themeChoice === "system" ? <Monitor size={18} /> : themeChoice === "light" ? <Sun size={18} /> : <Moon size={18} />}
          主题
        </button>
      </div>
    </section>
  );
}

function DemoSidebar() {
  return (
    <aside className="demo-sidebar">
      <div className="workspace-title">
        <Gauge size={18} />
        <span>学习总览</span>
      </div>
      <div className="metric-grid">
        <Metric label="题目" value="32/42" />
        <Metric label="词汇" value="133" />
        <Metric label="正确率" value="84%" />
        <Metric label="Token" value="18.4k" />
      </div>
      <div className="session-list">
        {DEMO_SESSIONS.map((session) => (
          <button className="session-item" type="button" key={session.label}>
            <span>{session.date}</span>
            <strong>{session.label}</strong>
            <small>
              {session.done} · {session.words}
            </small>
          </button>
        ))}
      </div>
      <button className="button primary-button sidebar-cta" type="button">
        <UploadSimple size={18} />
        当日导入
      </button>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DemoMain({
  answer,
  draft,
  messages,
  onAnswer,
  onDraftChange,
  onSubmit,
}: {
  answer: string | null;
  draft: string;
  messages: Message[];
  onAnswer: (answer: string) => void;
  onDraftChange: (draft: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="demo-main">
      <div className="chat-header">
        <div>
          <span>主聊天</span>
          <strong>截图词表练习：achieve</strong>
        </div>
        <div className="context-ring" aria-label="上下文容量 18%">
          18%
        </div>
      </div>
      <div className="message-feed">
        {messages.map((message, index) => (
          <div className={`message message-${message.role}`} key={`${message.role}-${index}-${message.text}`}>
            {message.text}
          </div>
        ))}
        <QuestionCard answer={answer} onAnswer={onAnswer} />
      </div>
      <form className="chat-input" onSubmit={onSubmit}>
        <button className="icon-button" type="button" aria-label="上传文件">
          <UploadSimple size={18} />
        </button>
        <input
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="问问 Lang Drill Agent，或粘贴 3 个以上词条..."
        />
        <button className="icon-button send-button" type="submit" aria-label="发送消息">
          <PaperPlaneTilt size={18} weight="fill" />
        </button>
      </form>
    </section>
  );
}

function QuestionCard({ answer, onAnswer }: { answer: string | null; onAnswer: (answer: string) => void }) {
  return (
    <article className="active-question-card">
      <div className="question-card-header">
        <span>当前题 · CET-4 语境选择</span>
        <strong>1 / 12</strong>
      </div>
      <p>The team worked together to ___ the goal before Friday.</p>
      <div className="option-grid">
        {QUESTION_OPTIONS.map((option) => {
          const selected = answer === option;
          const correct = option.includes("achieve");
          return (
            <button
              className={`option-button ${selected ? "is-selected" : ""} ${selected && correct ? "is-correct" : ""} ${
                selected && !correct ? "is-wrong" : ""
              }`}
              type="button"
              key={option}
              onClick={() => onAnswer(option)}
            >
              {selected && correct ? <CheckCircle size={17} /> : selected ? <XCircle size={17} /> : <span />}
              {option}
            </button>
          );
        })}
      </div>
      {answer ? (
        <div className="answer-feedback">
          {answer.includes("achieve") ? "正确。achieve 表示“达成目标”。" : "这一题的正确答案是 B. achieve。"}
        </div>
      ) : null}
    </article>
  );
}

function DemoWorkbench({ activeTab, onTabChange }: { activeTab: WorkbenchTab; onTabChange: (tab: WorkbenchTab) => void }) {
  return (
    <aside className="demo-workbench">
      <div className="workbench-tabs" role="tablist" aria-label="右侧工作台">
        <WorkbenchTabButton active={activeTab === "branch"} icon={<GitBranch size={17} />} label="分支" onClick={() => onTabChange("branch")} />
        <WorkbenchTabButton active={activeTab === "import"} icon={<ImageSquare size={17} />} label="截图" onClick={() => onTabChange("import")} />
        <WorkbenchTabButton active={activeTab === "skills"} icon={<PlugsConnected size={17} />} label="Skills" onClick={() => onTabChange("skills")} />
        <WorkbenchTabButton active={activeTab === "settings"} icon={<GearSix size={17} />} label="设置" onClick={() => onTabChange("settings")} />
      </div>
      <div className="workbench-panel">
        {activeTab === "branch" ? <BranchPanel /> : null}
        {activeTab === "import" ? <ImportPanel /> : null}
        {activeTab === "skills" ? <SkillsPanel /> : null}
        {activeTab === "settings" ? <SettingsPanel /> : null}
      </div>
    </aside>
  );
}

function WorkbenchTabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button className={`tab-button ${active ? "is-active" : ""}`} type="button" onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function BranchPanel() {
  return (
    <div className="panel-stack">
      <div className="reference-card">
        <span>引用当前题</span>
        <p>The team worked together to ___ the goal.</p>
      </div>
      <textarea defaultValue="解释 achieve 和 accomplish 在四级语境题中的区别。" />
      <button className="button primary-button" type="button">
        <ChatsCircle size={18} />
        创建分支
      </button>
    </div>
  );
}

function ImportPanel() {
  return (
    <div className="panel-stack">
      <div className="drop-zone">
        <ImageSquare size={24} />
        <strong>拖入截图或文件</strong>
        <span>选择文件后先进入待解析队列</span>
      </div>
      <button className="button quiet-button" type="button">
        <Play size={18} />
        解析文本
      </button>
      <div className="parsed-words">
        {FLOW_WORDS.map((word) => (
          <div key={word.term}>
            <strong>{word.term}</strong>
            <span>{word.meaning}</span>
          </div>
        ))}
      </div>
      <button className="button primary-button" type="button">
        导入并开始练习
      </button>
    </div>
  );
}

function SkillsPanel() {
  return (
    <div className="panel-stack">
      <div className="tool-note">
        <Database size={18} />
        内置联网检索始终可见，实际调用仍受权限控制。
      </div>
      {SKILL_PLACEHOLDERS.map((skill) => (
        <div className="skill-card" key={skill.id}>
          <div>
            <strong>{skill.name}</strong>
            <span>{skill.path}</span>
          </div>
          <small>{skill.state}</small>
          <p>{skill.body}</p>
        </div>
      ))}
    </div>
  );
}

function SettingsPanel() {
  return (
    <div className="panel-stack settings-stack">
      <label>
        API Format
        <select defaultValue="openai">
          <option value="openai">OpenAI-compatible</option>
          <option value="anthropic">Anthropic Messages</option>
        </select>
      </label>
      <label>
        Base URL
        <input defaultValue="https://api.example.com/v1" />
      </label>
      <label>
        数据目录
        <input defaultValue="C:\\Users\\You\\AppData\\Roaming\\Lang Drill Agent\\data" />
      </label>
      <div className="permission-list">
        <span>截图导入</span>
        <span>学习数据库写入</span>
        <span>联网功能</span>
      </div>
    </div>
  );
}

function ScreenshotsSection() {
  return (
    <section className="screens-section" id="screens">
      <div className="section-heading reveal">
        <h2>真实前端截图素材</h2>
        <p>展示站使用脱敏截图辅助说明，所有交互演示仍在本页静态模拟器里完成。</p>
      </div>
      <div className="screenshot-grid">
        {SCREENSHOTS.map((shot) => (
          <figure className="screenshot-card reveal" key={shot.src}>
            <img src={shot.src} alt={shot.title} loading="lazy" />
            <figcaption>
              <strong>{shot.title}</strong>
              <span>{shot.body}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

function InstallSection() {
  return (
    <section className="install-section reveal">
      <div>
        <h2>本地应用优先，网页体验正在演进</h2>
        <p>
          当前推荐安装 Windows 桌面版体验完整能力。展示站里的模拟器可探索布局、题卡和设置流程，但不会调用真实模型或读取本地数据。
        </p>
      </div>
      <div className="install-actions">
        <a className="button primary-button" href={DOWNLOAD_URL}>
          <DownloadSimple size={20} />
          Windows 安装包
        </a>
        <a className="button quiet-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
          <GithubLogo size={20} />
          GitHub 仓库
        </a>
      </div>
    </section>
  );
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <span>Lang Drill Agent</span>
      <span>Vocabulary in. Exam drills out.</span>
      <a href={GITHUB_URL} target="_blank" rel="noreferrer">
        GitHub
        <ArrowRight size={15} />
      </a>
    </footer>
  );
}

export default App;
