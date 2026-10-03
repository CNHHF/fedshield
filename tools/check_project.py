# -*- coding: utf-8 -*-
"""FedShield 静态自检（仓库内工具，随代码一起分发）。

用法（在仓库根目录执行）：
    python tools/check_project.py all

检查项：Python 语法、Vue/JS 语法与模板配对、前后端接口契约双向比对、
        路由视图引用、@/ 别名导入、API 方法完备性。
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))          # fedshield/tools
PROJECT = os.path.dirname(ROOT)                             # fedshield（仓库根）
BACKEND = os.path.join(PROJECT, "backend")
FRONTEND = os.path.join(PROJECT, "frontend")
NODE = r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
             "source", "track", "wbr"}

errors: list[str] = []
warnings: list[str] = []


def rel(path: str) -> str:
    return os.path.relpath(path, PROJECT).replace("\\", "/")


def walk(folder: str, ext: str):
    for base, _dirs, files in os.walk(folder):
        if "node_modules" in base or "__pycache__" in base:
            continue
        for name in files:
            if name.endswith(ext):
                yield os.path.join(base, name)


# ---------------------------------------------------------------------------
def check_python() -> None:
    count = 0
    for path in list(walk(BACKEND, ".py")) + [os.path.join(PROJECT, "run.py")]:
        if not os.path.exists(path):
            continue
        count += 1
        try:
            with open(path, encoding="utf-8") as fp:
                ast.parse(fp.read(), filename=path)
        except SyntaxError as exc:
            errors.append(f"[python] {rel(path)}:{exc.lineno} {exc.msg}")
    print(f"  Python 语法：检查 {count} 个文件")


# ---------------------------------------------------------------------------
def extract_block(source: str, tag: str) -> str | None:
    """提取 SFC 块内容。

    注意：模板中可能包含 <template #default> 插槽，因此根模板必须用
    **贪婪** 匹配取到最后一个 </template>，否则会被插槽的结束标签截断。
    """
    pattern = rf"<{tag}[^>]*>(.*)</{tag}>" if tag == "template" else rf"<{tag}[^>]*>(.*?)</{tag}>"
    match = re.search(pattern, source, re.S)
    return match.group(1) if match else None


def check_template_tags(path: str, template: str) -> None:
    stack: list[str] = []
    for match in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)(/?)>", template):
        closing, tag, _attrs, self_closing = match.groups()
        tag = tag.lower()
        if tag in VOID_TAGS or self_closing:
            continue
        if closing:
            if not stack:
                errors.append(f"[template] {rel(path)} 多余的结束标签 </{tag}>")
                return
            if stack[-1] != tag:
                errors.append(f"[template] {rel(path)} 标签闭合错误：期望 </{stack[-1]}>，实际 </{tag}>")
                return
            stack.pop()
        else:
            stack.append(tag)
    if stack:
        errors.append(f"[template] {rel(path)} 未闭合标签：{stack}")


def check_vue() -> None:
    files = list(walk(os.path.join(FRONTEND, "src"), ".vue"))
    tmp_dir = os.path.join(ROOT, "_vuecheck")
    os.makedirs(tmp_dir, exist_ok=True)
    checked = 0
    for path in files:
        with open(path, encoding="utf-8") as fp:
            source = fp.read()

        template = extract_block(source, "template")
        if template is None:
            warnings.append(f"[template] {rel(path)} 未找到 <template>")
        else:
            check_template_tags(path, template)

        script = extract_block(source, "script setup") or extract_block(source, "script")
        if script is None:
            continue
        checked += 1
        tmp_file = os.path.join(tmp_dir, os.path.basename(path).replace(".vue", ".mjs"))
        with open(tmp_file, "w", encoding="utf-8") as fp:
            fp.write(script)
        result = subprocess.run([NODE, "--check", tmp_file], capture_output=True, text=True)
        if result.returncode != 0:
            brief = " | ".join((result.stderr or "").strip().splitlines()[:3])
            errors.append(f"[script] {rel(path)} 语法错误：{brief}")

    # 校验 api/index.js 与 utils 等纯 JS 文件
    for path in walk(os.path.join(FRONTEND, "src"), ".js"):
        with open(path, encoding="utf-8") as fp:
            content = fp.read()
        tmp_file = os.path.join(tmp_dir, os.path.basename(path) + ".mjs")
        with open(tmp_file, "w", encoding="utf-8") as fp:
            fp.write(content)
        result = subprocess.run([NODE, "--check", tmp_file], capture_output=True, text=True)
        if result.returncode != 0:
            brief = " | ".join((result.stderr or "").strip().splitlines()[:3])
            errors.append(f"[script] {rel(path)} 语法错误：{brief}")

    print(f"  Vue 文件：{len(files)} 个（{checked} 个含脚本块已用 node --check 校验）")


# ---------------------------------------------------------------------------
BACKEND_ROUTE_RE = re.compile(r"@bp\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']", re.S)
FRONTEND_CALL_RE = re.compile(r"request\.(get|post|put|delete)\(\s*(`[^`]*`|'[^']*'|\"[^\"]*\")")


def normalize(path: str) -> str:
    path = re.sub(r"\$\{[^}]+\}", "<var>", path)
    path = re.sub(r"<[a-zA-Z_][a-zA-Z0-9_]*>", "<var>", path)
    path = re.sub(r"<int:([a-zA-Z_][a-zA-Z0-9_]*)>", "<var>", path)
    path = re.sub(r"<[a-zA-Z]+:([a-zA-Z_][a-zA-Z0-9_]*)>", "<var>", path)
    return path.rstrip("/")


def check_api() -> None:
    api_file = os.path.join(FRONTEND, "src", "api", "index.js")
    with open(api_file, encoding="utf-8") as fp:
        api_source = fp.read()

    frontend_routes = set()
    for method, raw in FRONTEND_CALL_RE.findall(api_source):
        path = raw.strip("`'\"").split("?")[0]
        frontend_routes.add((method.upper(), normalize("/api" + path)))

    # 视图/组件中直接使用 request.<method>('/path') 的调用（跳过 @/api 封装层）
    direct_re = re.compile(r"request\.(get|post|put|delete)\(\s*(`[^`]*`|'[^']*'|\"[^\"]*\")")
    direct_count = 0
    for ext in (".vue", ".js"):
        for path in walk(os.path.join(FRONTEND, "src"), ext):
            if os.path.normpath(path) == os.path.normpath(api_file):
                continue
            with open(path, encoding="utf-8") as fp:
                source = fp.read()
            for method, raw in direct_re.findall(source):
                literal = raw.strip("`'\"")
                if not literal.startswith("/"):
                    continue  # 动态拼接的路径无法静态校验
                direct_count += 1
                frontend_routes.add((method.upper(), normalize("/api" + literal.split("?")[0])))

    backend_routes = set()
    for path in walk(os.path.join(BACKEND, "api"), ".py"):
        with open(path, encoding="utf-8") as fp:
            source = fp.read()
        prefix_match = re.search(r"url_prefix=[\"']([^\"']+)[\"']", source)
        prefix = prefix_match.group(1) if prefix_match else ""
        for verb, route in BACKEND_ROUTE_RE.findall(source):
            backend_routes.add((verb.upper(), normalize(prefix + route)))

    missing = sorted(frontend_routes - backend_routes)
    print(f"  前端接口调用 {len(frontend_routes)} 条（含视图直调 {direct_count} 条）/ 后端路由 {len(backend_routes)} 条")
    for method, path in missing:
        errors.append(f"[api] 前端调用未实现的后端接口：{method} {path}")
    if not missing:
        print("  -> 前后端接口全部匹配")

    unused = sorted(backend_routes - frontend_routes)
    if unused:
        print(f"  （后端有 {len(unused)} 条路由未被前端直接调用，属正常：导出/扩展接口）")


def check_api_methods() -> None:
    """检查视图中调用的 xxxApi.method(...) 是否都在 api/index.js 中定义。

    只检查「确实从 @/api 导入的对象」，避免把同名局部变量误判为 API 对象。
    """
    api_file = os.path.join(FRONTEND, "src", "api", "index.js")
    with open(api_file, encoding="utf-8") as fp:
        api_source = fp.read()

    defined: dict[str, set[str]] = {}
    for obj_name, body in re.findall(r"export const (\w+Api) = \{(.*?)\n\}", api_source, re.S):
        defined[obj_name] = set(re.findall(r"^\s*(\w+)\s*:", body, re.M))

    checked_objects = 0
    checked_methods = 0
    missing: list[str] = []
    for base, _dirs, files in os.walk(os.path.join(FRONTEND, "src")):
        for name in files:
            if not name.endswith((".vue", ".js")):
                continue
            path = os.path.join(base, name)
            if os.path.normpath(path) == os.path.normpath(api_file):
                continue
            with open(path, encoding="utf-8") as fp:
                source = fp.read()

            imported: set[str] = set()
            for names in re.findall(r"import\s*\{([^}]+)\}\s*from\s*['\"]@/api['\"]", source):
                imported.update(item.strip().split(" as ")[-1].strip() for item in names.split(",") if item.strip())
            if not imported:
                continue

            for obj_name, method in re.findall(r"\b(\w+)\s*\.\s*(\w+)\s*\(", source):
                if obj_name not in imported:
                    continue
                checked_methods += 1
                if obj_name not in defined or method not in defined[obj_name]:
                    missing.append(f"{rel(path)}: {obj_name}.{method}()")
            checked_objects += len(imported)

    print(f"  API 方法调用检查：覆盖 {checked_objects} 处导入、{checked_methods} 次方法调用")
    for item in sorted(set(missing)):
        errors.append(f"[api-method] 调用了未定义的接口方法：{item}")
    if not missing:
        print("  -> 全部接口方法均已定义")


def check_views() -> None:
    routes_file = os.path.join(FRONTEND, "src", "router", "routes.js")
    if not os.path.exists(routes_file):
        return
    with open(routes_file, encoding="utf-8") as fp:
        source = fp.read()
    imports = re.findall(r"import\(\s*['\"]@/([^'\"]+)['\"]\s*\)", source)
    missing = [
        item for item in imports
        if not os.path.exists(os.path.join(FRONTEND, "src", item.replace("/", os.sep)))
    ]
    print(f"  路由引用视图 {len(imports)} 个")
    for item in missing:
        errors.append(f"[view] 路由引用的视图不存在：src/{item}")


def check_imports() -> None:
    """检查前端 @/ 别名导入的文件是否真实存在。"""
    pattern = re.compile(r"from\s+['\"]@/([^'\"]+)['\"]")
    missing = set()
    for ext in (".vue", ".js"):
        for path in walk(os.path.join(FRONTEND, "src"), ext):
            with open(path, encoding="utf-8") as fp:
                source = fp.read()
            for target in pattern.findall(source):
                base = os.path.join(FRONTEND, "src", target.replace("/", os.sep))
                if os.path.exists(base) or os.path.exists(base + ".js") or os.path.exists(base + ".vue"):
                    continue
                missing.add(f"{rel(path)} -> @/{target}")
    print(f"  别名导入检查完成")
    for item in sorted(missing):
        errors.append(f"[import] 引用不存在的模块：{item}")


def main() -> int:
    scope = sys.argv[1] if len(sys.argv) > 1 else "all"
    print("FedShield 静态自检开始…")
    if scope in ("all", "backend"):
        check_python()
    if scope in ("all", "vue"):
        check_vue()
    if scope in ("all", "api"):
        check_api()
    if scope in ("all", "views"):
        check_views()
        check_imports()
        check_api_methods()

    print("\n===== 结果 =====")
    if warnings:
        print(f"警告 {len(warnings)} 条：")
        for item in warnings:
            print("  !", item)
    if errors:
        print(f"错误 {len(errors)} 条：")
        for item in errors:
            print("  x", item)
        return 1
    print("全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
