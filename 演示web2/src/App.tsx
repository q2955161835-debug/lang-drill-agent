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
  Warning,
} from "@phosphor-icons/react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP, ScrollTrigger);

// ---------- 类型与常量 ----------

type ThemeChoice = "system" | "light" | "dark";
type ResolvedTheme = "light" | "dark";

const GITHUB_URL = "https://github.com/q2955161835-debug/lang-drill-agent";
const DOWNLOAD_VERSION = "v1.0.0-alpha.2";
const DOWNLOAD_URL =
  "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v1.0.0-alpha.2/Lang.Drill.Agent_1.0.0-alpha.2_x64-setup.exe";

const THEME_OPTIONS: Array<{ value: ThemeChoice; label: string }> = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

// 单词银河：英文占 80%，日语占 20%，粒子构成银河旋臂
// 密度进一步提升至 ~3.6 倍（在原 3 倍基础上再增加 2 倍 → 1.2×3×2=7.2 → 但权衡性能保留 240 词）
const GALAXY_WORDS_EN: Array<{ text: string; weight?: number }> = [
  { text: "achieve" }, { text: "focus" }, { text: "growth" }, { text: "knowledge" },
  { text: "challenge" }, { text: "analyze" }, { text: "practice" }, { text: "review" },
  { text: "efficient" }, { text: "context" }, { text: "mastery" }, { text: "progress" },
  { text: "appropriate" }, { text: "sustainable" }, { text: "evaluate" }, { text: "question" },
  { text: "vocabulary", weight: 700 }, { text: "exam" }, { text: "drill", weight: 700 },
  { text: "agent", weight: 700 }, { text: "memory" }, { text: "fluency" }, { text: "insight" },
  { text: "satellite" }, { text: "nebula" }, { text: "orbit" }, { text: "particle" },
  { text: "horizon" }, { text: "iterate" }, { text: "comprehend" }, { text: "syntax" },
  { text: "acquire" }, { text: "absorb" }, { text: "articulate" }, { text: "assess" },
  { text: "brainstorm" }, { text: "clarify" }, { text: "compound" }, { text: "concept" },
  { text: "decode" }, { text: "deduce" }, { text: "derive" }, { text: "distinct" },
  { text: "elaborate" }, { text: "enhance" }, { text: "frame" }, { text: "grasp" },
  { text: "infer" }, { text: "integrate" }, { text: "master" }, { text: "navigate" },
  { text: "probe" }, { text: "pursue" }, { text: "retain" }, { text: "sequence" },
  { text: "synthesis" }, { text: "tackle" }, { text: "transform" }, { text: "validate" },
  { text: "grind" }, { text: "leverage" }, { text: "retain" }, { text: "anchor" },
  { text: "boost" }, { text: "calibrate" }, { text: "cement" }, { text: "distill" },
  { text: "echo" }, { text: "filter" }, { text: "forge" }, { text: "galvanize" },
  { text: "harness" }, { text: "ignite" }, { text: "kindle" }, { text: "loop" },
  { text: "model" }, { text: "narrate" }, { text: "orbit" }, { text: "process" },
  { text: "quiz" }, { text: "recap" }, { text: "stress" }, { text: "target" },
  { text: "unfold" }, { text: "verify" }, { text: "weigh" }, { text: "yield" },
  { text: "adapt" }, { text: "build" }, { text: "capture" }, { text: "digest" },
  { text: "extract" }, { text: "flow" }, { text: "ground" }, { text: "highlight" },
  { text: "intuition" }, { text: "journey" }, { text: "knack" }, { text: "lens" },
  // 密度 +2 倍新增词
  { text: "milestone" }, { text: "spark" }, { text: "anchor" }, { text: "cascade" },
  { text: "stream" }, { text: "ripple" }, { text: "trail" }, { text: "pulse" },
  { text: "shimmer" }, { text: "gleam" }, { text: "fractal" }, { text: "kernel" },
  { text: "matrix" }, { text: "vector" }, { text: "tensor" }, { text: "ratio" },
  { text: "median" }, { text: "outlier" }, { text: "sample" }, { text: "subset" },
  { text: "domain" }, { text: "cluster" }, { text: "node" }, { text: "edge" },
  { text: "graph" }, { text: "tree" }, { text: "leaf" }, { text: "branch" },
  { text: "queue" }, { text: "stack" }, { text: "heap" }, { text: "map" },
  { text: "filter" }, { text: "fold" }, { text: "merge" }, { text: "split" },
  { text: "pivot" }, { text: "scan" }, { text: "seed" }, { text: "trace" },
  { text: "evolve" }, { text: "drift" }, { text: "diffuse" }, { text: "converge" },
  { text: "diverge" }, { text: "orbit" }, { text: "sphere" }, { text: "arc" },
  { text: "trail" }, { text: "vault" }, { text: "peak" }, { text: "valley" },
  { text: "ridge" }, { text: "slope" }, { text: "delta" }, { text: "gamma" },
  { text: "alpha" }, { text: "beta" }, { text: "omega" }, { text: "sigma" },
  { text: "theta" }, { text: "lambda" }, { text: "phi" }, { text: "tau" },
  { text: "spark" }, { text: "flux" }, { text: "wave" }, { text: "tide" },
  { text: "drift" }, { text: "shift" }, { text: "lift" }, { text: "drop" },
  { text: "phase" }, { text: "state" }, { text: "stage" }, { text: "tier" },
  { text: "band" }, { text: "scope" }, { text: "realm" }, { text: "field" },
  { text: "lens" }, { text: "prism" }, { text: "beam" }, { text: "ray" },
];

const GALAXY_WORDS_JP: Array<{ text: string; weight?: number }> = [
  { text: "達成" }, { text: "集中" }, { text: "成長" }, { text: "知識" },
  { text: "挑戦" }, { text: "分析" }, { text: "練習" }, { text: "復習" },
  { text: "効率的" }, { text: "文脈" }, { text: "習得" }, { text: "進歩" },
  { text: "適切" }, { text: "持続可能" }, { text: "評価" }, { text: "問題" },
  { text: "語彙" }, { text: "試験" }, { text: "訓練" }, { text: "記憶" },
  { text: "流暢" }, { text: "洞察" }, { text: "理解" }, { text: "反復" },
  { text: "構文" },
  // 密度 +2 倍新增日语词
  { text: "思考" }, { text: "推論" }, { text: "仮説" }, { text: "検証" },
  { text: "実装" }, { text: "構築" }, { text: "形成" }, { text: "変換" },
  { text: "集約" }, { text: "展開" }, { text: "反映" }, { text: "結合" },
  { text: "分解" }, { text: "分類" }, { text: "抽出" }, { text: "選別" },
  { text: "段階" }, { text: "局面" }, { text: "範囲" }, { text: "領域" },
  { text: "境界" }, { text: "接続" }, { text: "連結" }, { text: "統合" },
  { text: "輪郭" }, { text: "軌道" }, { text: "波紋" }, { text: "余韻" },
  { text: "萌芽" }, { text: "萌芽" }, { text: "伏線" }, { text: "連鎖" },
];

// 工作流演示：单词 → 题目（数据保持不变，仅改动画）
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
    body: "截图、文本、文件里的词条会直接进入真实练习会话，自动生成考试式题组，让背词与刷题同步发生。",
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
    title: "模型讲解，本地统计",
    body: "Agent 生成题目和讲解，本地数据库负责落库、判分和统计，避免学习记录散落在聊天上下文里。",
    icon: Brain,
    tag: "Agent",
  },
  {
    title: "三栏学习工作台",
    body: "左侧学习状态、中间聊天与题目、右侧分支 / 截图导入，边界可拖拽，状态不丢失。",
    icon: Cards,
    tag: "Layout",
  },
  {
    title: "多考试与多考纲并行",
    body: "英语四六级、考研英语、日语四级等 9 种考试与对应考纲同时支持，按考试目标自动匹配题型。",
    icon: Target,
    tag: "Exams",
  },
  {
    title: "复习算法，错题回流",
    body: "掌握度分、错题权重与间隔复习窗口共同决定下一轮内容，让新题、错题和待巩固词按优先级回到练习。",
    icon: Sparkle,
    tag: "Review",
  },
];

// 截图清单：每张图都带 light/dark 两个版本
const SCREENSHOTS = [
  { file: "01-cet4-home-long-panel", title: "长期学习总面板", body: "题目完成、词汇掌握、正确率和考试倒计时同一口径。" },
  { file: "07-cet4-active-question", title: "当前题吸附卡", body: "中栏聊天与题卡同一学习流推进，自动下一题。" },
  { file: "09-cet4-answer-feedback-extra-question", title: "答题反馈", body: "作答后判题讲解、补充提问和下一题自动推进。" },
  { file: "14-cet4-screenshot-import-parsed", title: "截图词表导入", body: "OCR 后先编辑词条，确认后再导入并生成题组。" },
  { file: "12-branch-selected-text-reference-card", title: "分支引用", body: "划词进入右侧分支，主会话不被污染。" },
  { file: "06-cet4-daily-summary", title: "当日总结", body: "模型结合数据库明细生成复盘、错题归因与建议。" },
  { file: "13-cet4-screenshot-import-queued", title: "截图入队", body: "多张单词截图依次入队，等待 OCR 解析。" },
  { file: "18-settings-model-mimo", title: "模型配置", body: "供应商、模型、视觉能力与上下文容量集中管理。" },
  { file: "20-settings-exam", title: "考试选择", body: "目标考试、考试时间和目标语言集中设置。" },
  { file: "21-settings-syllabus-papers", title: "考纲真题", body: "考纲版本、历年真题和题型勾选一目了然。" },
  { file: "23-settings-token-ledger", title: "令牌台账", body: "使用台账、模型排行和最近调用透明可见。" },
  { file: "26-settings-skills", title: "拓展 Skills", body: "内置联网始终可用，拓展 Skill 单项开关控制。" },
  { file: "29-cjt4-home-long-panel", title: "日语四级面板", body: "切换日语四级后的长期学习总面板。" },
  { file: "30-cjt4-active-question", title: "日语四级题卡", body: "CJT4 同样支持语境题、阅读和翻译题型。" },
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
  { value: "3", label: "核心复习信号" },
  { value: "6+", label: "题型自动组卷" },
  { value: "1", label: "复习学习闭环" },
];

// ---------- 工具函数 ----------

function isThemeChoice(value: string | null): value is ThemeChoice {
  return value === "system" || value === "light" || value === "dark";
}

function cssVars(vars: Record<string, string | number>): CSSProperties {
  return vars as CSSProperties;
}

function resolveTheme(choice: ThemeChoice, media: MediaQueryList | null): ResolvedTheme {
  if (choice === "system") {
    return media && media.matches ? "dark" : "light";
  }
  return choice;
}

function useResolvedTheme(choice: ThemeChoice): ResolvedTheme {
  const getSnapshot = () => {
    if (typeof window === "undefined") return "dark" as ResolvedTheme;
    return resolveTheme(choice, window.matchMedia("(prefers-color-scheme: dark)"));
  };
  const [theme, setTheme] = useState<ResolvedTheme>(getSnapshot);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setTheme(resolveTheme(choice, media));
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [choice]);
  return theme;
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
        gsap.set(".reveal, .flow-word, .generated-question, .question-flight, .galaxy-word", {
          autoAlpha: 1, x: 0, y: 0, filter: "none", scale: 1,
        });
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

      // 单词银河整体：随滚动逐渐淡出（不缩小，避免词越滚越小）
      gsap.to(".word-galaxy", {
        y: 60,
        opacity: 0,
        ease: "power2.in",
        scrollTrigger: {
          trigger: ".hero",
          start: "bottom 90%",
          end: "bottom 40%",
          scrub: 1,
        },
      });

      // 工作流：滚动到页面下方 1/3 处完整完成
      // 1) 单词从左侧汇聚进入中央 Generate 图标
      // 2) 单词向右滑动渐变消失到 Generate 的左 2/9 处
      // 3) 题卡从 Generate 的 7/9 处渐变出现，移动到 Output 框的正确位置
      // Generate 图标保持静态（不随滚动变化），仅靠 CSS animation 持续脉冲
      const workflowTimeline = gsap.timeline({
        scrollTrigger: {
          trigger: ".workflow-stage",
          start: "top 80%",
          end: "bottom 67%", // 滚到页面下方 1/3 处完整完成
          scrub: 1,
        },
      });

      workflowTimeline
        // 1. 单词从左栏 Vocabulary 飞入到原位置
        .fromTo(
          ".flow-word",
          {
            autoAlpha: 0,
            x: -120,
            y: (_i: number) => [-30, 15, -8, 22, 0][_i % 5],
            scale: 0.6,
            filter: "blur(4px)",
          },
          {
            autoAlpha: 1,
            x: 0,
            y: 0,
            scale: 1,
            filter: "blur(0px)",
            stagger: 0.04,
            ease: "power2.out",
            duration: 1.0,
          }
        )
        // 2. 单词向右滑动渐变消失到 Generate 的左 2/9 处（用 vw 单位跨栏位移）
        .to(".flow-word", {
          autoAlpha: 0,
          x: "20vw", // 视口宽度的 20%，大致是左栏中央到 Generate 左 2/9 处的距离
          y: 0,
          scale: 0.35,
          filter: "blur(8px)",
          stagger: 0.02,
          ease: "power2.in",
          duration: 0.5,
        })
        // 3. 题卡从 Generate 的 7/9 处渐变出现，移动到 Output 框的正确位置
        //    用 xPercent 相对自身宽度偏移，避免 stagger 时多个题卡 x 位置错位
        .fromTo(
          ".generated-question",
          {
            autoAlpha: 0,
            xPercent: -35, // 向左偏移自身宽度的 35%（从 Generate 7/9 处出现）
            scale: 0.5,
            filter: "blur(8px)",
          },
          {
            autoAlpha: 1,
            xPercent: 0, // 回到 Output 框的 CSS 原位置
            scale: 1,
            filter: "blur(0px)",
            stagger: 0.06,
            ease: "power3.out",
            duration: 0.7,
          },
          "<0.05"
        )
        // 4. 题卡从 Output 区飞到下方题卡区（被题卡界面遮挡）
        .to(".generated-question", {
          autoAlpha: 0,
          y: "+=160",
          scale: 0.8,
          filter: "blur(6px)",
          stagger: 0.05,
          ease: "power2.in",
          duration: 0.5,
        })
        // 5. 下方题卡从无到有渐变呈现
        .fromTo(
          ".question-flight",
          {
            autoAlpha: 0,
            y: -40,
            scale: 0.9,
            filter: "blur(8px)",
          },
          {
            autoAlpha: 1,
            y: 0,
            scale: 1,
            filter: "blur(0px)",
            stagger: 0.12,
            ease: "power3.out",
            duration: 0.7,
          },
          "<0.1"
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
  const base = import.meta.env.BASE_URL;

  return (
    <header className={`site-header ${scrolled ? "is-scrolled" : ""}`}>
      <div className="header-inner">
        <a className="brand-link" href="#top" aria-label="Lang Drill Agent 首页">
          <span className="brand-mark">
            <img className="brand-logo brand-logo-light" src={`${base}assets/logo-light.png`} alt="" />
            <img className="brand-logo brand-logo-dark" src={`${base}assets/logo-dark.png`} alt="" />
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
            <span>Download {DOWNLOAD_VERSION}</span>
          </a>
        </div>
      </div>
    </header>
  );
}

// ---------- Hero 区：动态单词银河 ----------

function HeroSection() {
  const base = import.meta.env.BASE_URL;
  return (
    <section className="hero" id="top">
      <div
        className="hero-bg-image"
        aria-hidden="true"
        style={{ backgroundImage: `url(${base}assets/hero-bg-texture.jpg)` }}
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
          把截图词表、文本词条和文件材料变成考试式题组，让"记住单词"和"会做题"进入同一个闭环。
        </p>
        <div className="hero-actions">
          <a className="button primary-button hero-cta" href="#/app">
            <Play size={18} weight="fill" />
            在线体验
          </a>
          <a className="button ghost-button" href={DOWNLOAD_URL}>
            <DownloadSimple size={18} />
            下载 Windows 桌面版 {DOWNLOAD_VERSION}
          </a>
        </div>
        <div className="hero-meta">
          <span><CheckCircle size={14} weight="fill" /> 浅色 / 深色双主题</span>
          <span><CheckCircle size={14} weight="fill" /> 多考试与多考纲并行</span>
          <span><CheckCircle size={14} weight="fill" /> 复习算法，错题回流</span>
        </div>
      </div>
      <ScrollHint />
    </section>
  );
}

// 伪随机数生成器（seeded），保证每次渲染位置一致
function seededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function WordGalaxy() {
  const items: Array<{ text: string; lang: "en" | "jp"; weight?: number }> = [
    ...GALAXY_WORDS_EN.map((w) => ({ ...w, lang: "en" as const })),
    ...GALAXY_WORDS_JP.map((w) => ({ ...w, lang: "jp" as const })),
  ];
  const total = items.length;
  const rng = seededRandom(42);

  // 预计算每个词的位置和动画参数
  const wordData = items.map((item, i) => {
    // 极坐标分布：角度均匀分布 + 半径从中心向外，形成银河盘面
    const angle = rng() * Math.PI * 2;
    // 半径用平方根分布让密度均匀（避免中心过密），范围 5%~48%
    const r = Math.sqrt(rng()) * 43 + 5;
    const x = 50 + Math.cos(angle) * r;
    const y = 50 + Math.sin(angle) * r * 0.75; // 椭圆：y 轴压缩

    // 距离中心归一化（0=中心，1=边缘）
    const dist = Math.min(r / 48, 1);

    // 字号：中心词大（20-24px），边缘词小（13-16px），权重词更大
    const baseSize = item.weight ? 20 : 14;
    const fontSize = Math.round(baseSize + (1 - dist) * 8 + rng() * 3);

    // 中心词更亮不模糊，边缘词略透明轻微模糊
    const opacity = 0.45 + (1 - dist) * 0.55;
    const blur = dist * 1.2;

    // 飘动参数：随机方向、速度
    const driftX = (rng() - 0.5) * 30;
    const driftY = (rng() - 0.5) * 20;
    const driftDur = 8 + rng() * 10;
    const driftDelay = -rng() * driftDur;

    return { item, x, y, dist, fontSize, opacity, blur, driftX, driftY, driftDur, driftDelay, i };
  });

  return (
    <div className="word-galaxy" aria-hidden="true">
      {wordData.map(({ item, x, y, dist, fontSize, opacity, blur, driftX, driftY, driftDur, driftDelay, i }) => (
        <span
          key={`${item.text}-${i}`}
          className={`galaxy-word galaxy-word-${item.lang}`}
          style={cssVars({
            "--gw-x": `${x}%`,
            "--gw-y": `${y}%`,
            "--gw-size": `${fontSize}px`,
            "--gw-opacity": opacity.toFixed(3),
            "--gw-blur": `${blur.toFixed(2)}px`,
            "--gw-dx": `${driftX.toFixed(1)}px`,
            "--gw-dy": `${driftY.toFixed(1)}px`,
            "--gw-dur": `${driftDur.toFixed(1)}s`,
            "--gw-delay": `${driftDelay.toFixed(1)}s`,
            fontWeight: item.weight ? 700 : 400 + Math.round((1 - dist) * 200),
          })}
        >
          {item.text}
        </span>
      ))}
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
        <p>导入的词条在 Agent 里自动生成考试式题组，作答、讲解和错题回流全部在同一个学习闭环里完成。</p>
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
        <h2>完整能力，复习闭环</h2>
        <p>从截图 OCR 到 Agent 组卷，从分支对话到拓展 Skills，所有能力围绕同一个学习闭环展开。</p>
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

// ---------- 真实用户体验截图 ----------

function ShowcaseSection() {
  const [activeIndex, setActiveIndex] = useState(0);
  // 主题感知：根据当前主题选择 light/dark 图片
  const [theme, setTheme] = useState<ResolvedTheme>(() => {
    if (typeof document !== "undefined") {
      const attr = document.documentElement.dataset.theme;
      if (attr === "light" || attr === "dark") return attr;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const attr = document.documentElement.dataset.theme;
      if (attr === "light" || attr === "dark") setTheme(attr);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  const base = import.meta.env.BASE_URL;
  const active = SCREENSHOTS[activeIndex];
  const activeSrc = `${base}assets/screenshots/${theme}-${active.file}.png`;

  return (
    <section className="showcase-section" id="showcase">
      <div className="section-heading reveal">
        <span className="section-eyebrow">04 · Showcase</span>
        <h2>真实用户体验</h2>
        <p>以下截图来自真实学习场景，跟随当前主题自动切换浅色 / 深色版本。</p>
      </div>
      <div className="showcase-stage reveal">
        <div className="showcase-main-col">
          <div className="showcase-main">
            <img
              src={activeSrc}
              alt={active.title}
              key={`${theme}-${active.file}`}
            />
          </div>
          <div className="showcase-caption-below">
            <strong>{active.title}</strong>
            <span>{active.body}</span>
          </div>
        </div>
        <div className="showcase-thumbs">
          {SCREENSHOTS.map((shot, index) => {
            const src = `${base}assets/screenshots/${theme}-${shot.file}.png`;
            return (
              <button
                type="button"
                className={`showcase-thumb ${index === activeIndex ? "is-active" : ""}`}
                onClick={() => setActiveIndex(index)}
                key={shot.file}
              >
                <img src={src} alt={shot.title} loading="lazy" />
                <span>{shot.title}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// ---------- 在线体验 CTA ----------

function DemoCtaSection() {
  return (
    <section className="demo-cta-section reveal" id="demo">
      <div className="demo-cta-glow" aria-hidden="true" />
      <div className="demo-cta-inner">
        <span className="section-eyebrow">05 · Live Demo</span>
        <h2>在浏览器里直接体验</h2>
        <p>
          展示站内置完整的桌面版前端，三栏可拖拽工作台、当前题卡、聊天与分支、截图导入、
          设置和拓展 Skills 都可以自由探索。所有数据均为演示用，不会调用真实模型或读取本地文件。
        </p>
        <div className="demo-cta-actions">
          <a className="button primary-button large" href="#/app">
            <Play size={20} weight="fill" />
            进入在线体验
          </a>
          <a className="button ghost-button" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GithubLogo size={18} />
            查看 GitHub 源码
          </a>
        </div>
        <ul className="demo-cta-list">
          <li><ChatsCircle size={16} /> 与模型对话，体验学习流程</li>
          <li><ImageSquare size={16} /> 拖入截图或文件，查看词条解析</li>
          <li><GearSix size={16} /> 设置供应商、模型、考试与考纲</li>
          <li><PlugsConnected size={16} /> 探索拓展 Skills 与分支对话</li>
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
          <h2>复习策略可追踪</h2>
          <p>
            推荐安装 Windows 桌面版体验完整能力：掌握度分、错题权重和间隔复习窗口会随每次作答更新，下一轮优先召回最应该巩固的词和题。
            当前版本 {DOWNLOAD_VERSION} 为实验版（Experimental），首次集成分层记忆、知识库 RAG 引用、Agent 计划时间线、Pi 创造模式、真实真题检索与蒸馏、三语 UI 和应用内签名更新中心；内测未签名安装包首次运行可能触发 Windows SmartScreen 提示，请选择"仍要运行"。
          </p>
          <div className="install-warning">
            <Warning size={16} weight="fill" />
            <span>测试版未代码签名，安装时如遇 SmartScreen 警告请选择"更多信息 → 仍要运行"。</span>
          </div>
          <div className="install-actions">
            <a className="button primary-button large" href={DOWNLOAD_URL}>
              <DownloadSimple size={20} />
              Windows 安装包 {DOWNLOAD_VERSION}
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
            <span><Brain size={12} /> 掌握度回流</span>
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
  const base = import.meta.env.BASE_URL;
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <span className="brand-mark">
            <img className="brand-logo brand-logo-light" src={`${base}assets/logo-light.png`} alt="" />
            <img className="brand-logo brand-logo-dark" src={`${base}assets/logo-dark.png`} alt="" />
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
