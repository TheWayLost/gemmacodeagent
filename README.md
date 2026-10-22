# Budget-Fit v5 + thinking_budget 6000

Current submission: [artifacts/submission.zip](artifacts/submission.zip), v5 +6000 thinking,56 tool calls,15 minutes,160 turns. Budget text matches runtime configuration. Historical8min package: [artifacts/submission_legacy_8min.zip](artifacts/submission_legacy_8min.zip). This updated package has CPU contract checks, not a new Kaggle score.

Training update: [deployment-prefix alignment guide](training/weighted_reasoning_lora/PREFIX_ALIGNMENT.md). Rebuild token caches before training.

**八路是外部评测调度，不打进 submission，也不能强制 Kaggle 评分器八路运行。** 每台 PRO 6000 独立加载模型、本地推理，无跨机器 SSH 推理隧道。

## 必须先在目标 48GB RTX 4090 上运行 GPU 容量验收

完成环境安装和模型下载后，先停止该卡上自己的 GPU 任务，再运行：

```bash
envs/eval/bin/python scripts/check_4090_capacity.py
# 长时间运行也可以保留终端自动汇报：
# envs/eval/bin/python -u scripts/check_4090_capacity.py 2>&1 | tee logs/4090-capacity.log
```

脚本要求实际48GB RTX4090，拒绝24GB卡、其他型号及已有明显显存占用的设备。测试服务默认使用8124端口；不会接管8000上的现有服务，也不会终止别人的GPU进程。需要单独指定设备时加 --gpu 0 或 GPU UUID。

它依次启动1、2、3、4路配置，每档三轮，每个请求30,000输入tokens+2,048输出tokens，固定32k上下文。关闭prefix缓存并使用不同输入，防止共享KV缓存夸大容量；同时检查实际running请求数、完整生成、显存峰值、KV抢占、HTTP错误和OOM等启动/运行失败。某档失败后停止更高档测试。测试仅创建自己的独立服务和日志，结束后关闭自己启动的服务。

**终端会自动打印每档PASS/FAIL，以及最高通过并发、实测吞吐最优的推荐并发和完整启动命令。** 结果保存在 runs/4090-capacity-时间戳/report.json 与 RECOMMENDATION.txt。无档位通过时明确提示不要启动评测。全套需处理最多61,440输出tokens并加载四次模型，可能需要数十分钟或更久；实际时间取决于该卡和磁盘。

不需要下载不同的代码包：同一仓库和同一个 artifacts/submission.zip，使用报告推荐的 CONCURRENCY=1、2、3或4。例如报告推荐三路：

```bash
CONCURRENCY=3 bash scripts/run_4090_48g.sh model
# 等待8000健康检查通过后，先做单题gold/empty/agent验证：
CONCURRENCY=3 bash scripts/run_4090_48g.sh eval --cohort paired20 --shards 1 --shard 0 --ids requests_6644 --arms v5_6000 --run 4090-smoke-c3
# 单题环境验证通过后，再跑20题：
CONCURRENCY=3 bash scripts/run_4090_48g.sh eval --cohort paired20 --shards 1 --shard 0 --arms v5_6000 --run 4090-20-c3
```

先按原说明准备 paired20 数据。推荐仅适用于该次软件配置与测试负载，不是对所有未来任务的稳定性保证。脚本的长上下文测试不替代完整agent工具调用验收；它也不是4090已经测得能跑四路的声明。

可选的纯CPU调度器自检：python3 scripts/check_concurrency.py（覆盖1/2/3/4/8路、容量冲突和异常退出恢复）。CPU门控自检不能用于推断GPU容量。--dry-run只打印GPU测试计划，不启动服务，也不产生容量认证。

## 三台 PRO 6000，各八路

 Linux x86_64、RTX PRO 6000 Blackwell 96GB、root、CUDA 12.8 兼容驱动、Python 3.12、git、chroot、setpriv。建议 22 CPU、110GB RAM、150GB 可用数据盘。模型约 23.3GB，安装缓存和沙箱需要额外空间。所有文件放数据盘。


```bash
cd /root/autodl-tmp
git clone https://github.com/TheWayLost/gemmacodeagent.git
cd gemmacodeagent
export HF_HOME="$PWD/cache/huggingface" XDG_CACHE_HOME="$PWD/cache" TMPDIR="$PWD/tmp"
mkdir -p "$HF_HOME" "$TMPDIR" logs runs
bash scripts/setup.sh
```

setup 下载官方 wheelhouse v31，安装版本锁，并校验六个核心包源码是否与实验一致。不能替换成 PyPI 同版本 vLLM；官方 wheel 有补丁。hash 不一致须停止，不混合结果。完整新机安装尚未在另一台空白机器验收；现有机器验收记录见 reports。

 Python 3.13 沙箱及各题离线 wheels 由 Release `calibration-v1.tar.gz` 提供，setup 自动下载、校验 SHA256、解压。附件不含模型、任务快照或令牌，保留第三方 metadata/license。AutoDL chroot 不等同完整 Docker 隔离，尤其没有宿主网络隔离；仅在可信独立评测机器运行。


```bash
read -rsp 'Kaggle API token: ' KAGGLE_API_TOKEN; echo
export KAGGLE_API_TOKEN
# 若 HF 模型下载需要鉴权，从环境设置 HF_TOKEN。
envs/eval/bin/python scripts/download_model.py
```

'MD' HF revision `52f3f65bc7a02d555763bc923bd1d9094898219d`，脚本核对完整权重 SHA256。可在下载前设置 `HF_ENDPOINT=https://hf-mirror.com`；仍须通过相同校验，不保证各机房镜像更快。

> 0/1/2 设置 SHARD=0/1/2：

```bash
SHARD=0  # 第二台改 1，第三台改 2
envs/bootstrap/bin/python scripts/prepare_data.py --cohort valid55 --shards 3 --shard "$SHARD"
envs/eval/bin/python src/start_model_capacity.py
# 等待模型健康检查成功，再启动 benchmark：
# curl http://127.0.0.1:8000/v1/models
nohup env ADP_CONCURRENCY=8 envs/eval/bin/python src/benchmark.py \
  --cohort valid55 --shards 3 --shard "$SHARD" --workers 8 \
  --arms v5_6000 --run v5-6000-55 > logs/benchmark.log 2>&1 < /dev/null &
tail -f logs/benchmark.log
```

55 题分为 19/18/18。四台时所有命令统一 `--shards 4`，分别 `--shard 0,1,2,3`，分为 14/14/14/13。不能混用 shards 或重复 shard。每机只 vLLM 服务。

20 题比较两个历史配置（当前 v5_6000 为56次/15分钟，v5_4096 为28次/8分钟；不是仅 thinking budget 不同的对照）：

```bash
envs/bootstrap/bin/python scripts/prepare_data.py --cohort paired20 --shards 3 --shard "$SHARD"
nohup env ADP_CONCURRENCY=8 envs/eval/bin/python src/benchmark.py \
  --cohort paired20 --shards 3 --shard "$SHARD" --workers 8 \
  --arms v5_4096 v5_6000 --run paired20-repeat > logs/paired20.log 2>&1 < /dev/null &
```

 `--dry-run` 可检查分片。另一个可选 arm `original_baseline` 是此前 Kaggle 0.13 提交，不是 v5。

## 调度、恢复与合并

- ThreadPool + FIRST_COMPLETED 滚动补位，完成一个立即补一个，末尾不足八题自然无法填满。
- 主机级 flock 八槽限制多个调度器总并发。默认 `/root/autodl-tmp/gemma-eval-slots`；修改 GEMMA_SLOT_DIR 时同机进程须一致。锁由内核释放，避免陈旧 PID。排队发生 agent 限时之前。
- 每个 job 独立 chroot、日志、临时缓存，避免官方固定 sp_base.tar 并发覆盖。
- 原命令可断点续跑；代码、任务、submission 改变会拒绝混合旧结果，应换新 --run。基础设施错误可修复后续跑；算法 是结果， timeout
- 状态：`runs/<run>-shardN/state.json`。逐题目录含 task_results.jsonl、manifest、worker.log、llm_requests.jsonl。日志含完整交互，应作为实验数据保管。
- 运行中不要修改代码或配置；重启后恢复本地模型服务再执行同一命令。

'MD' `runs/v5-6000-55-shardN` 目录汇集到一台的 collected/ 后：

```bash
envs/eval/bin/python src/merge_results.py collected/v5-6000-55-shard{0,1,2}
```

#
.bashrc .cache .conda .condarc .config .ipython .jupyter .local .nv .profile .ssh .triton autodl-pub autodl-tmp miniconda3 tf-/中位耗时、排序后的逐题时间；双方案输出配对胜负。效率应同时看完成题数/墙钟小时、agent 耗时、tokens/s；八路不等于八倍速度。

## 实验定义与证据

|设置|值|
|---|---|
|模型|gemma-4-31b-it-qat-w4a16-ct，无微调|
|temperature / top_p|0.2 / 0.95|
|max_output_tokens|8192，含 reasoning 与正文|
|thinking_budget|6000，对照4096|
|agent预算|8分钟、28 tool calls、80 turns|
|命令 / 最终验证限时|240s / 300s|
|上下文 / compact|32768 / threshold14336、interval15、overlap2、retention5|

8分钟来自所采用的 submission 配置。task wall_seconds 包括最终验证，可能超过8分钟。

|本地同轮20题|成功|平均任务耗时|agent timeout|
|---|---:|---:|---:|
|v5 4096|10/20|290.9s|4|
|v5 6000|12/20|275.3s|1|

6000 两胜零负，exact McNemar p=0.5，尚不足证明稳定提升。早一轮4096在同20题是13/20，说明跨轮变动不可忽略。

55题 v5 **4096** 为28/55，原基线26/55，不能当作6000的55题成绩。v5采用旧24+新31并集，并非同轮跑完。rich_3468 因 gold/empty 均通过排除。统计与时间分布图见 [reports](reports/)。旧 Kaggle 0.13 属于原基线；不宣称6000有已知 Kaggle 分数。

PRO 6000 TP1+chroot 与官方4×L4+Docker的时延、隔离不完全一致。冻结环境没有接入 graph/embedding 数据，prompt 也要求不用这些工具；接入须另立实验条件。

## 来源与提交

- [Budget-Fit v5 notebook](https://www.kaggle.com/code/verracodeguacas/gemma-4-agent-budget-fit-single-agent)：Wilmer E. Henao 原提示词。6000只改一个预算值。
- [比赛数据与 HARNESS_README](https://www.kaggle.com/competitions/gemma-4-developer-agent/data)。任务和模型不上传 Git；从授权来源下载，遵守规则与许可。
- [官方 wheelhouse](https://www.kaggle.com/datasets/metric/gemma-4-developer-agent-wheelhouse)。保留版本和源码 hash，避免同版本补丁差异。

Kaggle 应上传 artifacts/submission.zip，保持文件名 submission.zip；不要提交整个仓库或校准环境。本次发布不消耗新的 Kaggle 提交次数。

## 单卡 48GB RTX 4090

见 [4090 48GB 部署说明](docs/4090-48gb.md)：默认单路，可试两路，保留32k上下文与同一 submission。尚未完成目标硬件验收。
