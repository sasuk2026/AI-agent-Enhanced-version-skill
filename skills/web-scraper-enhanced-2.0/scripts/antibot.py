"""反爬对抗层：真实浏览器指纹、UA 池、请求头构造、封锁判定、Stealth 注入脚本。

2.0 核心增强。目标：让抓取请求在服务端看起来就是一台真实的浏览器，
从而跳过目标站常见的反爬校验（UA 黑名单、请求头指纹、基础 JS 挑战）。

分层对抗能力：
  1) 静态请求层 —— 真实 UA 池轮换 + 完整浏览器级请求头 + Cookie 持续化
  2) 渲染层     —— Playwright 真实浏览器内核 + Stealth 补丁（见 renderer.py）
  3) 策略层     —— 封锁自动识别与升级（静态被拦 → 自动切渲染），见 fetcher.py

注意：本模块只做「指纹伪装与升级」，不破解验证码、不暴力撞库。
遇到验证码 / 登录墙 / 企业级 WAF 会如实报告（is_blocked_response）。
"""
from __future__ import annotations

import random
import re
from typing import Optional

# ---------------------------------------------------------------- UA 池
# 均为近期真实稳定版本的浏览器 UA（覆盖桌面 Chrome/Edge/Firefox/Safari + 移动端）
UA_POOL: list[str] = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Firefox / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Chrome / Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # 移动端 Chrome / Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    # 移动端 Safari / iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
]

# UA → sec-ch-ua 客户端提示（与 UA 池对应的大版本，给 Chrome/Edge 用）
_CHROME_VERSION = {"131": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                   "130": '"Google Chrome";v="130", "Chromium";v="130", "Not_A Brand";v="24"'}
_EDGE_VERSION = '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"'


def pick_ua(fixed: Optional[str] = None, rotate: bool = True) -> str:
    """选一个 UA。fixed 优先；否则按 rotate 决定池轮换/固定池首。"""
    if fixed:
        return fixed
    if rotate:
        return random.choice(UA_POOL)
    return UA_POOL[0]


def _sec_ch_ua(ua: str) -> Optional[str]:
    if "Edg/" in ua:
        return _EDGE_VERSION
    m = re.search(r"Chrome/(\d+)", ua)
    if m and "Chrome" in ua:
        return _CHROME_VERSION.get(m.group(1), _CHROLE_VERSION)
    return None


_CHROLE_VERSION = _CHROME_VERSION  # 兼容拼写


def _platform_of(ua: str) -> tuple[str, str]:
    """返回 (sec-ch-ua-platform, sec-ch-ua-mobile)。"""
    if "Windows" in ua:
        return '"Windows"', "?0"
    if "Macintosh" in ua or "Mac OS X" in ua:
        return '"macOS"', "?0"
    if "iPhone" in ua or "Android" in ua:
        return ('"Android"' if "Android" in ua else '"iOS"'), "?1"
    return '"Linux"', "?0"


def browser_headers(
    ua: str,
    referer: Optional[str] = None,
    extra: Optional[dict] = None,
    xml_http_request: bool = False,
) -> dict:
    """构造一套与真实浏览器一致的请求头（顺序即真实浏览器的发送顺序）。"""
    platform, mobile = _platform_of(ua)
    headers = {
        "User-Agent": ua,
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,image/apng,*/*;q=0.8,"
                   "application/signed-exchange;v=b3;q=0.7")
        if not xml_http_request else
        "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Sec-Ch-Ua": _sec_ch_ua(ua) or "",
        "Sec-Ch-Ua-Mobile": mobile,
        "Sec-Ch-Ua-Platform": platform,
        "Sec-Fetch-Dest": "document" if not xml_http_request else "empty",
        "Sec-Fetch-Mode": "navigate" if not xml_http_request else "cors",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1" if not xml_http_request else "",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    if extra:
        headers.update(extra)
    # 清理空值头（部分 WAF 对空 Sec-Ch-Ua 敏感）
    return {k: v for k, v in headers.items() if v}


# ---------------------------------------------------------------- 封锁判定
# 常见反爬/挑战页面的 HTML 特征（小写匹配）
BLOCK_MARKERS: tuple[str, ...] = (
    "just a moment",               # Cloudflare 5 秒盾
    "cf-browser-verification",
    "checking your browser",
    "challenge-platform",
    "_cf_chl_opt",
    "attention required",          # Cloudflare 错误页
    "verify you are human",        # reCAPTCHA/hCaptcha 提示
    "are you a robot",
    "i'm not a robot",
    "captcha",
    "access denied",               # 通用拒绝页
    "request blocked",
    "rate limit exceeded",
    "too many requests",
    "bot detection",
    "unsuccessful security check",
    "ddos protection by",          # 各类 DDoS 防护商
    "enable javascript and cookies",
)

BLOCK_STATUS = {401, 403, 429, 503}


def is_blocked_response(status: int, html: str = "",
                        headers: Optional[dict] = None) -> tuple[bool, str]:
    """判断一次响应是否属于「被反爬拦截」。

    返回 (blocked, reason)。404/410 等正常业务错误不算封锁。
    """
    if status in BLOCK_STATUS:
        # 429/503 常伴随 Retry-After，是限流而非硬封锁，单独标注
        reason = {401: "需要认证/登录", 403: "访问被拒绝（WAF/权限）",
                  429: "触发频率限制", 503: "服务不可用（可能是防护盾）"}.get(status, f"HTTP {status}")
        return True, reason
    if html:
        head = html[:200_000].lower()
        for marker in BLOCK_MARKERS:
            if marker in head:
                return True, f"检测到反爬挑战页特征：{marker!r}"
    if headers:
        server = str(headers.get("Server", "")).lower()
        if "cloudflare" in server and status >= 500:
            return True, "Cloudflare 5xx（疑似挑战）"
    return False, ""


# ---------------------------------------------------------------- Stealth 脚本
STEALTH_JS = r"""
// Playwright 注入：抹除常见自动化指纹，尽量让页面 JS 认为这是真人浏览器
(() => {
  // 1) webdriver 标志（最常见检测点）
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

  // 2) 伪造 window.chrome（Chromium 内核标识）
  if (!window.chrome) {
    window.chrome = {
      runtime: {},
      loadTimes: function () {},
      csi: function () {},
      app: {isInstalled: false},
    };
  }

  // 3) 语言与插件数量
  Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
  Object.defineProperty(navigator, 'plugins', {
    get: () => {
      const arr = [
        {name: 'PDF Viewer', filename: 'internal-pdf-viewer'},
        {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer'},
        {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer'},
        {name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer'},
        {name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer'},
      ];
      arr.item = (i) => arr[i] || null;
      arr.namedItem = (n) => arr.find(p => p.name === n) || null;
      arr.refresh = () => {};
      return arr;
    },
  });

  // 4) permissions.query 对 notifications 的返回值与真实浏览器一致
  const originalQuery = window.navigator.permissions?.query;
  if (originalQuery) {
    window.navigator.permissions.query = (parameters) => (
      parameters && parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters)
    );
  }

  // 5) 硬件指纹合理值（headless 常暴露 0/undefined）
  Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
  Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

  // 6) WebGL 厂商伪装（SwiftShader 是 headless 的典型特征）
  const getParameterOriginal = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function (parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameterOriginal.call(this, parameter);
  };

  // 7) 时区/语言一致性由 context 层设置，这里兜底 Date 精度指纹
  // （真实浏览器 Date.getTimezoneOffset 与 Intl 一致，Playwright 默认已处理）

  // 8) iframe contentWindow.navigator.webdriver 同步抹除
  const iframeDescriptor = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
  if (iframeDescriptor && iframeDescriptor.get) {
    const originalGetter = iframeDescriptor.get;
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
      get: function () {
        const win = originalGetter.call(this);
        if (win) {
          try {
            Object.defineProperty(win.navigator, 'webdriver', {get: () => undefined});
          } catch (e) { /* 跨域 iframe 无法访问，忽略 */ }
        }
        return win;
      },
    });
  }
})();
"""
