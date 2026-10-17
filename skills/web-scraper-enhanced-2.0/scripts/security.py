"""安全层：SSRF 防护 + 协议/主机校验。

增强版核心安全模块。抓取类 skill 最大的风险是 SSRF（服务端请求伪造）：
用户传入的 URL 看似外网，实际经 DNS 解析或 30x 重定向落到内网/云元数据地址，
从而泄露凭据或攻击内部服务。本模块在每次请求「前」与「后（含重定向链）」都做校验。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# 仅允许这两种面向资源的协议
ALLOWED_SCHEMES = {"http", "https"}

# 需要被拦截的保留/特殊地址段（云元数据是重点防护对象）
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),       # 含 169.254.169.254 云元数据
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("100.64.0.0/10"),        # CGNAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),             # 唯一本地地址
    ipaddress.ip_network("fe80::/10"),            # 链路本地
]


def _ip_is_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # 解析不了的按危险处理
    if addr.is_private or addr.is_loopback or addr.is_link_local or \
       addr.is_reserved or addr.is_multicast or addr.is_unspecified:
        return True
    for net in _BLOCKED_NETWORKS:
        if addr.version == net.version and addr in net:
            return True
    return False


def _resolve_host(host: str) -> list[str]:
    """解析主机名到所有 A/AAAA 记录；允许字面 IP 直接返回。"""
    try:
        return [r[4][0] for r in socket.getaddrinfo(host, None)]
    except (socket.gaierror, OSError):
        return []


def check_url(url: str, *, allow_private: bool = False) -> tuple[bool, str]:
    """校验单个 URL 是否可安全抓取。

    返回 (ok, reason)。allow_private 仅用于显式内网自检场景，默认 False。
    """
    if not url or not isinstance(url, str):
        return False, "URL 为空或非字符串"
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, f"协议 {parsed.scheme!r} 不被允许（仅支持 http/https）"
    host = parsed.hostname
    if not host:
        return False, "无法解析出主机名"
    if allow_private:
        return True, "私有地址放行（显式内网自检）"

    # 字面 IP 直接判定；域名则解析后逐 IP 判定（防 DNS rebinding 落内网）
    ips = [host] if _looks_like_ip(host) else _resolve_host(host)
    if not ips:
        return False, f"无法解析主机 {host!r}"
    for ip in ips:
        if _ip_is_blocked(ip):
            return False, f"目标解析到受限地址 {ip}（疑似内网/元数据，已拦截）"
    return True, "OK"


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def check_chain(urls: list[str], *, allow_private: bool = False) -> tuple[bool, str]:
    """校验完整重定向链上的每一个 URL。

    增强点：requests 默认跟随重定向，攻击者可借 30x 把请求引到内网；
    故对 history + 最终 URL 逐一校验。
    """
    for u in urls:
        ok, reason = check_url(u, allow_private=allow_private)
        if not ok:
            return False, f"重定向链中 {u!r} 被拦截：{reason}"
    return True, "OK"
