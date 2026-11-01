# proxy-access

通过用户提供的代理地址连接海外平台（Google、GitHub、OpenAI、HuggingFace 等）。

> 设计为在本地环境运行：局域网代理（192.168.x.x 等）只能在能访问该局域网的本地机器上生效；云端运行需公网可达的代理地址。

## 用法
1. 安装本技能（目录含 SKILL.md 与 scripts/proxy.sh）
2. 对 Agent 说："代理是 http://host:port，帮我访问 GitHub"
