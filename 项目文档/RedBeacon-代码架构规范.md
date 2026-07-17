# RedBeacon 代码架构规范（六边形 · 人机协作）

> 🔴 **本规范对代码层有约束力（2026-06-27 老板拍板纳入）**：开发窗口写 `cli/` 任何**新代码**、以及为"独立 UI"做的引擎改造，**必须遵守本文**。下半部「设计理念 + 编码规范」是老板提供的通用范本，**原文照收、不得删改**；上半部是 PM 加的 **RedBeacon 落地映射**（怎么把这套套到本项目），开发据此对号入座。
> 与本文冲突时，本架构规范 + `项目进度.md` 的红线优先；实现有偏离按惯例回报 PM 同步。

---

## 0. RedBeacon 落地映射（PM 注，开发对号入座）

把范本里的 core/infra/adapters/composition 映射到 RedBeacon：

| 范本层 | RedBeacon 具体 | 说明 |
|---|---|---|
| **core/ 核心用例** | 定位 / 选题 / 写文案 / 配图 / 审稿 / 发布 等**业务用例函数**（纯逻辑、不认框架） | 现在这些逻辑散在 `routers/`、`tasks/` 里、和飞书/DB/HTTP 调用混着——**要抽进 core/**，成为 UI/CLI/skill 共享的唯一逻辑。 |
| **core/ports.py 端口** | `飞书数据口` / `平台AI口(对话+生图)` / `小红书发布口(cloakbrowser)` / `本地存储口` 等 Protocol 抽象 | 核心只认抽象接口，不认具体实现。 |
| **infra/ 基础设施** | 飞书 API 客户端 / 平台网关客户端(`/v1/chat`、`/v1/images`) / cloakbrowser / 本地文件 | 端口的真实现，可替换、可换桩件测。 |
| **adapters/ 各个面** | ① **CLI**(现有 typer) ② **skill**(AI 面) ③ **UI 后端**(新：本机 HTTP 服务，给浏览器 UI 用) | 全是薄壳，**都直接 import 同一批 core 用例**。⚠️ **UI 后端绝不许去拼 CLI 命令 / 爬 CLI 文字输出**（范本§八红线）。 |
| **composition.py 组装根** | 唯一一处挑 infra 实现注入核心 | 换真实/桩件只改这里。 |

**几条 RedBeacon 专属强约束（叠加在范本红线之上）：**
1. 🔴 **飞书 = 那"一份中心数据"的真源**（范本§一"数据是锚"）。**禁止本地存第二份业务数据 + 禁止双向同步**（这是本轮重构的命根子，详见 `项目进度.md` UI 结构红线）。UI 审稿 = core 用例直接读写飞书，自己不留副本。
2. 🔴 **客户端永不持上游 AI key**；文案/定位/选题/生图的 AI 一律走"平台AI口"(infra)带设备令牌；免费/本地只剩文字卡渲染、发布、飞书读写。（接入规范铁律，已随"文案走平台"改写。）
3. 🔴 **`account_id` 由令牌/会话服务端解出，core 用例不信外部传入的 account_id**（防 IDOR）。
4. **三个面共享 core**：同一个"发布""写文案"用例，CLI 跑一遍、UI 点一下、skill 调一次，走的是**同一个函数**，不许各写一份。

**落地节奏（PM 建议，避免大爆炸重写）：** 现有引擎不是六边形结构（逻辑混在 adapters 里）。**不要求一次性重写全部**；按"UI 用到哪个用例，就先把那个用例规规矩矩抽进 core/（带端口 + 桩件测）"，UI 与存量 CLI 共享之；其余存量逻辑**机会性迁移**。新代码一律按本规范写、不再往 adapters 里塞业务逻辑。

---

# （以下为老板提供的通用范本 · 原文照收）

# 人机协作软件设计理念(AI 原生 · 六边形架构)

> 本文件是一份**设计理念 + 编码规范**,供 AI 在本项目中创作代码时学习并遵守。
> 它先讲清楚"为什么这样设计"(理念),再给出"具体怎么写"(结构与代码)。
> 读完后,AI 写任何新代码都应当符合这里的原则。

---

## 一、核心理念

### 1. 数据是锚,一切入口都是为了更好地操作数据

软件存在的意义,是为了更好地操作数据。**数据层是整个系统唯一不可替代的中心**;
CLI、API、MCP、UI 都只是建立在"操作数据"之上的不同入口(面)。

它们不是互相替代、互相竞争的关系,而是同一份核心逻辑的不同投影:

```
        CLI ─┐
        API ─┤
   MCP 工具 ─┤──►  核心用例(唯一逻辑)──►  数据 / 外部系统
     UI 后端 ─┘
```

判断任何一段代码是否健康,只有一个标准:**它有没有老实地通过核心去读写那一份中心数据,
而不是自己偷偷攒一套逻辑或一份状态。**

### 2. 真正的核心不是 CLI,是"用例函数"

CLI 本身也只是一个"面"——它干的事是把文字参数解析成调用、再把结果格式化成文字。
真正干活的是 CLI 背后调用的那批**对数据做操作的用例函数**。

所以:**不要让 UI 建立在 CLI 之上(去拼命令字符串、爬 CLI 的文字输出),
而要让 CLI、API、MCP、UI 并排站在同一个"核心"之上。** 逻辑只写一遍,所有入口共享(DRY)。

### 3. 人机协作:人提供判断,AI 提供执行

本项目面向"人机共创"形态。人的角色不是"操作员",而是上移到了**判断、品味、意图、方向**;
AI 负责执行、规模、速度。"人提供想法,机器提供更好的执行。"

因此衡量人的重要性,**不该用"手动操作量"来衡量**。人的入口(UI / 画布)存在的意义,
是让人**看见成品、做出判断、随时介入与否决**,而不是让人去学一套复杂的操作流程。

### 4. 内容共创需要一块"共同操作的画布"

纯命令行 / 纯对话有一个隐形门槛:用户得先知道有某个功能、还得会把它说出来。
而图形界面的杀手锏不是"好看",而是**让人不必事先知道该问什么,就能看见自己能干什么**。

尤其对"内容打磨"这类场景:人的"好/不好"判断作用在**渲染后的成品**上,不是作用在命令上。
所以需要一块**人和 AI 都能操作同一份状态**的画布(canvas):AI 在一侧执行/批量,
人在另一侧看成品、圈选、微调,两边写的是同一份数据。应用是常驻环境,AI 是嵌在里面的协作者,
而不是反过来让 AI 当唯一总闸。

---

## 二、架构:六边形(Ports & Adapters)

核心在中心,适配器在四周,**所有依赖箭头都指向核心**:

```
                 ┌─────────────┐
                 │  CLI 适配器  │
                 └──────┬──────┘
                        │ (依赖)
   ┌──────────┐   ┌─────▼──────┐   ┌──────────┐
   │ API 适配器│──►│   核心      │◄──│ MCP 适配器│
   └──────────┘   │ 领域 + 用例 │   └──────────┘
                  │ 不认识任何   │
                  │ 框架/UI/HTTP │
                  └─────▲──────┘
                        │ (依赖)
                 ┌──────┴──────┐
                 │  UI 后端适配器│
                 └─────────────┘
```

- **核心(core)**:领域模型 + 用例函数 + 端口抽象。纯逻辑,不依赖任何外部技术。
- **适配器(adapters)**:每个"面"(CLI/API/MCP/UI),都是薄壳,只做翻译。
- **基础设施(infra)**:端口的具体实现(真实数据库、第三方平台客户端)。
- **组装根(composition)**:唯一一处把 infra 具体实现注入核心的地方。

---

## 三、铁律:依赖只能向内(最重要)

外层可以依赖内层;内层**永远不许**知道外层的存在。具体到 import:

- `core/` 下任何文件 **绝对禁止** `import` 任何 Web/CLI/数据库/HTTP 库
  (typer、fastapi、fastmcp、flask、sqlalchemy、requests……),
  也不许出现"命令行参数""HTTP 请求""像素/界面"等外层概念。
- `core/usecases.py` 只能 import `core/domain.py` 和 `core/ports.py`。
- 核心需要外部能力时,在 `core/ports.py` 用 `Protocol` 声明一个**抽象接口**,
  在 `infra/` 写具体实现,在 `composition.py` 注入。
- 只有 `composition.py` 和 `adapters/` 允许 import `infra/`。

> 这条规则是整套架构的灵魂。守住它,加任何新入口都不用动核心;违反它,逻辑就会散得到处都是。

---

## 四、目录结构

```
yourapp/
  core/                # 核心,纯逻辑。禁止 import 任何框架。
    domain.py          #   领域模型(dataclass)
    ports.py           #   抽象接口(Protocol):核心需要的外部能力
    usecases.py        #   用例函数:业务逻辑,核心对外的唯一 API
  infra/               # 端口的具体实现:数据库、第三方平台客户端...
  adapters/            # 各个"面",都很薄:
    cli.py             #   Typer
    api.py             #   FastAPI
    mcp_server.py      #   FastMCP
  composition.py       # 组装根:唯一一处挑选 infra 具体实现的地方
tests/                 # 用桩件直接测 core,不依赖框架/网络
```

---

## 五、每层怎么写(附最小示例)

下面用一个"发布一篇自媒体内容"的用例贯穿演示。

### 1. 领域模型 `core/domain.py` —— 只描述业务概念长什么样

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Post:
    account_id: str
    content: str

@dataclass(frozen=True)
class PublishResult:
    ok: bool
    post_id: str | None = None
    message: str = ""
```

### 2. 端口 `core/ports.py` —— 用 Protocol 声明"核心需要什么能力"

```python
from typing import Protocol
from .domain import Post, PublishResult

class Publisher(Protocol):
    """把一篇 Post 发布出去的能力。任何实现了这个方法的对象都算一个 Publisher。"""
    def publish(self, post: Post) -> PublishResult: ...
```

### 3. 用例 `core/usecases.py` —— 全部业务逻辑的唯一所在地

```python
from .domain import Post, PublishResult
from .ports import Publisher

def publish_post(publisher: Publisher, *, account_id: str, content: str) -> PublishResult:
    # 业务规则写在这里,只写一遍,所有入口共享。
    if not content.strip():
        return PublishResult(ok=False, message="content is empty")
    post = Post(account_id=account_id, content=content)
    return publisher.publish(post)
```

### 4. 基础设施 `infra/fake_publisher.py` —— 端口的具体实现(可替换)

```python
import uuid
from ..core.domain import Post, PublishResult

class FakePublisher:
    """桩件。以后接真实平台时,新增一个文件实现同一个端口即可,核心一行不用改。"""
    def publish(self, post: Post) -> PublishResult:
        post_id = uuid.uuid4().hex[:8]
        return PublishResult(ok=True, post_id=post_id, message="published")
```

### 5. 组装根 `composition.py` —— 唯一挑选具体实现的地方

```python
from .core.ports import Publisher
from .infra.fake_publisher import FakePublisher

def get_publisher() -> Publisher:
    # 想换真实平台?只改这一个函数。其它任何地方都不许 import infra/。
    return FakePublisher()
```

### 6. 三个面 `adapters/` —— 全是薄壳,调用同一个用例

CLI(Typer):

```python
import typer
from ..composition import get_publisher
from ..core.usecases import publish_post

app = typer.Typer()

@app.command()
def publish(account_id: str, content: str):
    result = publish_post(get_publisher(), account_id=account_id, content=content)
    typer.echo(result)
```

API(FastAPI):

```python
from fastapi import FastAPI
from pydantic import BaseModel
from ..composition import get_publisher
from ..core.usecases import publish_post

app = FastAPI()

class PublishRequest(BaseModel):
    account_id: str
    content: str

@app.post("/publish")
def publish(req: PublishRequest):
    return publish_post(get_publisher(), account_id=req.account_id, content=req.content)
```

MCP(FastMCP):

```python
from fastmcp import FastMCP
from ..composition import get_publisher
from ..core.usecases import publish_post

mcp = FastMCP("yourapp")

@mcp.tool
def publish(account_id: str, content: str) -> dict:
    """发布一篇内容到指定的自媒体账号。"""
    result = publish_post(get_publisher(), account_id=account_id, content=content)
    return result.__dict__
```

注意三个适配器调用的是**同一个** `publish_post`,各自只多了一层"翻译"。

---

## 六、加新东西时,放在哪里(决策指南)

- **新业务功能** → 在 `core/usecases.py` 加一个新函数,依赖通过参数传入。
- **新外部系统**(新平台、新存储)→ 在 `core/ports.py` 加抽象,在 `infra/` 加实现,
  在 `composition.py` 接线。**不改任何已有用例。**
- **新入口**(新的面)→ 在 `adapters/` 加一层薄壳,调用已有用例。**适配器里不写业务逻辑。**

---

## 七、MCP 工具:意图导向,不要 1:1 映射 CRUD

给 AI 用的 MCP 工具,要按"意图"暴露少量、语义清晰的工具(`publish_post`、`schedule_post`),
**不要**把所有 CRUD 端点自动全导出来。原因:工具一多(超过约 25–50 个),
LLM 会选错工具,且每个工具的 schema 都吃 token。

好消息是:只要核心暴露的是**意图形状的用例**,你的 MCP 工具天然就是意图导向的——
这正是本架构顺带解决的问题。

---

## 八、正确 vs 错误(照着写)

✅ 正确——适配器是薄壳,业务逻辑在核心:

```python
@app.post("/publish")
def publish(req: PublishRequest):
    return publish_post(get_publisher(), account_id=req.account_id, content=req.content)
```

❌ 错误——业务逻辑跑进了适配器(以后每个面都得重写一遍):

```python
@app.post("/publish")
def publish(req: PublishRequest):
    if not req.content.strip():     # ← 业务规则应在 core/usecases.py
        return {"error": "empty"}
    db.insert(...)                  # ← 适配器不许直连数据库
```

❌ 错误——核心 import 了框架:

```python
# core/usecases.py
import requests   # ← 绝对禁止。核心不许碰 HTTP / 框架 / 数据库
```

❌ 错误——UI 寄生在 CLI 上:

```python
# 不要这样。UI 后端应直接 import 同一个用例,而不是去调 CLI、解析它的文字输出。
output = subprocess.run(["yourapp", "publish", account_id, content], capture_output=True)
parse_text(output.stdout)
```

---

## 九、代码风格与测试约定

- 领域模型用 `@dataclass(frozen=True)`;用例函数用关键字参数(`*, account_id, content`)。
- 端口用 `typing.Protocol`,不用强行继承基类。
- 依赖通过参数显式传入(依赖注入),不用全局变量、不在用例里硬编码具体实现。
- **每个用例都要能用一个桩件(Stub)直接测,不碰网络/数据库:**

```python
class StubPublisher:
    def __init__(self): self.published = []
    def publish(self, post):
        self.published.append(post)
        return PublishResult(ok=True, post_id="test123")

def test_publish_post_success():
    pub = StubPublisher()
    result = publish_post(pub, account_id="acc1", content="hello")
    assert result.ok and pub.published[0].content == "hello"

def test_rejects_empty_content():
    pub = StubPublisher()
    assert not publish_post(pub, account_id="acc1", content="   ").ok
```

---

## 十、推荐技术栈(Python)

这三个库都吃 Python 类型注解 + Pydantic,所以核心用例的签名**一处定义、多个面共享**:

- **CLI**:Typer(基于 Click,类型注解定义命令)
- **API**:FastAPI + uvicorn
- **MCP**:FastMCP(`@mcp.tool` 装饰函数即成工具,schema 自动生成)
- **依赖注入**(项目变大后):dependency-injector / dishka
- **架构参考读物**:Architecture Patterns with Python(cosmicpython.com,免费在线)

> 换语言同理:TypeScript 用 NestJS(自带模块化 + 依赖注入);.NET 用 Ardalis CleanArchitecture;
> Java 用 Spring。原理不变,只换语言的壳。

---

## 十一、绝不要做(红线清单)

- ❌ 不要在 `core/` 里 import 任何框架、数据库或网络库。
- ❌ 不要在 `adapters/` 里写业务规则或直连数据库。
- ❌ 不要在 `composition.py` 以外的地方挑选 infra 的具体实现。
- ❌ 不要让 UI 去拼 CLI 命令、或爬 CLI 的文字输出——UI 后端直接 import 同一个用例。
- ❌ 不要把一堆 CRUD 端点 1:1 自动导出成 MCP 工具。
- ❌ 不要因为某个面方便,就把"只写一遍"的逻辑复制到多个面里。

---

## 一句话总纲

**数据是锚;核心是对数据做操作的用例,只写一遍;CLI/API/MCP/UI 都是它的薄适配器;
依赖只能向内;人提供判断,AI 提供执行,两者在同一份数据上协作。**
