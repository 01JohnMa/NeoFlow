
  Claude Code 使用技巧指南

  1. 常用快捷方式和命令

  核心快捷键

  - Ctrl+C：取消当前输入或生成
  - Ctrl+D：退出会话
  - Ctrl+L：清屏（保留对话历史）
  - Shift+Tab：循环切换权限模式（普通→自动接受→计划模式）
  - Ctrl+B：后台运行任务
  - Esc + Esc：回滚代码/对话到之前的状态

  多行输入

  - \ + Enter：所有终端通用换行
  - Shift+Enter：iTerm2、WezTerm等中默认可用

  文本编辑

  - Ctrl+K：删除到行尾（可粘贴）
  - Ctrl+U：删除整行（可粘贴）

  2. 最佳实践和工作流程

  高效文件引用

  - 使用 @ 符号快速引用文件：
  > 解释 @src/utils/auth.js 中的逻辑
  > @src/components 的结构是什么？

  会话管理

  - 命名会话：/rename auth-refactor
  - 恢复会话：claude --resume auth-refactor
  - 并行会话：使用Git worktrees创建隔离环境

  计划模式

  - 启动：claude --permission-mode plan
  - 切换：Shift+Tab 两次进入计划模式
  - 用途：安全分析代码库、规划复杂变更、代码审查

  3. 工具高效使用技巧

  Bash工具

  - 环境变量持久化：设置 CLAUDE_ENV_FILE=/path/to/env-setup.sh
  - 后台命令：按 Ctrl+B 将命令移到后台执行

  搜索工具

  - Glob模式：Glob("**/*.test.js") 查找测试文件
  - Grep高级搜索：使用 -A 3 -B 2 显示上下文，-i 忽略大小写

  文件操作

  - 批量读取：同时读取多个相关文件提供完整上下文
  - 增量编辑：先使用 Read 查看，再用 Edit 修改

  自定义斜杠命令

  # 创建项目命令
  mkdir -p .claude/commands
  echo "分析这段代码的性能问题并建议优化：" > .claude/commands/optimize.md

  # 使用参数
  echo '修复问题 #$ARGUMENTS' > .claude/commands/fix-issue.md
  # 使用：/fix-issue 123

  4. 配置和自定义技巧

  权限配置（.claude/settings.json）

  {
    "permissions": {
      "allow": [
        "Bash(npm run lint)",
        "Bash(npm run test:*)"
      ],
      "deny": [
        "Bash(curl:*)",
        "Read(./.env)",
        "Read(./secrets/**)"
      ]
    }
  }

  环境变量优化

  # 减少非必要流量
  export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

  # 自定义思考令牌
  export MAX_THINKING_TOKENS=4096

  # 使用系统ripgrep提升搜索性能
  export USE_BUILTIN_RIPGREP=0

  # 隐藏账户信息（录制时有用）
  export CLAUDE_CODE_HIDE_ACCOUNT_INFO=1

  5. 调试和故障排除

  诊断工具

  - /doctor：检查安装健康状况
  - /context：可视化当前上下文使用情况
  - /cost：查看令牌使用统计

  性能优化

  - 定期压缩：使用 /compact 减少上下文大小
  - 搜索优化：安装系统 ripgrep 并设置 USE_BUILTIN_RIPGREP=0

  常见错误解决

  - 认证问题：运行 /logout 然后重新登录
  - 命令卡住：按 Ctrl+C，如无效则重启终端

  6. 与其他工具的集成

  IDE集成

  - VS Code扩展：提供更好的代码编辑体验
  - JetBrains插件：支持IntelliJ、PyCharm等
  - Chrome扩展：测试本地Web应用、调试控制台日志

  MCP服务器配置

  // .mcp.json
  {
    "mcpServers": {
      "github": {
        "command": "npx",
        "args": ["@modelcontextprotocol/server-github", "--token", "${env:GITHUB_TOKEN}"]
      }
    }
  }

  高级技巧

  1. 扩展思考（Extended Thinking）

  - 启用：ultrathink: 设计我们的API缓存层
  - 快捷键：Option+T (macOS) / Alt+T (Windows/Linux)

  2. 沙盒模式

  {
    "sandbox": {
      "enabled": true,
      "autoAllowBashIfSandboxed": true
    }
  }

  3. 钩子（Hooks）自动化

  {
    "hooks": {
      "PreToolUse": {
        "Bash": {
          "matcher": "rm -rf",
          "hooks": [{
            "type": "command",
            "command": "echo '危险操作！' && exit 1"
          }]
        }
      }
    }
  }

  4. 子代理专业化

  ---
  description: 代码审查专家
  model: claude-3-5-sonnet-20241022
  allowed-tools: Read, Grep, Bash(git diff:*)
  ---

  你是一个专业的代码审查员，专注于：
  1. 安全漏洞
  2. 性能问题
  3. 代码风格一致性

  实用工作流示例

  代码审查流程

  # 1. 获取更改概览
  > 总结我对认证模块的更改

  # 2. 安全审查
  > /security-review

  # 3. 运行测试
  > 运行测试并修复任何失败

  # 4. 创建PR
  > 创建PR

  调试流程

  # 1. 重现错误
  > 当我运行npm test时看到错误

  # 2. 分析堆栈跟踪
  > 分析这个堆栈跟踪并建议修复

  # 3. 应用修复
  > 更新user.ts添加你建议的空检查

  # 4. 验证修复
  > 再次运行测试确认修复

  总结建议

  1. 开始简单：先掌握基本命令和快捷键
  2. 逐步深入：按需学习高级功能
  3. 团队标准化：在项目中共享配置和命令
  4. 安全第一：配置适当的权限和沙盒
  5. 定期维护：压缩会话、监控成本、更新配置

  您可以根据项目需求逐步应用这些技巧，提高开发效率。