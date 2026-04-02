# Jenkins + Gitea + Nexus 自动化部署配置指南

## 环境信息

| 服务 | 地址 |
|------|------|
| Jenkins | http://10.10.80.35:8080 |
| Gitea | http://10.10.80.35:3000 |
| Nexus | http://10.10.80.35:8081 |
| 目标服务器 | http://10.10.80.37 |
| Docker Registry | 10.10.80.35:8082 |

---

## 一、Jenkins 插件安装

访问 `http://10.10.80.35:8080/manage/pluginManager/available`，安装以下插件：

1. **Git** - 代码拉取
2. **Pipeline** - 流水线编写
3. **Publish Over SSH** - 远程服务器部署
4. **SSH Agent** - SSH 认证支持

---

## 二、Nexus 配置 Docker 仓库

### 1. 访问 Nexus

访问 `http://10.10.80.35:8081`，使用默认账号登录：
- 用户名：`admin`
- 密码：`admin123`

### 2. 创建 Docker Hosted 仓库

1. 点击左侧 **Server Administration and configuration**（齿轮图标）
2. 选择 **Repositories** → **Create repository**
3. 选择 **docker (hosted)**
4. 填写配置：

```
Name:           docker-hosted
HTTP:           8082
Allow anonymous docker pull: ✓
Enable Docker V1 API:        ✓
```

5. 点击 **Create repository**

### 3. 添加 Docker 仓库到 Docker 客户端

在需要推送镜像的机器（Jenkins 服务器）上配置：

```bash
# 编辑 Docker 配置
vi /etc/docker/daemon.json

# 添加以下内容
{
  "insecure-registries": ["10.10.80.35:8082"]
}

# 重启 Docker
systemctl restart docker
```

---

## 三、Jenkins 凭证配置

### 1. Gitea 凭证

1. 进入 `Manage Jenkins` → `Credentials`
2. 点击 **Add Credentials**
3. 填写：

```
Kind:     Username with password
Username: root
Password: 你的Gitea密码
ID:       gitea-credentials
```

### 2. 服务器 SSH 凭证

1. 进入 `Manage Jenkins` → `Credentials`
2. 点击 **Add Credentials**
3. 填写：

```
Kind:     SSH Username with private key
Username: root
Private Key: Enter directly
           （粘贴服务器 SSH 私钥，或使用用户名/密码）
ID:       server-ssh-key
```

---

## 四、Jenkins 系统配置

### 配置 SSH 远程服务器

1. 进入 `Manage Jenkins` → `Configure System`
2. 找到 **Publish Over SSH** 部分
3. 点击 **Add**：

```
Name:          production-server
Hostname:      10.10.80.37
Username:      root
Password/Key:   你的服务器密码或私钥
Remote Dir:    /opt
```

---

## 五、创建 Jenkins 任务

### 方式一：从 Git 读取 Jenkinsfile（推荐）

1. 点击 `http://10.10.80.35:8080` → **New Item**
2. 名称：`neoflow-deploy`
3. 选择 **Pipeline**，点击 **OK**
4. 在 Pipeline 配置中选择 **Pipeline script from SCM**
5. 填写：

```
SCM:           Git
Repository URL: http://10.10.80.35:3000/root/neoflow.git
Credentials:   gitea-credentials
Branch:        */develop
Script Path:   Jenkinsfile
```

6. 保存

### 方式二：直接粘贴 Jenkinsfile

1. 选择 **Pipeline script**
2. 复制项目中的 `Jenkinsfile` 内容粘贴进去
3. 保存

---

## 六、触发构建

### 手动触发

1. 进入任务页面
2. 点击 **Build Now**

### 自动触发（代码推送时自动构建）

在任务配置中勾选：

```
✓ GitHub hook trigger for GITScm polling
```

或在 Gitea 中配置 Webhook：

1. 进入 Gitea 仓库 → **Settings** → **Webhooks**
2. 添加 Webhook：
   ```
   Target URL: http://10.10.80.35:8080/github-webhook/
   ```

---

## 七、验证部署

构建成功后，访问：

| 服务 | 地址 |
|------|------|
| API | http://10.10.80.37:8080 |
| Web | http://10.10.80.37:8080 |
| Supabase Studio | http://10.10.80.37:3001 |

---

## 八、常见问题

### 1. Docker 推送失败

检查 Jenkins 服务器是否配置了 `insecure-registries`：

```bash
cat /etc/docker/daemon.json
# 应该包含 "10.10.80.35:8082"
```

### 2. SSH 连接失败

检查：
- 服务器 SSH 是否开启
- 防火墙是否开放 22 端口
- Jenkins 凭证是否正确

### 3. Git 拉取失败

检查：
- Gitea 是否运行正常
- 仓库 URL 是否正确
- 凭证是否有效
