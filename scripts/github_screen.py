#!/usr/bin/env python3
"""第二阶段：只用 GitHub 搜索接口完成过滤和华人信号识别（本环境的单仓库/用户接口受限）。

输入：out/raw_repos.json（screen.py 的发现结果）
华人信号：
  A 仓库描述含中文
  B 账号所在地命中中国大陆/港澳台城市（search/users 批量 OR 查询）
  C 账号全名含常见拼音姓氏（search/users fullname 批量 OR 查询）
主要开发者：个人仓库默认 owner；组织仓库标记"待确认"，进入人工核实。
"""
import csv, json, re, subprocess, sys, time
from github_discover import is_non_innovative, is_big_org, CJK

OUT = "out"
LOCS = ("china beijing shanghai shenzhen hangzhou guangzhou chengdu nanjing wuhan "
        "hongkong taiwan taipei 中国 北京 上海 深圳 杭州").split()
SURN = ("wang li zhang liu chen yang huang zhao wu zhou xu sun ma zhu hu guo he lin gao luo "
        "zheng liang xie song tang han feng deng cao peng zeng xiao tian dong pan yuan cai jiang "
        "yu du ye cheng wei su lu ding ren shen yao jin fan fu zhong qian tan jia hou meng qin xiong "
        "bai qiu xue yan").split()

def search_users(q):
    for i in range(4):
        r = subprocess.run(["gh", "api", "-X", "GET", "search/users", "-f", f"q={q}",
                            "-f", "per_page=100"], capture_output=True, text=True)
        time.sleep(2.1)
        if r.returncode == 0:
            return {it["login"].lower() for it in json.loads(r.stdout)["items"]}
        if "rate limit" in (r.stderr + r.stdout).lower():
            time.sleep(60); continue
        print("[warn]", q[:80], r.stderr[:150], file=sys.stderr); return set()
    return set()

def batched_match(logins, terms, field, max_len=250):
    """把 user:a user:b ... 与 field:t1 field:t2 ... 组合进一条查询（两类条件各自 OR）。
    词表过长时分段，保证每条查询不超过 GitHub 的长度上限。"""
    hits = set()
    term_chunks, cur = [], []
    for t in terms:
        if len(" ".join(f"{field}:{x}" for x in cur + [t])) > 130:
            term_chunks.append(cur); cur = []
        cur.append(t)
    term_chunks.append(cur)
    for tc in term_chunks:
        tail = " ".join(f"{field}:{x}" for x in tc)
        batch = []
        for lg in logins + [None]:
            if lg is not None and len(" ".join(f"user:{x}" for x in batch + [lg])) + len(tail) + 1 <= max_len:
                batch.append(lg); continue
            if batch:
                hits |= search_users(" ".join(f"user:{x}" for x in batch) + " " + tail)
            batch = [lg] if lg else []
    return hits

def main():
    repos = json.load(open(f"{OUT}/raw_repos.json"))
    funnel = {"1_发现：2026-08-04后新建且≥1k stars": len(repos)}
    keep, dropped = [], []
    for r in repos:
        why = ("fork" if r.get("fork") else "归档" if r.get("archived") else
               "教程/资源汇总" if is_non_innovative(r) else "大厂/机构官方" if is_big_org(r) else None)
        (dropped if why else keep).append((r, why))
    funnel["2_过滤 fork/归档/教程汇总/大厂官方后"] = len(keep)

    owners = sorted({r["owner"]["login"] for r, _ in keep})
    print(f"查询 {len(owners)} 个账号的地点与姓名信号…", file=sys.stderr)
    loc_hit = batched_match(owners, LOCS, "location")
    name_hit = batched_match(owners, SURN, "fullname")

    rows = []
    for r, _ in keep:
        lg = r["owner"]["login"]
        sig = []
        if CJK.search(r.get("description") or ""): sig.append("中文描述")
        if lg.lower() in loc_hit: sig.append("所在地中国/港台")
        if lg.lower() in name_hit: sig.append("拼音姓氏")
        rows.append({
            "repo": r["full_name"], "url": r["html_url"], "stars": r["stargazers_count"],
            "created": r["created_at"][:10], "language": r.get("language"),
            "owner_type": r["owner"]["type"],
            "primary_dev_guess": lg if r["owner"]["type"] == "User" else "待确认(组织仓库)",
            "description": (r.get("description") or "")[:150],
            "topics": ",".join(r.get("topics") or []), "homepage": r.get("homepage") or "",
            "cn_signals": "|".join(sig), "cn_score": len(sig),
        })
    cn = [x for x in rows if x["cn_score"] > 0]
    funnel["3_有华人信号（≥1项）"] = len(cn)
    funnel["3a_强信号（≥2项）"] = sum(1 for x in cn if x["cn_score"] >= 2)
    funnel["3b_其中个人仓库"] = sum(1 for x in cn if x["owner_type"] == "User")

    cols = list(rows[0].keys())
    def dump(name, data):
        with open(f"{OUT}/{name}", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(data)
    dump("all_filtered.csv", sorted(rows, key=lambda x: -x["stars"]))
    dump("cn_candidates.csv", sorted(cn, key=lambda x: (-x["cn_score"], -x["stars"])))
    with open(f"{OUT}/dropped.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["repo", "stars", "reason", "description"])
        for r, why in dropped:
            w.writerow([r["full_name"], r["stargazers_count"], why, (r.get("description") or "")[:100]])
    json.dump(funnel, open(f"{OUT}/funnel.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps(funnel, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
