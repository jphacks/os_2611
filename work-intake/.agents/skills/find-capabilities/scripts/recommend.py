#!/usr/bin/env python3
"""Read-only task-fit selection. Host supplies semantic judgments and observations."""
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("capability_catalog", Path(__file__).with_name("catalog.py"))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
Error = catalog.Error
require, text, strings = catalog.require, catalog.research.text, catalog.strings
MATCH = {"direct": 0, "partial": 1, "adjacent": 2, "none": 3}
CHECK_LABELS = {
    "ja": {"identity": "提供元", "entrypoint": "利用手順", "license": "利用条件",
           "dependencies": "追加ソフト", "permissions": "必要な権限", "data_flow": "データの送信先",
           "account": "アカウント", "cost": "費用", "compatibility": "接続先での動作", "host_capabilities": "今使える機能の確認"},
    "zh": {"identity": "提供方", "entrypoint": "使用步骤", "license": "使用许可",
           "dependencies": "额外软件", "permissions": "所需权限", "data_flow": "数据发送方向",
           "account": "账号", "cost": "费用", "compatibility": "在当前软件中的兼容性", "host_capabilities": "当前已有能力的检查"}}


def enum(value, choices):
    return isinstance(value, str) and value in choices


def validate(req):
    required = {"action", "language", "task", "pool", "assessments", "available_tools"}
    require(isinstance(req, dict) and required <= set(req) <= required | {"preferences", "host_inventory_checked"})
    prefs = req.get("preferences", {"allow_new_accounts": False, "allow_setup": False})
    require(isinstance(prefs, dict) and set(prefs) == {"allow_new_accounts", "allow_setup"} and
            all(type(v) is bool for v in prefs.values()), "invalid_preferences")
    require(type(req.get("host_inventory_checked", False)) is bool, "invalid_observation")
    require(req["action"] == "recommend" and text(req["language"], 100))
    require(isinstance(req["task"], dict) and set(req["task"]) == {"summary", "desired_output"})
    require(all(text(v, 1000) for v in req["task"].values()))
    require(isinstance(req["pool"], dict) and req["pool"].get("action") == "evaluate")
    evaluated = catalog.handle(req["pool"])
    ids = {c["id"] for c in evaluated["candidates"]}
    candidate_sources = {c["id"]: set(c["source_ids"]) for c in evaluated["candidates"]}
    assessments = req["assessments"]
    require(isinstance(assessments, list) and len(assessments) <= 8, "invalid_assessment")
    seen = set()
    for a in assessments:
        require(isinstance(a, dict) and set(a) == {"id", "match", "reason", "source_ids"}, "invalid_assessment")
        require(text(a["id"]) and a["id"] in ids and a["id"] not in seen and
                enum(a["match"], MATCH) and text(a["reason"]), "invalid_assessment")
        require(catalog.refs(a["source_ids"], candidate_sources[a["id"]], a["match"] != "none"), "invalid_assessment")
        seen.add(a["id"])
    require(seen == ids, "missing_assessment")
    tools = req["available_tools"]
    require(isinstance(tools, list) and len(tools) <= 8, "invalid_observation")
    require(not tools or req.get("host_inventory_checked", False), "inventory_not_checked")
    seen = set()
    for t in tools:
        require(isinstance(t, dict) and set(t) == {
            "id", "name", "match", "reason", "permission", "scope", "data_flow", "limitations", "observation", "account", "cost"}, "invalid_observation")
        require(all(text(t[k]) for k in ("id", "name", "reason", "scope", "data_flow")), "invalid_observation")
        require(t["id"] not in seen and enum(t["match"], MATCH) and
                enum(t["permission"], {"available", "needs_approval", "unavailable", "unknown"}) and
                enum(t["account"], {"existing", "none", "new", "unknown"}) and
                enum(t["cost"], {"existing_quota", "free_software", "paid", "unknown"}) and
                strings(t["limitations"]), "invalid_observation")
        seen.add(t["id"])
        o = t["observation"]
        require(isinstance(o, dict) and set(o) == {"host", "checked_at", "evidence"}, "invalid_observation")
        require(o["host"] == evaluated["host"] and text(o["evidence"]), "invalid_observation")
        # Observations are session-specific. A previous snapshot must be checked again.
        require(o["checked_at"] == req["pool"]["as_of"], "stale_observation")
    return evaluated


def build_options(req, evaluated):
    options, excluded = [], []
    source_map = {s["id"]: s for s in req["pool"]["sources"]}
    prefs = req.get("preferences", {"allow_new_accounts": False, "allow_setup": False})
    for t in req["available_tools"]:
        if t["account"] == "new" and not prefs["allow_new_accounts"]:
            excluded.append({"type": "existing", "id": t["id"], "reason": "new_account_disallowed"})
            continue
        if t["permission"] == "unavailable" or t["match"] in {"none", "adjacent"}:
            excluded.append({"type": "existing", "id": t["id"], "reason":
                             "unavailable" if t["permission"] == "unavailable" else "not_task_solution"})
            continue
        state = {"available": "use_existing", "needs_approval": "permission_needed",
                 "unknown": "review_needed"}[t["permission"]]
        missing = [k for k in ("account", "cost") if t[k] == "unknown"]
        if t["permission"] == "unknown": missing.append("permissions")
        if missing: state = "review_needed"
        elif state == "use_existing" and t["account"] == "new": state = "choose_setup"
        if state == "choose_setup" and not prefs["allow_setup"]: state = "review_only"
        options.append({"type": "existing", "id": t["id"], "name": t["name"],
                        "state": state, "match": t["match"], "reason": t["reason"],
                        "scope": t["scope"], "data_flow": t["data_flow"],
                        "limitations": t["limitations"], "missing": missing, "source_ids": [],
                        "sources": [], "review_sources": [], "reason_is_inference": True,
                        "observation": t["observation"], "account": t["account"], "cost": t["cost"]})
    assessments = {a["id"]: a for a in req["assessments"]}
    for c in evaluated["candidates"]:
        a = assessments[c["id"]]
        if c["account"] == "new" and not prefs["allow_new_accounts"]:
            excluded.append({"type": "candidate", "id": c["id"], "reason": "new_account_disallowed"})
            continue
        if c["review_status"] == "blocked" or a["match"] in {"none", "adjacent"}:
            excluded.append({"type": "candidate", "id": c["id"], "reason":
                             "blocked" if c["review_status"] == "blocked" else "not_task_solution"})
            continue
        state = "choose_setup" if c["review_status"] == "ready_for_user_choice" else "review_needed"
        if state == "choose_setup" and (not prefs["allow_setup"] or not req.get("host_inventory_checked", False)):
            state = "review_only"
        options.append({"type": "candidate", "id": c["id"], "name": c["name"],
                        "state": state,
                        "match": a["match"], "reason": a["reason"], "scope": c["permissions"],
                        "data_flow": c["data_flow"], "limitations": [], "catalog_fit_description": c["fit"],
                        "missing": list(c["missing"]) + ([] if req.get("host_inventory_checked", False) else ["host_capabilities"]),
                        "source_ids": a["source_ids"], "locator": c["locator"],
                        "sources": [source_map[i] for i in a["source_ids"]],
                        "review_sources": [source_map[i] for i in c["source_ids"]], "reason_is_inference": True,
                        "account": c["account"], "cost": c["cost"], "compatibility": c["compatibility"],
                        "tier": c["tier"]})
    # Evidence gaps never win merely because a label says direct fit. Among
    # actionable options, task fit precedes publisher tier and additional setup.
    gate = {"use_existing": 0, "choose_setup": 0, "permission_needed": 1, "review_needed": 2, "review_only": 2}
    options.sort(key=lambda o: (gate[o["state"]], MATCH[o["match"]],
                               o["type"] != "existing", o["account"] == "new",
                               o["cost"] == "paid", catalog.TIERS.index(o.get("tier", "builtin")), o["id"]))
    return options, excluded


def render(req, option):
    language = req["language"].lower().replace("_", "-").split("-")[0]
    if language not in CHECK_LABELS:
        return None  # Host must render into the requested language; no English fallback.
    ja = language == "ja"
    if option is None:
        return {"summary": "この作業に合い、利用条件を確認できた候補はまだありません。" if ja else
                "目前还没有找到适合这项任务、且使用条件已核查的选项。",
                "next_step": "新しいソフトは追加せず、今の方法で小さな作業を一つ整理します。" if ja else
                "先保留当前工具，从手动整理一项小任务开始。"}
    o = option
    states = {
        "ja": {"use_existing": "まず、今のソフトにある機能を使う方法です。",
               "review_only": "比較用の候補です。今は追加せず、資料の確認にとどめます。",
               "choose_setup": "作業に合う候補です。追加するか選べる段階で、まだ設定していません。",
               "permission_needed": "作業に合う機能ですが、必要な権限の確認が先です。",
               "review_needed": "関連する候補ですが、利用条件に未確認の点があります。"},
        "zh": {"use_existing": "先使用当前软件已经具备的能力。",
               "review_only": "这是供比较的候选，目前只查看资料，不进行接入。",
               "choose_setup": "这个候选适合任务，已可供选择，目前还没有配置。",
               "permission_needed": "这个能力适合任务，但需要先确认所需权限。",
               "review_needed": "这是相关候选，使用条件仍有未核查之处。"}}
    if o["state"] == "use_existing":
        next_step = (f"対象を指定して「{req['task']['desired_output']}」と依頼できます。この説明ではまだ実行していません。" if ja else
                     f"指定要处理的材料后，可以直接说：“{req['task']['desired_output']}”。这份说明还没有执行操作。")
    elif o["state"] == "permission_needed":
        next_step = ("読む範囲と送信先を確認してから、利用中のソフトが示す承認手順に進みます。承認できなければ手動の方法を続けられます。" if ja else
                     "先确认读取范围和数据去向，再使用当前软件提供的真实授权流程；无法授权时可继续采用手动方式。")
    elif o["state"] == "choose_setup":
        next_step = ("追加する場合の変更内容を確認し、利用者が選んだ後に設定と動作確認へ進みます。" if ja else
                     "先查看接入将改变什么，由用户选择后，再进入配置和运行验证。")
    elif o["state"] == "review_only":
        next_step = ("原文を使って比較します。新しいアカウントやソフトを追加する操作には進みません。" if ja else
                     "使用原始资料进行比较，不进入新增账号或软件的操作。")
    else:
        next_step = ("未確認の条件を調べます。現時点では追加や実行を行いません。" if ja else
                     "继续核查未确认条件，目前不执行安装或操作。")
    missing = [CHECK_LABELS[language][k] for k in o["missing"]]
    accounts = {"ja": {"existing": "既存アカウントを利用", "none": "新規アカウント不要", "new": "別アカウントが必要", "unknown": "アカウント条件は未確認"},
                "zh": {"existing": "使用已有账号", "none": "无需新账号", "new": "需要额外账号", "unknown": "账号条件未确认"}}
    costs = {"ja": {"existing_quota": "現在のサービスの利用枠・契約を使用", "free_software": "ソフト自体は無料。モデルや外部サービスの費用は別途確認", "paid": "有料。金額と契約条件を確認", "unknown": "費用は未確認"},
             "zh": {"existing_quota": "使用当前服务的额度或合同", "free_software": "软件本身免费，模型与外部服务费用需另查", "paid": "需要付费，金额和合同条件需确认", "unknown": "费用未确认"}}
    limitations = list(o["limitations"])
    if o["type"] == "candidate" and o["compatibility"] != "tested":
        limitations.append("現在の環境での実動作は確認できていません。" if ja else "尚未确认它在当前环境中的实际运行情况。")
    return {"summary": states[language][o["state"]], "name": o["name"], "why": o["reason"],
            "coverage": ("この作業の一部だけを支援します。" if ja else "只能帮助完成这项任务的一部分。") if o["match"] == "partial" else
                        ("今回の作業に直接対応するという宿主AIの判断です。" if ja else "当前宿主AI判断它直接对应这项任务。"),
            "next_step": next_step, "account": accounts[language][o["account"]],
            "cost": costs[language][o["cost"]], "scope": o["scope"], "data_flow": o["data_flow"],
            "limitations": limitations, "unchecked": missing,
            "sources": o["sources"], "setup_sources": o["review_sources"],
            "attribution": "適合性は、利用者の作業と出典を照合した提案です。出典元の推薦ではありません。" if ja else
                           "适合度是根据你的任务与来源资料提出的判断，不代表来源方推荐了该方案。",
            "execution": "まだ実行・設定していません。" if ja else "尚未执行或配置。"}


def handle(req):
    evaluated = validate(req)
    options, excluded = build_options(req, evaluated)
    selection = options[0] if options else None
    message = render(req, selection)
    return {"ok": True, "host": evaluated["host"], "as_of": req["pool"]["as_of"], "language": req["language"],
            "preferences": req.get("preferences", {"allow_new_accounts": False, "allow_setup": False}),
            "host_inventory_checked": req.get("host_inventory_checked", False),
            "task": req["task"], "selection": selection, "alternatives": options[1:3],
            "excluded": excluded, "message": message,
            "host_translation_required": message is None,
            "evidence_verified": False, "executed": False, "persisted": False,
            "note": "Task fit and enabled-tool observations are supplied by the host; no semantic model, live tool check or permission grant occurs in this helper."}


def main():
    try:
        raw = sys.stdin.buffer.read(262145)
        require(len(raw) <= 262144)
        result = handle(json.loads(raw))
    except (ValueError, UnicodeError):
        result = {"ok": False, "error": "invalid_json"}
    except Error as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
