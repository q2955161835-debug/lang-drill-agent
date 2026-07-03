import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Books,
  Brain,
  Cards,
  ChatsCircle,
  CheckCircle,
  ClipboardText,
  Code,
  Database,
  DownloadSimple,
  GearSix,
  GithubLogo,
  GitBranch,
  Globe,
  ImageSquare,
  ListChecks,
  Monitor,
  Moon,
  PaperPlaneTilt,
  Play,
  PlugsConnected,
  Sparkle,
  Sun,
  Target,
  UploadSimple,
} from "@phosphor-icons/react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP, ScrollTrigger);

// ---------- 类型与常量 ----------

type ThemeChoice = "system" | "light" | "dark";

const GITHUB_URL = "https://github.com/q2955161835-debug/lang-drill-agent";
const DOWNLOAD_URL =
  "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v0.1.0/Lang.Drill.Agent_0.1.0_x64-setup.exe";

const THEME_OPTIONS: Array<{ value: ThemeChoice; label: string }> = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

// 单词银河：英语 + 日语混合，粒子构成银河
const GALAXY_WORDS: Array<{ text: string; lang: "en" | "jp"; weight?: number }> = [
  { text: "achieve", lang: "en" }, { text: "達成", lang: "jp" },
  { text: "focus", lang: "en" }, { text: "集中", lang: "jp" },
  { text: "growth", lang: "en" }, { text: "成長", lang: "jp" },
  { text: "knowledge", lang: "en" }, { text: "知識", lang: "jp" },
  { text: "challenge", lang: "en" }, { text: "挑戦", lang: "jp" },
  { text: "analyze", lang: "en" }, { text: "分析", lang: "jp" },
  { text: "practice", lang: "en" }, { text: "練習", lang: "jp" },
  { text: "review", lang: "en" }, { text: "復習", lang: "jp" },
  { text: "efficient", lang: "en" }, { text: "効率的", lang: "jp" },
  { text: "context", lang: "en" }, { text: "文脈", lang: "jp" },
  { text: "mastery", lang: "en" }, { text: "習得", lang: "jp" },
  { text: "progress", lang: "en" }, { text: "進歩", lang: "jp" },
  { text: "appropriate", lang: "en" }, { text: "適切", lang: "jp" },
  { text: "sustainable", lang: "en" }, { text: "持続可能", lang: "jp" },
  { text: "evaluate", lang: "en" }, { text: "評価", lang: "jp" },
  { text: "question", lang: "en" }, { text: "問題", lang: "jp" },
  { text: "vocabulary", lang: "en", weight: 700 }, { text: "語彙", lang: "jp" },
  { text: "exam", lang: "en" }, { text: "試験", lang: "jp" },
  { text: "drill", lang: "en", weight: 700 }, { text: "訓練", lang: "jp" },
  { text: "agent", lang: "en", weight: 700 }, { text: "代理人", lang: "jp" },
  { text: "memory", lang: "en" }, { text: "記憶", lang: "jp" },
  { text: "fluency", lang: "en" }, { text: "流暢", lang: "jp" },
  { text: "insight", lang: "en" }, { text: "洞察", lang: "jp" },
  { text: "satellite", lang: "en" }, { text: "衛星", lang: "jp" },
  { text: "nebula", lang: "en" }, { text: "星雲", lang: "jp" },
  { text: "orbit", lang: "en" }, { text: "軌道", lang: "jp" },
  { text: "particle", lang: "en" }, { text: "粒子", lang: "jp" },
  { text: "horizon", lang: "en" }, { text: "地平線", lang: "jp" },
  { text: "iterate", lang: "en" }, { text: "反復", lang: "jp" },
  { text: "comprehend", lang: "en" }, { text: "理解", lang: "jp" },
  { text: "syntax", lang: "en" }, { text: "構文", lang: "jp" },
];

// 工作流演示：单词 → 题目
const FLOW_WORDS = [
  { term: "achieve", meaning: "v. 達成する", en: "achieve" },
  { term: "challenge", meaning: "n. 挑戦", en: "challenge" },
  { term: "appropriate", meaning: "adj. 適切な", en: "appropriate" },
  { term: "efficient", meaning: "adj. 効率的な", en: "efficient" },
  { term: "sustainable", meaning: "adj. 持続可能な", en: "sustainable" },
];

const QUESTION_CARDS = [
  {
    type: "Fill in the Blank",
    stem: "The team worked together to ___ the goal before Friday.",
    options: ["A. assess", "B. achieve", "C. approach", "D. advertise"],
    answer: "B",
  },
  {
    type: "Reading",
    stem: "Which sentence best describes a sustainable plan?",
    options: ["A. One that costs less.", "B. One that finishes fast.", "C. One that can continue over time.", "D. One that looks modern."],
    answer: "C",
  },
  {
    type: "Synonym",
    stem: "Choose the closest meaning of appropriate.",
    options: ["A. suitable", "B. cheap", "C. heavy", "D. loud"],
    answer: "A",
  },
];

const FEATURE_ROWS = [
  {
    title: "词表不再停在收藏夹",
    body: "截图、文本、文件里的词条会进入真实练习会话，生成考试式题组，而不是只停留在静态单词卡。",
    icon: Books,
    tag: "Import",
  },
  {
    title: "刷题结果回流到复习",
    body: "每次作答都写入学习状态，错题、掌握度、讲解和后续题目围绕同一批词持续推进。",
    icon: ListChecks,
    tag: "Loop",
  },
  {
    title: "模型负责讲解，程序负责进度",
    body: "Agent 生成题目和讲解，数据库负责落库、判分和统计，避免学习记录散落在聊天上下文里。",
    icon: Brain,
    tag: "Agent",
  },
  {
    title: "三栏工作台一体",
    body: "左侧学习状态、中间聊天与题目、右侧分支/截图导入/手机映像，边界可拖拽，状态不丢失。",
    icon: Cards,
    tag: "Layout",
  },
  {
    title: "多模型与考纲并行",
    body: "OpenAI、Claude、DeepSeek、MiMo 与自定义供应商共存；英语、日语、法语多考试与考纲同时支持。",
    icon: PlugsConnected,
    tag: "Models",
  },
  {
    title: "本地优先，网页可演示",
    body: "Windows 桌面版承载完整能力；展示站 1:1 还原前端，可探索布局、题卡和设置流程。",
    icon: DownloadSimple,
    tag: "Local",
  },
];

const SCREENSHOTS = [
  { src: "assets/screenshots/dark-01-cet4-home-long-panel.png", title: "长期学习总面板", body: "题目完成、词汇掌握、正确率和考试倒计时同一口径。" },
  { src: "assets/screenshots/dark-07-cet4-active-question.png", title: "当前题吸附卡", body: "中栏聊天与题卡同一学习流推进，自动下一题。" },
  { src: "assets/screenshots/dark-14-cet4-screenshot-import-parsed.png", title: "截图词表导入", body: "OCR 后先编辑词条，确认后再导入并生成题组。" },
  { src: "assets/screenshots/dark-16-cet4-screenshot-import-auto-drill.png", title: "导入自动开练", body: "确认词条后自动创建独立练习会话。" },
  { src: "assets/screenshots/dark-12-branch-selected-text-reference-card.png", title: "分支引用", body: "划词进入右侧分支，主会话不被污染。" },
  { src: "assets/screenshots/dark-06-cet4-daily-summary.png", title: "当日总结", body: "模型结合数据库明细生成复盘、错题归因与建议。" },
  { src: "assets/screenshots/dark-18-settings-model-mimo.png", title: "模型配置", body: "供应商、模型、视觉能力与上下文容量集中管理。" },
  { src: "assets/screenshots/dark-26-settings-skills.png", title: "拓展 Skills", body: "内置联网始终可用，拓展 Skill 单项开关控制。" },
  { src: "assets/screenshots/dark-30-cjt4-active-question.png", title: "日语四级题卡", body: "CJT4 同样支持语境题、阅读和翻译题型。" },
];

const PAIN_POINTS = [
  {
    label: "BEFORE",
    title: "背词和刷题分离",
    points: [
      "词表停在收藏夹，不会变成题目",
      "刷题时遇到生词要手动抄到本子",
      "错题和讲解散落在聊天记录里",
      "学习进度无法追踪和回顾",
    ],
    tone: "dim" as const,
  },
  {
    label: "AFTER",
    title: "导入即练习，练习即闭环",
    points: [
      "截图 / 文本 / 文件词条直接进入练习会话",
      "Agent 一次生成完整考试式题组",
      "作答、错题、掌握度写入本地数据库",
      "讲解、复盘、错题回流同一批词",
    ],
    tone: "glow" as const,
  },
];

const STATS = [
  { value: "9", label: "内置考试与考纲" },
  { value: "4+", label: "真实模型供应商" },
  { value: "1:1", label: "前端还原度" },
  { value: "0", label: "需要密钥即可演示" },
];

// ---------- 工具函数 ----------

function isThemeChoice(value: string | null): value is ThemeChoice {
  return value === "system" || value === "light" || value === "dark";
}

function cssVars(vars: Record<string, string | number>): CSSProperties {
  return vars as CSSProperties;
}

// ---------- 主应用 ----------

function App() {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(() => {
    if (typeof window === "undefined") return "system";
    const stored = window.localStorage.getItem("langdrill-site2-theme");
    return isThemeChoice(stored) ? stored : "system";
  });

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const applyTheme = () => {
      const resolved = themeChoice === "system" ? (media.matches ? "dark" : "light") : themeChoice;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.themeChoice = themeChoice;
      window.localStorage.setItem("langdrill-site2-theme", themeChoice);
    };
    applyTheme();
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [themeChoice]);

  const cycleTheme = useCallback(() => {
    setThemeChoice((current) => (current === "system" ? "light" : current === "light" ? "dark" : "system"));
  }, []);

  useGSAP(
    () => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion) {
        gsap.set(".reveal, .flow-word, .generated-question, .question-flight", { autoAlpha: 1, x: 0, y: 0, filter: "none" });
        return;
      }

      // Hero 标题入场
      gsap.from(".hero-content > *", {
        autoAlpha: 0,
        y: 28,
        filter: "blur(8px)",
        stagger: 0.08,
        duration: 0.9,
        ease: "power3.out",
        delay: 0.15,
      });

      // 单词银河滚动响应：随滚动整体飘动
      gsap.to(".word-galaxy", {
        y: 120,
        scale: 0.92,
        opacity: 0.6,
        ease: "none",
        scrollTrigger: {
          trigger: ".hero",
          start: "top top",
          end: "bottom top",
          scrub: 1,
        },
      });

      // 工作流：单词飞入左侧 → 飞到右侧 → 题目生成 → 题目飞到下方
      const workflowTimeline = gsap.timeline({
        scrollTrigger: {
          trigger: ".workflow-stage",
          start: "top 78%",
          end: "bottom 55%",
          scrub: 1,
        },
      });

      workflowTimeline
        .fromTo(
          ".flow-word",
          { autoAlpha: 0, x: -180, y: 12, scale: 0.92 },
          { autoAlpha: 1, x: 0, y: 0, scale: 1, stagger: 0.06, ease: "power3.out" }
        )
        .to(".flow-word", {
          x: 280,
          y: (_index: number) => -36 + _index * 16,
          stagger: 0.04,
          ease: "power2.inOut",
        })
        .fromTo(
          ".generated-question",
          { autoAlpha: 0, x: 160, scale: 0.94 },
          { autoAlpha: 1, x: 0, scale: 1, stagger: 0.08, ease: "power3.out" },
          "<0.1"
        )
        .fromTo(
          ".question-flight",
          { autoAlpha: 0, y: -50, scale: 0.92, filter: "blur(8px)" },
          { autoAlpha: 1, y: 0, scale: 1, filter: "blur(0px)", stagger: 0.12, ease: "power3.out" },
          ">-0.1"
        );

      // 通用 reveal 入场
      ScrollTrigger.batch(".reveal", {
        start: "top 85%",
        once: true,
        onEnter: (elements) => {
          gsap.to(elements, {
            autoAlpha: 1,
            y: 0,
            filter: "blur(0px)",
            duration: 0.8,
            stagger: 0.08,
            ease: "power3.out",
            overwrite: true,
          });
          elements.forEach((el) => el.classList.add("is-visible"));
        },
      });

      gsap.set(".reveal", { autoAlpha: 0, y: 24, filter: "blur(8px)" });

      return () => {
        ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
      };
    },
    { scope: rootRef }
  );

  return (
    <div className="site" ref={rootRef}>
      <SiteHeader themeChoice={themeChoice} onThemeCycle={cycleTheme} />
      <main>
        <HeroSection />
        <StatsStrip />
        <WorkflowSection />
        <PainPointSection />
        <FeatureSection />
        <ShowcaseSection />
        <DemoCtaSection />
        <InstallSection />
      </main>
      <SiteFooter />
      <CursorGlow />
    </div>
  );
}

// ---------- 顶部导航 ----------

function SiteHeader({ themeChoice, onThemeCycle }: { themeChoice: ThemeChoice; onThemeCycle: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const themeLabel = THEME_OPTIONS.find((option) => option.value === themeChoice)?.label ?? "跟随系统";

  return (
    <header className={`site-header ${scrolled ? "is-scrolled" : ""}`}>
      <div className="header-inner">
        <a className="brand-link" href="#top" aria-label="Lang Drill Agent 首页">
          <span className="brand-mark">
            <img className="brand-logo brand-logo-light" src="assets/logo-light.png" alt="" />
            <img className="brand-logo brand-logo-dark" src="assets/logo-dark.png" alt="" />
          </span>
          <span className="brand-text">
            Lang Drill Agent
            <small>Words become drills</small>
          </span>
        </a>
        <nav className="site-nav" aria-label="主导航">
          <a href="#workflow">Workflow</a>
          <a href="#painpoint">Pain Point</a>
          <a href="#features">Features</a>
          <a href="#showcase">Showcase</a>
          <a href="#demo">Demo</a>
        </nav>
        <div className="header-actions">
          <button className="icon-button" type="button" onClick={onThemeCycle} aria-label={`主题：${themeLabel}`}>
            {themeChoice === "system" ? <Monitor size={18} /> : themeChoice === "light" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <a className="button ghost-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GithubLogo size={18} />
            <span>GitHub</span>
          </a>
          <a className="button primary-button" href={DOWNLOAD_URL}>
            <DownloadSimple size={18} />
            <span>Download</span>
          </a>
        </div>
      </div>
    </header>
  );
}

// ---------- Hero 区：动态单词银河 ----------

function HeroSection() {
  return (
    <section className="hero" id="top">
      <div
        className="hero-bg-image"
        aria-hidden="true"
        style={{ backgroundImage: `url(${import.meta.env.BASE_URL}assets/hero-bg-texture.jpg)` }}
      />
      <WordGalaxy />
      <div className="hero-aurora" aria-hidden="true" />
      <div className="hero-grid-overlay" aria-hidden="true" />
      <div className="hero-content">
        <span className="kicker">
          <Sparkle size={14} weight="fill" />
          Language learning agent · 語学学習エージェント
        </span>
        <h1 className="hero-title">
          <span className="hero-title-line">背词与刷题</span>
          <span className="hero-title-line gradient-text">不再分离</span>
        </h1>
        <p className="hero-subtitle">
          把截图词表、文本词条和文件材料变成考试式题组，让“记住单词”和“会做题”进入同一个闭环。
        </p>
        <div className="hero-actions">
          <a className="button primary-button hero-cta" href="#/app">
            <Play size={18} weight="fill" />
            在线探索演示前端
          </a>
          <a className="button ghost-button" href={DOWNLOAD_URL}>
            <DownloadSimple size={18} />
            下载 Windows 桌面版
          </a>
        </div>
        <div className="hero-meta">
          <span><CheckCircle size={14} weight="fill" /> 浅色 / 深色双主题</span>
          <span><CheckCircle size={14} weight="fill" /> 1:1 还原主应用前端</span>
          <span><CheckCircle size={14} weight="fill" /> GitHub Pages 静态部署</span>
        </div>
      </div>
      <ScrollHint />
    </section>
  );
}

function WordGalaxy() {
  const total = GALAXY_WORDS.length;
  return (
    <div className="word-galaxy" aria-hidden="true">
      {GALAXY_WORDS.map((item, index) => {
        // 螺旋分布：让单词环绕中心呈银河旋臂
        const angle = (index / total) * Math.PI * 8;
        const radius = 0.18 + (index / total) * 0.42;
        const side = index % 2 === 0 ? -1 : 1;
        const x = 50 + Math.cos(angle) * radius * 50 * side;
        const y = 50 + Math.sin(angle) * radius * 48;
        const depth = 0.4 + ((index * 7) % 10) / 10;
        const fontSize = 12 + ((index * 13) % 18);
        const delay = ((index * 17) % 100) / 25;
        const duration = 6 + ((index * 11) % 14);
        const blur = ((index * 3) % 5) * 0.4;
        return (
          <span
            className={`galaxy-word galaxy-word-${item.lang}`}
            key={`${item.text}-${index}`}
            style={cssVars({
              "--top": `${y}%`,
              "--left": `${x}%`,
              "--depth": depth,
              "--delay": `${delay}s`,
              "--duration": `${duration}s`,
              "--font-size": `${fontSize}px`,
              "--blur": `${blur}px`,
              fontWeight: item.weight ?? 500,
            })}
          >
            {item.text}
          </span>
        );
      })}
      <div className="galaxy-core" aria-hidden="true" />
    </div>
  );
}

function ScrollHint() {
  return (
    <a className="scroll-hint" href="#workflow" aria-label="向下滚动查看工作流">
      <span>Scroll</span>
      <span className="scroll-line" />
    </a>
  );
}

// ---------- 数据带 ----------

function StatsStrip() {
  return (
    <section className="stats-strip reveal">
      <div className="stats-inner">
        {STATS.map((stat) => (
          <div className="stat-item" key={stat.label}>
            <strong>{stat.value}</strong>
            <span>{stat.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- 工作流演示：单词飞入 → 题目飞出 → 题目飞到下方 ----------

function WorkflowSection() {
  return (
    <section className="workflow-section" id="workflow">
      <div className="section-heading reveal">
        <span className="section-eyebrow">01 · Workflow</span>
        <h2>从词条到题组，不再断层</h2>
        <p>单词汇入左侧学习状态，经中栏 Agent 组卷，再从右侧输出为可作答题卡，最后飞入下方演示题目区。</p>
      </div>

      <div className="workflow-stage reveal">
        <div className="workflow-frame">
          <div className="frame-topbar">
            <span className="frame-dots"><i /><i /><i /></span>
            <span className="frame-title">Lang Drill Agent · 三栏学习工作台</span>
            <span className="frame-actions"><Moon size={13} /><GearSix size={13} /></span>
          </div>
          <div className="frame-body">
            {/* 左栏：单词飞入 */}
            <aside className="wf-panel wf-left">
              <div className="wf-panel-title"><span className="wf-index">1</span>Vocabulary</div>
              <div className="wf-input-row"><span>Add word...</span><button type="button">Add</button></div>
              <div className="word-stack">
                {FLOW_WORDS.map((word) => (
                  <div className="flow-word" key={word.term}>
                    <strong>{word.term}</strong>
                    <span>{word.meaning}</span>
                  </div>
                ))}
              </div>
            </aside>

            {/* 中栏：Agent 组卷 */}
            <section className="wf-panel wf-center">
              <div className="wf-panel-title"><span className="wf-index">2</span>Generate</div>
              <div className="generator-core">
                <Sparkle size={32} weight="fill" />
                <span className="generator-ring" />
                <span className="generator-ring generator-ring-2" />
              </div>
              <div className="generator-lines">
                <span /><span /><span />
              </div>
              <p>Agent 生成考试式题组</p>
            </section>

            {/* 右栏：题目输出 */}
            <aside className="wf-panel wf-right">
              <div className="wf-panel-title"><span className="wf-index">3</span>Output</div>
              {QUESTION_CARDS.map((q) => (
                <div className="generated-question" key={q.type}>
                  <Cards size={16} />
                  <div>
                    <strong>{q.type}</strong>
                    <span>{q.stem.slice(0, 36)}…</span>
                  </div>
                  <ArrowRight size={14} />
                </div>
              ))}
            </aside>
          </div>
        </div>

        {/* 下方演示题目区：题目飞入 */}
        <div className="practice-strip">
          {QUESTION_CARDS.map((q, index) => (
            <article className="question-flight" key={q.type} style={cssVars({ "--flight-index": index })}>
              <header>
                <span className="q-index">0{index + 1}</span>
                <span className="q-type">{q.type}</span>
              </header>
              <p className="q-stem">{q.stem}</p>
              <div className="q-options">
                {q.options.map((option) => {
                  const isAnswer = option.startsWith(`${q.answer}.`);
                  return (
                    <span className={`q-option ${isAnswer ? "is-correct" : ""}`} key={option}>
                      {isAnswer ? <CheckCircle size={12} weight="fill" /> : null}
                      {option}
                    </span>
                  );
                })}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------- 核心痛点 ----------

function PainPointSection() {
  return (
    <section className="painpoint-section" id="painpoint">
      <div className="section-heading reveal">
        <span className="section-eyebrow">02 · Pain Point</span>
        <h2>核心痛点很简单：背词和刷题分离</h2>
        <p>Lang Drill Agent 把导入、出题、作答、讲解、复盘和统计放进同一个本地学习工作台。</p>
      </div>
      <div className="painpoint-grid">
        {PAIN_POINTS.map((point) => (
          <article className={`painpoint-card painpoint-${point.tone} reveal`} key={point.title}>
            <span className="painpoint-label">{point.label}</span>
            <h3>{point.title}</h3>
            <ul>
              {point.points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      <div className="painpoint-bridge reveal">
        <span className="bridge-arrow"><ArrowRight size={20} weight="bold" /></span>
        <p>导入即练习 · 练习即闭环 · 错题即复习</p>
      </div>
    </section>
  );
}

// ---------- 功能特性 ----------

function FeatureSection() {
  return (
    <section className="feature-section" id="features">
      <div className="section-heading reveal">
        <span className="section-eyebrow">03 · Features</span>
        <h2>完整能力，本地优先</h2>
        <p>从截图 OCR 到模型组卷，从分支对话到拓展 Skills，所有能力围绕同一个学习闭环展开。</p>
      </div>
      <div className="feature-grid">
        {FEATURE_ROWS.map((feature, index) => {
          const Icon = feature.icon;
          return (
            <article className="feature-card reveal" key={feature.title} style={cssVars({ "--card-index": index })}>
              <div className="feature-card-glow" aria-hidden="true" />
              <div className="feature-card-head">
                <span className="feature-icon">
                  <Icon size={22} weight="duotone" />
                </span>
                <span className="feature-tag">{feature.tag}</span>
              </div>
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

// ---------- 截图画廊 ----------

function ShowcaseSection() {
  const [activeIndex, setActiveIndex] = useState(0);
  return (
    <section className="showcase-section" id="showcase">
      <div className="section-heading reveal">
        <span className="section-eyebrow">04 · Showcase</span>
        <h2>真实前端脱敏截图</h2>
        <p>展示站使用脱敏截图辅助说明，所有交互演示仍可在演示前端中探索。</p>
      </div>
      <div className="showcase-stage reveal">
        <div className="showcase-main">
          <img
            src={SCREENSHOTS[activeIndex].src}
            alt={SCREENSHOTS[activeIndex].title}
            key={SCREENSHOTS[activeIndex].src}
          />
          <div className="showcase-caption">
            <strong>{SCREENSHOTS[activeIndex].title}</strong>
            <span>{SCREENSHOTS[activeIndex].body}</span>
          </div>
        </div>
        <div className="showcase-thumbs">
          {SCREENSHOTS.map((shot, index) => (
            <button
              type="button"
              className={`showcase-thumb ${index === activeIndex ? "is-active" : ""}`}
              onClick={() => setActiveIndex(index)}
              key={shot.src}
            >
              <img src={shot.src} alt={shot.title} loading="lazy" />
              <span>{shot.title}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------- 演示前端 CTA ----------

function DemoCtaSection() {
  return (
    <section className="demo-cta-section reveal" id="demo">
      <div className="demo-cta-glow" aria-hidden="true" />
      <div className="demo-cta-inner">
        <span className="section-eyebrow">05 · Live Demo</span>
        <h2>1:1 还原主应用前端</h2>
        <p>
          展示站内置一份与 Windows 桌面版同源的前端 mock：三栏可拖拽工作台、当前题卡、聊天与分支、
          截图导入、设置和拓展 Skills 都可以探索。模型回复固定为自我介绍 + 网页版开发中提示。
        </p>
        <div className="demo-cta-actions">
          <a className="button primary-button large" href="#/app">
            <Play size={20} weight="fill" />
            进入演示前端
          </a>
          <a className="button ghost-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GithubLogo size={18} />
            查看 GitHub 源码
          </a>
        </div>
        <ul className="demo-cta-list">
          <li><ChatsCircle size={16} /> 给模型发消息，固定返回自我介绍</li>
          <li><ImageSquare size={16} /> 拖入截图/文件，演示词条解析</li>
          <li><GearSix size={16} /> 设置页供应商、模型、考试、考纲原样保留</li>
          <li><PlugsConnected size={16} /> skill1 / skill2 占位，不暴露真实主机路径</li>
        </ul>
      </div>
    </section>
  );
}

// ---------- 安装区 ----------

function InstallSection() {
  return (
    <section className="install-section reveal">
      <div className="install-grid">
        <div className="install-copy">
          <span className="section-eyebrow">06 · Install</span>
          <h2>本地应用优先</h2>
          <p>
            当前推荐安装 Windows 桌面版体验完整能力。展示站里的演示前端可探索布局、题卡和设置流程，
            但不会调用真实模型或读取本地数据。
          </p>
          <div className="install-actions">
            <a className="button primary-button large" href={DOWNLOAD_URL}>
              <DownloadSimple size={20} />
              Windows 安装包
            </a>
            <a className="button ghost-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
              <GithubLogo size={20} />
              GitHub 仓库
            </a>
          </div>
        </div>
        <div className="install-code">
          <div className="code-head">
            <span><Code size={14} /> 快速开始</span>
            <button className="icon-button" type="button" aria-label="复制">
              <ClipboardText size={14} />
            </button>
          </div>
          <pre>
            <code>{`# 克隆仓库
git clone https://github.com/q2955161835-debug/lang-drill-agent.git
cd lang-drill-agent

# 一键启动 Web 开发模式
./start.bat

# 或构建桌面版安装包
powershell -File scripts/desktop/build-desktop.ps1`}</code>
          </pre>
          <div className="code-foot">
            <span><Database size={12} /> 数据本地化</span>
            <span><Target size={12} /> 9 内置考试</span>
            <span><Globe size={12} /> 内置联网检索</span>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------- 页脚 ----------

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <span className="brand-mark">
            <img className="brand-logo brand-logo-light" src="assets/logo-light.png" alt="" />
            <img className="brand-logo brand-logo-dark" src="assets/logo-dark.png" alt="" />
          </span>
          <strong>Lang Drill Agent</strong>
          <span>Vocabulary in. Exam drills out.</span>
        </div>
        <nav className="footer-nav" aria-label="页脚导航">
          <a href="#workflow">Workflow</a>
          <a href="#painpoint">Pain Point</a>
          <a href="#features">Features</a>
          <a href="#showcase">Showcase</a>
          <a href="#/app">Demo</a>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
        </nav>
        <div className="footer-meta">
          <span>© {new Date().getFullYear()} Lang Drill Agent</span>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            GitHub 仓库 <ArrowUpRight size={12} />
          </a>
        </div>
      </div>
    </footer>
  );
}

// ---------- 鼠标光晕 ----------

function CursorGlow() {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (window.matchMedia("(pointer: coarse)").matches) return;
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const onMove = (event: MouseEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        el.style.setProperty("--x", `${event.clientX}px`);
        el.style.setProperty("--y", `${event.clientY}px`);
      });
    };
    window.addEventListener("mousemove", onMove);
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);
  return <div className="cursor-glow" ref={ref} aria-hidden="true" />;
}

export default App;
