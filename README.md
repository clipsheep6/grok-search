# Grok Search

通过 `grok2api` 反向代理执行并发、共识排名的网页搜索（行为等同于 Grok 网页对话，**非**官方 xAI API）。
使用方法见 [SKILL.md](./SKILL.md)；配置/参数/错误码见 [references/api_reference.md](./references/api_reference.md)。

---

## 检索策略

### 为什么要并发？

单次查询本身已经触发真实的多源 web/X 检索（可能阅读数百页）。脚本不重新实现检索，只补充上层不会自动做的事：

- **并发扇出**：同一查询同时发送给多个异构模型（默认 2 路），耗时 ≈ 最慢单次，几乎没有额外等待。
- **共识排名**：合并各路结果的来源，按被引用次数（`×N`）排序。`×N` 是跨运行显著性信号，不是权威性或正确性证明。
- **压缩输出**：结论前置，来源列表完整保留（非对称截断：裁散文、不裁来源）。
- **信号层**：可选 URL 校验 + 共识/分歧信号，把“像真的来源”与“已确认来源”分开。

### 扇出模式

| 模式 | 运行数 | 适用场景 |
|------|--------|----------|
| 默认（2 路） | 同一查询 × 2 异构模型 | 大多数查询 |
| `--deep` | 3 路 + 广度提示 | 需要更多来源面；经验值：可见来源 ~14 → ~68 |
| `--angle "A" --angle "B"` | 每个角度一路 | 明确需要多视角对比 |

`concurrency` 现在可以通过 CLI 或 `config.json` 配置，不再只能吃脚本内置默认值。  
当有效并发数大于 `2` 时，脚本会默认做 `stagger_ms=1000` 的错峰发起，避免把 4-5 个请求同时砸到反向代理上；如果你确信代理扛得住，可以显式设成 `0`。

### 共识信号怎么读

输出中每条来源行末尾的 `×N` = 被 N 路运行同时引用，是“值得先检查”的注意力信号。

- `×2`（默认 2 路全部引用）→ 高显著性，适合优先检查
- `×1` → 仅单路引用，不代表低质量，可能正是一手源
- `M/N runs` 标注 → 部分成功，答案有效但覆盖面变窄；如果结果关键，重跑

真正排序时，仍应优先 **一手 / 权威 / 新鲜** 来源，而不是机械追高 `×N`。

脚本还会输出一行 `signal` 概览：

- `consensus: high` → 重叠强，适合尽快切到 direct fetch/read
- `consensus: mixed` → 有重叠也有分歧，先补一手源
- `consensus: low` → 低重叠，视为 unresolved / fast-moving 区域

如果开启 `--verify-urls`，最终打印的来源还会被标成：

- `live` → URL 成功解析
- `dead` → 明确失效
- `unverified` → 在当前预算内未确认，既不要盲信，也不要直接丢弃

`--deadline N` 是整次搜索共享的挂钟预算，覆盖 fanout、降级重试和 URL
校验。它的意义是防止一次检索无限拖长；预算耗尽时，脚本会丢弃未完成
run 或跳过后续校验，但它不是对底层网络请求的强制进程级 kill。

### 查询构造建议

**时效性**
- 近期范围用 `--days N`（相对天数），例如 `--days 7`
- 特定日期写进查询文本本身，例如 `"截至2025年Q4的数据"`——`--days` 无法精确到固定日期

**来源偏好**
- `--focus "<文本>"` 是软提示，非硬过滤，例如 `--focus "官方文档和 GitHub issues"`
- 偏好某平台时也可直接在查询里注明，例如 `"...，来自 Reddit 的讨论"`

**输出形态**
- 需要给人快速阅读：默认 markdown
- 需要交给下游 agent / 脚本继续处理：优先 `--json`
- 需要对外引用 URL：优先 `--verify-urls`
- `--json` 在 angle / preset 模式会带 `planned_angles`，记录实际展开的角度、是否包含 base query、preset 名称和 `angle_fanout`，便于复盘和 A/B 对比

### Search Tactics

下面这些是高频且值得保留的组合套路。它们不是“研究协议”，而是实际搜索时最常用的战术。

- **异构双模型并发（默认）**：一快一广。适合大多数查询，既保速度也保 source overlap。
- **三路 deep fanout**：用于 landscape scan 或 branch drill。目标是拉宽 source pool，而不是更快出一个答案。
- **direct-comparison 角度**：比较类查询必须保留一个正面对比 angle，不能只拆成 `A` 和 `B` 各自描述。
- **broad → drill**：先宽扫，再对 2-4 个分支各自深钻。不要一开始就把整个问题压成一个过深查询。
- **discovery 多轮调用**：找方向时，优先多次调用 `grok_search.py`，每次只跑 1-2 个角度，而不是一次塞满所有轴。
- **recent + official focus**：查时效问题时用 `--days N`；查规范、API、政策时可加 `--focus "official docs"`。
- **primary-source stop rule**：一旦已经拿到 authoritative URL，就停止继续搜索，改为 direct fetch/read。
- **controversy split**：遇到低重叠或相互冲突的来源，不要强行合并成一个整齐答案；把分歧当成继续拆分的信号。

### 多角度检索：什么时候真该拆

`--angle` 不是“多写几个同义句”，而是把问题拆成不同证据路径。最有效的几类：

- **正面对比 + 各自短板**：适合选型题。至少保留一个 `A vs B` 正面对比角度，再加 `A limits`、`B limits`。
- **时间线拆分**：适合最近变化。把 `announcement`、`migration/breaking changes`、`community incidents` 分开。
- **利益相关方拆分**：适合不同群体会给出不同答案的问题，比如 vendor / operator / regulator。
- **机制拆分**：适合“为什么会这样”，拆成 `mechanism`、`counterexample`、`boundary conditions`。
- **争议拆分**：适合极化问题，拆成 `best supporting evidence`、`best critique`、`primary sources actually show`。

经验上，**3 个 angle 通常最合适**。超过 3 个之前，先怀疑是不是基准 query 写得太宽，而不是问题真的需要 6 个方向。

如果你只是做 discovery，通常不需要额外的 base query；可以直接加 `--no-base-query`，让一次 angle sweep 只跑显式角度本身。

两个常见反例：

- **不要把比较题只拆成 `A` 和 `B`**：这样很容易失去 head-to-head 证据，最后只得到两组各自宣传的材料。
- **不要拿到 primary URL 后继续反复 re-search**：后续搜索往往只会带来更多二手转述，不会比直接读一手源更强。

### Common Combinations

- **官方事实核查**：默认 fanout + `--verify-urls` + `--focus "official docs"`
- **最近变化 / 发布信息**：默认 fanout + `--days 7` 或 `--days 30`
- **对比选型**：默认 fanout + direct-comparison angle + optional limitations angles
- **陌生领域摸底**：`--deep`
- **先全景后深挖**：第一次 `--deep`，后续对单分支再 `--deep`
- **争议问题**：多 angle + `--verify-urls` + 看 `consensus/divergence`

### 全覆盖深度技术洞察协议

当你的目标是“对某个技术做完整判断”，而不是回答一个狭窄问题时，最合适的不是单次 `--deep`，而是把同一主题沿 **4 条证据轴** 并行拉开：

- **学术轴**：论文、benchmark、survey、arXiv、论文关联 repo
- **工业轴**：官方文档、发布说明、工程博客、案例、postmortem
- **社交信号轴**：X.com、Hacker News、Reddit、开发者讨论
- **采用现实轴**：不是只看外围热度，而是下钻到最具体的落地内容和技术方案本体：GitHub issue/PR、RFC/design doc、集成代码、迁移文档、example app、配置说明、事故复盘、operator writeup、部署笔记、benchmark 复现 repo

这不是 4 个子任务，而是 **一个统一的技术研究协议**。社交轴负责发现新信号和摩擦点，不负责单独下结论；真正的结论要看它能否被学术轴、工业轴、采用轴交叉支撑。这里的“采用轴”也不是看 stars、名单、宣传页，而是看最具体的落地证据、技术方案取舍和运维摩擦。

推荐命令模板：

```bash
python3 scripts/grok_search.py "dynamic workflow for AI agents in 2026" \
  --angle "dynamic workflow for AI agents academic papers benchmarks surveys and research repos in 2026" \
  --angle "dynamic workflow for AI agents official docs product announcements engineering blogs and postmortems in 2026" \
  --angle "dynamic workflow for AI agents X.com Hacker News Reddit discussions praise criticism and notable links in 2026" \
  --angle "dynamic workflow for AI agents GitHub issues PRs RFCs design docs integration code migration guides example apps deployment notes operator writeups and incident reports in 2026" \
  --verify-urls --json
```

最后不要按“论文说了什么 / X 上说了什么”来归并，而要按这些判断维度归并：

- `capability`
- `reliability`
- `operability`
- `cost`
- `ecosystem / adoption`
- `failure modes`
- `open questions`

这套协议最后通常服务两种终点：

- **深度报告型**：追求详实、专业、证据链完整，保留分歧、反例、限制条件
- **实操指导型**：追求指导技术演进，最后要收束成 `现在该做什么 / 先试什么 / 暂缓什么 / 需要哪些前提`

### Task → Protocol

- **官方事实核查**：先拿官方 URL，再停搜，直接读一手源。
- **最近变化**：先用 `--days N` 控时窗；如果结果太糊，再加时间线 angle，而不是直接上更多 fanout。
- **对比选型**：必须保留一个 head-to-head angle；只拆 `A` 和 `B` 往往会丢失真正的 benchmark。
- **陌生领域摸底**：先做宽扫，拿到 2-4 个 branch 之后再 deep；不要一开始就把整个领域压成一个超深问题。
- **争议问题**：让支持证据、反对证据、primary reality 分开跑；如果最后 `consensus: low`，这不是失败，而是提醒你别过早下结论。
- **根因 / 机制问题**：优先拆 `mechanism / counterexample / boundary`，而不是拆成多个近义问法。

### 多角度检索的停止规则

- 如果多个 angle 最终还是落回同一批域名、同一批 claims，说明你拆的不是角度，只是措辞变化，应该收缩 query。
- 如果 angle 模式出来几乎全是 `×1`，且没有稳定 primary source，不要继续加角度；先缩窄范围。
- 如果已经拿到 authoritative URL，继续多角度搜索的边际收益通常很低，改成 direct fetch/read。
- 如果社交轴上的热门说法无法被论文 / 官方 / GitHub 现实交叉支撑，只能保留为“信号”，不能直接当结论。
- 如果论文很热、工业宣传很强，但 adoption 轴证据很弱，应把它标成 frontier / emerging，而不是 production-proven。
- 如果官方叙事很强，但 issue / PR / RFC / design doc / integration code / migration / operator 证据显示真实方案与宣传差异很大，优先相信“已落地方案与摩擦”而不是 marketing 叙事。

**多步研究循环**（脚本是单次原语，编排由你来做）
1. **宽泛查询** → 读答案 + 来源 → 识别 2-4 个分支/争议点
2. **分支深钻** → 每个分支 `--deep`（可并行子调用）
3. **交叉验证** → 优先一手 / 权威 / 新鲜来源；把高 `×N` 当作注意力提示；来源间存在分歧 = 问题尚未有定论

### 最终收束：报告型 vs 实操型

- **报告型**：保留更宽的证据面、显式写出冲突证据、给出不确定性和开放问题
- **实操型**：把证据压缩成决策动作，例如 `adopt / pilot / defer / avoid / monitor`
- 如果某条证据不会改变技术路线，只会增加“背景知识”，那它更适合报告型，不适合实操型结论

### 开销取舍

真正需要权衡的成本有两项：

1. **挂钟时间** → 并发解决，扇出 2-3 路不增加实际等待（≈ 最慢单次）。
2. **返回给调用方的 payload** → 压缩散文、保护来源列表；`max_tokens` 是截断保护，不是调优旋钮。

### 模型梯队

- 快速模型（`grok-4.3-*`）：~8-13 s，适合大多数查询
- 多智能体模型：深度和广度更强，`--deep` 时发挥最大价值
- 默认配对一快一广，可在 `config.json` 调整

---

## 校验

```bash
python3 -m py_compile scripts/grok_search.py
python3 scripts/grok_search.py --help
```
