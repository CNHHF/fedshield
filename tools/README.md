# 仓库内工具脚本

本目录是随代码一起分发的验证与演示工具，均为相对路径实现，克隆到任何机器后
**在仓库根目录执行**即可（`fedshield/` 下）。

| 脚本 | 用途 | 命令 |
| --- | --- | --- |
| `check_project.py` | 静态自检：Python 语法、Vue/JS 语法与模板配对、前后端接口契约双向比对、路由视图引用、`@/` 别名导入、API 方法完备性 | `python tools/check_project.py all` |
| `e2e_backend.py` | 端到端接口验证：113 项检查，覆盖登录鉴权、任务全生命周期、三大业务场景、合规、授权、预算、血缘、存证、AI 风控大脑与赛题五大建设范围、权限边界 | `python tools/e2e_backend.py` |
| `prepare_demo.py` | 准备演示数据：重置演示库 → 联邦建模 → 异常检测 → 支付处理（含故障演练）→ 审核批次，用于演示与录制视频 | `python tools/prepare_demo.py` |

## 说明

- `e2e_backend.py` 使用独立的临时数据库（`instance/e2e_temp.db`），可重复执行，不会污染演示数据库；
- `check_project.py` 只做静态分析，不导入后端代码，因此不需要安装依赖；
- `e2e_backend.py` 与 `prepare_demo.py` 需要先安装后端依赖（见根目录 `README.md`）；
- 演示账号与口令见根目录 `README.md` 的「快速开始」章节。
