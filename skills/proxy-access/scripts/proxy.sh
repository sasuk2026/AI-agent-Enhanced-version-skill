#!/usr/bin/env bash
# proxy-access 配置与验证脚本
# 用法: proxy.sh <代理地址> [测试URL]
#   代理地址示例: http://127.0.0.1:7890  socks5://user:pass@1.2.3.4:1080
# 输出: JSON 风格的配置结果，供 agent 解析
set -uo pipefail

PROXY="${1:-}"
TEST_URL="${2:-https://www.google.com/generate_204}"

if [[ -z "$PROXY" ]]; then
  echo '{"ok":false,"error":"缺少代理地址参数，格式如 http://host:port 或 socks5://user:pass@host:port"}'
  exit 1
fi

# 规范化: 允许用户只给 host:port，默认按 http 处理
if [[ "$PROXY" != *"://"* ]]; then
  PROXY="http://${PROXY}"
fi
HOSTPORT="${PROXY#*://}"
HOSTPORT="${HOSTPORT%%@*}"
HOST="${HOSTPORT%%:*}"

# 1) 端口连通性（3 秒超时）
PORT="${HOSTPORT##*:}"
if ! timeout 3 bash -c "echo > /dev/tcp/$HOST/$PORT" >/dev/null 2>&1; then
  echo "{\"ok\":false,\"error\":\"无法连接代理 $HOST:$PORT（端口不通或代理未启动）\",\"proxy\":\"$PROXY\"}"
  exit 1
fi

# 2) 通过代理访问测试 URL
CODE=$(curl -s -m 10 -x "$PROXY" -o /dev/null -w '%{http_code}' "$TEST_URL" 2>/dev/null || echo "000")
if [[ "$CODE" == "204" || "$CODE" == "200" ]]; then
  echo "{\"ok\":true,\"proxy\":\"$PROXY\",\"test_url\":\"$TEST_URL\",\"http_code\":\"$CODE\",\"env\":{"
  echo "  \"http_proxy\":\"$PROXY\",\"https_proxy\":\"$PROXY\",\"all_proxy\":\"$PROXY\","
  echo "  \"no_proxy\":\"localhost,127.0.0.1,.internal\","
  echo "  \"git\":\"git config --global http.proxy $PROXY\","
  echo "  \"pip\":\"pip install --proxy $PROXY <pkg>\","
  echo "  \"npm\":\"npm config set proxy $PROXY && npm config set https-proxy $PROXY\","
  echo "  \"curl\":\"curl -x $PROXY <url>\"}}"
  exit 0
else
  echo "{\"ok\":false,\"error\":\"代理可达但测试请求失败\",\"proxy\":\"$PROXY\",\"test_url\":\"$TEST_URL\",\"http_code\":\"$CODE\"}"
  exit 1
fi
