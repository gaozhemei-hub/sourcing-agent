#!/usr/bin/env python3
"""GitHub 初筛：近三个月新建、1k+ Stars、主要开发者疑似华人的创新型项目。

漏斗：发现 → 过滤（fork/归档/教程汇总/大厂官方）→ 定位主要开发者 → 华人信号打分 → 输出待人工核实名单。
依赖：已登录的 gh CLI（gh api 会自动带上凭证）。
用法：python3 screen.py --since 2026-08-04 --min-stars 1000 --out out/
"""
import argparse, csv, json, os, re, subprocess, sys, time
from datetime import date, timedelta

# ---------- GitHub 调用 ----------
def gh(path, params=None, retries=3):
    args = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if params:
        args = ["gh", "api", "-X", "GET", "-H", "Accept: application/vnd.github+json", path]
        for k, v in params.items():
            args += ["-f", f"{k}={v}"]
    for i in range(retries):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout) if r.stdout.strip() else None
        msg = r.stderr + r.stdout
        if "rate limit" in msg.lower() or "403" in msg:
            time.sleep(30 * (i + 1)); continue
        if "404" in msg:
            return None
        time.sleep(3)
    print(f"[warn] 调用失败 {path}: {msg[:200]}", file=sys.stderr)
    return None

# ---------- 1. 发现 ----------
def discover(since, until, min_stars):
    """GitHub 搜索单次最多返回 1000 条，按 7 天切片创建日期以覆盖全部。"""
    repos, d = {}, since
    while d <= until:
        end = min(d + timedelta(days=6), until)
        q = f"created:{d.isoformat()}..{end.isoformat()} stars:>={min_stars}"
        for page in range(1, 11):
            res = gh("search/repositories", {"q": q, "sort": "stars", "order": "desc",
                                              "per_page": "100", "page": str(page)})
            time.sleep(2.2)  # 搜索接口 30 次/分钟
            items = (res or {}).get("items", [])
            for it in items:
                repos[it["full_name"]] = it
            if len(items) < 100:
                break
        d = end + timedelta(days=1)
    return list(repos.values())

# ---------- 2. 过滤 ----------
NON_INNOVATIVE = re.compile(
    r"(awesome|tutorial|course|roadmap|interview|cheat-?sheet|curated|collection|"
    r"resources?|learn(ing)?-|guide|handbook|book|notes|list of|prompts?|"
    r"教程|资源|合集|汇总|面试|学习路线|笔记|指南|大全)", re.I)
BIG_ORGS = {o.lower() for o in """
openai anthropics google google-deepmind google-research microsoft facebookresearch meta-llama
nvidia NVlabs huggingface apple amazon aws awslabs alibaba QwenLM AlibabaResearch modelscope
deepseek-ai bytedance volcengine ByteDance-Seed tencent Tencent-Hunyuan TencentARC baidu PaddlePaddle
THUDM zai-org moonshotai MoonshotAI MiniMax-AI Kwai KwaiVGI XiaomiMiMo xai-org mistralai
stepfun-ai OpenGVLab InternLM shanghai-ai-lab netease-youdao ant-research antgroup inclusionAI
salesforce ibm intel ollama vercel cloudflare github
""".split()}

def is_non_innovative(r):
    text = " ".join([r["name"], r.get("description") or "", " ".join(r.get("topics") or [])])
    return bool(NON_INNOVATIVE.search(text))

def is_big_org(r):
    o = r["owner"]
    return o["login"].lower() in BIG_ORGS

# ---------- 3. 定位主要开发者 ----------
def primary_dev(full_name):
    cs = gh(f"repos/{full_name}/contributors", {"per_page": "30"}) or []
    cs = [c for c in cs if c.get("type") == "User" and not c["login"].endswith("[bot]")]
    if not cs:
        return None, 0.0
    total = sum(c["contributions"] for c in cs)
    top = cs[0]
    return top["login"], round(top["contributions"] / total, 2) if total else 0.0

# ---------- 4. 华人信号 ----------
CJK = re.compile(r"[一-鿿]")
SURNAMES = set("""wang li zhang liu chen yang huang zhao wu zhou xu sun ma zhu hu guo he lin gao luo
zheng liang xie song tang han feng deng cao peng zeng xiao tian dong pan yuan cai jiang yu du ye cheng
wei su lv lu ding ren shen yao jin fan fu zhong qian tan jia hou meng qin xiong bai qiu xue yan""".split())
PLACES = re.compile(r"(china|beijing|shanghai|shenzhen|hangzhou|guangzhou|nanjing|wuhan|chengdu|xi'?an|"
                    r"suzhou|hefei|hong ?kong|taiwan|taipei|hsinchu|macau|中国|北京|上海|深圳|杭州|广州|香港|台湾|台北)", re.I)
ORGS_CN = re.compile(r"(tsinghua|peking|pku|zju|zhejiang|sjtu|fudan|ustc|nju|hust|whu|sysu|cuhk|hkust|hku|ntu|nus|"
                     r"alibaba|tencent|bytedance|baidu|meituan|jd\.com|huawei|xiaomi|清华|北大|浙大|交大|复旦|中科大|中科院)", re.I)

def chinese_signals(user):
    sig = []
    name = user.get("name") or ""
    if CJK.search(name): sig.append("中文名")
    parts = re.split(r"[\s\-_.]+", name.lower())
    if any(p in SURNAMES for p in parts): sig.append("拼音姓氏")
    if PLACES.search(user.get("location") or ""): sig.append("地点")
    if CJK.search(user.get("bio") or ""): sig.append("中文简介")
    if ORGS_CN.search((user.get("company") or "") + " " + (user.get("bio") or "")): sig.append("机构")
    if (user.get("blog") or "").endswith(".cn") or ".edu.cn" in (user.get("email") or ""): sig.append(".cn域名")
    return sig

# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=(date.today() - timedelta(days=92)).isoformat())
    ap.add_argument("--until", default=date.today().isoformat())
    ap.add_argument("--min-stars", type=int, default=1000)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    since, until = date.fromisoformat(a.since), date.fromisoformat(a.until)

    funnel = {}
    repos = discover(since, until, a.min_stars)
    funnel["1_发现（新建且达标）"] = len(repos)
    json.dump(repos, open(f"{a.out}/raw_repos.json", "w"), ensure_ascii=False)

    dropped = []
    keep = []
    for r in repos:
        why = ("fork" if r.get("fork") else "归档" if r.get("archived") else
               "教程/汇总" if is_non_innovative(r) else "大厂官方" if is_big_org(r) else None)
        (dropped if why else keep).append((r, why))
    funnel["2_过滤后"] = len(keep)

    from concurrent.futures import ThreadPoolExecutor
    def enrich(r):
        login, share = primary_dev(r["full_name"])
        if not login:
            return None
        u = gh(f"users/{login}") or {}
        return r, login, share, u
    with ThreadPoolExecutor(8) as ex:
        enriched = [e for e in ex.map(enrich, [r for r, _ in keep]) if e]

    rows = []
    for r, login, share, u in enriched:
        sig = chinese_signals(u)
        rows.append({
            "repo": r["full_name"], "url": r["html_url"], "stars": r["stargazers_count"],
            "created": r["created_at"][:10], "lang": r.get("language"),
            "desc": (r.get("description") or "")[:120], "owner_type": r["owner"]["type"],
            "primary_dev": login, "commit_share": share, "dev_name": u.get("name"),
            "location": u.get("location"), "company": u.get("company"), "blog": u.get("blog"),
            "twitter": u.get("twitter_username"), "bio": (u.get("bio") or "")[:120],
            "cn_signals": "|".join(sig), "cn_score": len(sig),
            "birth_year": "", "age_evidence": "", "evidence_level": "",  # 人工核实列
        })
    funnel["3_识别出主要开发者"] = len(rows)
    cn = [x for x in rows if x["cn_score"] > 0]
    funnel["4_有华人信号"] = len(cn)
    funnel["4a_强信号(≥2项)"] = sum(1 for x in cn if x["cn_score"] >= 2)

    cols = list(rows[0].keys()) if rows else []
    for name, data in [("all_candidates.csv", rows),
                       ("cn_candidates.csv", sorted(cn, key=lambda x: (-x["cn_score"], -x["stars"])))]:
        with open(f"{a.out}/{name}", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(data)
    with open(f"{a.out}/dropped.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["repo", "stars", "reason", "desc"])
        for r, why in dropped:
            w.writerow([r["full_name"], r["stargazers_count"], why, (r.get("description") or "")[:100]])
    json.dump(funnel, open(f"{a.out}/funnel.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps(funnel, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
