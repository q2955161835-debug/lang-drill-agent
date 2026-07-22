// 中文（简体）界面文案源目录。
// 这是源目录，英文和日文目录必须满足相同的 MessageCatalog 类型。

import type { MessageCatalog } from "../types";

export const zhCN: MessageCatalog = {
  // 应用壳与导航
  "app.title": "Lang Drill Agent",
  "app.settings": "设置",
  "app.settings.open": "打开设置",
  "app.newChat": "新聊天",
  "app.send": "发送",
  "app.cancel": "取消",
  "app.save": "保存",
  "app.confirm": "确认",
  "app.close": "关闭",
  "app.retry": "重试",
  "app.restoreDefaults": "恢复默认设置",
  "app.todayLearning": "当日学习",
  "app.longTermPanel": "长期学习记录",
  "app.longTermPanelTitle": "长期学习记录总面板",

  // 设置页签
  "settings.title": "设置",
  "settings.tab.model": "模型",
  "settings.tab.exam": "考试",
  "settings.tab.syllabus": "考纲",
  "settings.tab.tokens": "令牌",
  "settings.tab.data": "数据",
  "settings.tab.knowledge": "知识库",
  "settings.tab.memory": "记忆",
  "settings.tab.creative": "创造模式",
  "settings.tab.pastPapers": "真题库",
  "settings.tab.permissions": "权限",
  "settings.tab.skills": "拓展 Skills",
  "settings.tab.study": "学习",
  "settings.tab.appearance": "外观",
  "settings.tab.language": "语言",

  // 聊天区
  "chat.placeholder": "输入今日学习内容、答案或任何学习请求",
  "chat.sending": "发送中...",
  "chat.thinking": "模型正在思考",
  "chat.judging": "模型正在判题",
  "chat.recognizingImage": "模型正在识别图片",
  "chat.confirmingIntent": "正在确认练题意图",
  "chat.noSession": "暂无会话",
  "chat.emptyToday": "等待今日输入",
  "chat.imageVision": "模型视觉",
  "chat.imageMineru": "MinerU解析",
  "chat.imageHintVision": "拖入图片会随消息发给当前模型",
  "chat.imageHintMineru": "拖入图片会先调用 MinerU/本地 OCR 提取文本",

  // 长期面板统计
  "stats.examCountdown": "考试倒计时",
  "stats.examCountdownDetail": "按考试时间实时计算",
  "stats.examCountdownEmpty": "在设置中添加考试时间",
  "stats.currentExam": "当前考试",
  "stats.totalTokens": "累计 token（令牌）",
  "stats.questionsCompleted": "题目完成",
  "stats.wordsMastered": "单词掌握",
  "stats.overallAccuracy": "整体正确率",

  // 学习记忆
  "learningMemory.kicker": "Learning Memory（学习记忆）",

  // 考试状态
  "exam.deadlineNotSet": "未设置",
  "exam.deadlineReached": "考试时间已到",

  // 模型相关
  "model.unidentified": "未识别模型名称",
  "model.sameAsModelName": "同模型名",
  "model.visionSupported": "支持",
  "model.visionTextOnly": "文本模型",
  "model.provider": "模型供应商",
  "model.name": "模型",
  "model.confirmFillSettings": "确认填入设置",

  // 分支
  "branch.defaultPrompt": "请基于当前主会话全部内容，整理可继续追问的学习分支。",
  "branch.referenceMessage": "引用这条消息",
  "branch.needMainMessage": "需要先发送主会话消息",

  // 权限档位（创造模式）
  "creative.title": "创造模式",
  "creative.enable": "启用创造模式",
  "creative.runtimeReady": "运行时就绪",
  "creative.runtimeNotReady": "运行时未就绪",
  "creative.repair": "一键修复",
  "creative.repairing": "修复中...",
  "creative.openLog": "打开日志目录",
  "creative.failureCode": "失败代码",
  "creative.version": "版本",
  "creative.attemptedSteps": "已尝试步骤",
  "creative.logPath": "日志路径",
  "creative.manualInstall": "手动安装命令",
  "creative.profile.requestApproval": "逐次审批",
  "creative.profile.smartApproval": "智能审批",
  "creative.profile.fullAccess": "完全访问",
  "creative.profile.custom": "自定义",
  "creative.hardBlocks.title": "灾难性硬阻断（所有档位不可覆盖）",

  // 错误与状态
  "error.dataPathRefresh": "数据库统计刷新失败",
  "error.generic": "操作失败，请重试",
  "error.loading": "加载中...",
  "error.saveFailed": "保存失败",

  // 语言设置
  "language.label": "界面语言",
  "language.description": "仅影响应用界面文案，不影响模型回复、题目和自定义指令的语言。",
  "language.followSystem": "跟随系统",
};
