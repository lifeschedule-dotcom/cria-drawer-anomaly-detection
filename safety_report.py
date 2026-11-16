"""Read-only replay: detector evidence + illustrative risk rubric + local source retrieval."""
import argparse
import csv
import json
import os
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent


def load_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def read_detection(episode_id, model):
    if episode_id not in (8, 17, 149) or model not in ("random_forest", "lstm", "logistic_regression"):
        raise ValueError("Choose a saved replay episode and model.")
    with (ROOT / "results" / f"episode_{episode_id:06}_scores.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    groups = []
    prev = None
    for row in rows:
        if row[model + "_flag"] != "1":
            prev = None
            continue
        frame, sec = int(row["frame_index"]), round(float(row["time_s"]), 3)
        if prev is None or frame - prev != 5:
            groups.append([sec, sec])
        else:
            groups[-1][1] = sec
        prev = frame
    metadata = load_json("data/meta/annotation.json")["episodes"]
    annotation = next(e for e in metadata.values() if e["episode_index"] == episode_id)
    return {
        "episode_id": episode_id, "model": model,
        "threshold": load_json("results/model_comparison.json")["models"][model]["threshold"],
        "flagged_times_s": groups,
        "manual_times_s": [[round(a / 30, 3), round(b / 30, 3)] for a, b in annotation["anomaly"]["manual"]["ranges"]],
    }


EXPLAIN = {"S": "상해 심각도", "F": "위험 노출 빈도·시간", "O": "위험 사건의 가능성", "A": "회피의 어려움"}


def score_risk(scenario):
    case = load_json("safety_scenarios.json")[scenario]
    missing = [k for k in EXPLAIN if case[k] is None]
    values = {k: case[k] for k in EXPLAIN}
    if missing:
        return {"scenario": scenario, "assumption": case["description"], "inputs": values,
                "missing": missing, "total": None, "demo_level": "판정 보류"}
    total = sum(values.values())
    return {"scenario": scenario, "assumption": case["description"], "inputs": values,
            "missing": [], "total": total, "demo_level": "고" if total >= 10 else "중" if total >= 7 else "저"}


def retrieve_sources(query, limit=4):
    corpus = load_json("safety_sources.json")
    documents = [f"{r['title']} {r['tags']} {r['summary']}" for r in corpus]
    vectors = TfidfVectorizer(analyzer="char", ngram_range=(2, 4)).fit_transform(documents + [query])
    scores = (vectors[:-1] @ vectors[-1].T).toarray().ravel()
    ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], corpus[i]["id"]))
    return [corpus[i] for i in ranked if scores[i] > 0][:limit]


QUERY = "위험성평가 산업부 실증특례 IGRIS-C 서랍 끼임 로봇 방호 SFOA 감소대책 재평가"


SITE_SCENARIOS = {
    "unknown": ("미확인", "레이아웃과 작업 관찰 기록을 확보해 손 접근 여부를 확인한다."),
    "reachable": ("접근 가능으로 가정", "접근 경로, 최소 틈새, 개입 작업을 확인하고 접근 제거·분리 대책을 검토한다."),
    "separation_planned": ("물리적 차단을 설계했다고 가정", "설치 상태, 우회 접근 가능성, 정비 시 접근과 방호 해제 조건을 확인한다."),
}


def prepare_site_review(evidence, scenario):
    """Prepare evidence requests. A scenario input describes an assumption, not a field result."""
    if scenario not in SITE_SCENARIOS:
        raise ValueError(f"Select one of: {', '.join(SITE_SCENARIOS)}")
    assumption, next_step = SITE_SCENARIOS[scenario]
    return {
        "episode_id": evidence["episode_id"],
        "flagged_times_s": evidence["flagged_times_s"],
        "access_assumption": assumption,
        "first_check": next_step,
        "evidence_to_collect": [
            ("작업과 배치", "도면·사진에 그리퍼, 작업물, 위험점, 접근 경로와 최소 틈새를 표시한다."),
            ("운전 모드·노출", "자동 운전, 걸림 해소, 정비에서 누가 얼마나 자주 개입하는지 기록한다."),
            ("감소조치", "적용한 가드·인터록 등과 그 설치 확인 결과를 기록한다."),
            ("기능 검증", "접근 시 정지를 채택했다면 적용 조건에서 정지 시간·거리와 재기동 방지 결과를 첨부한다."),
        ],
        "actual_risk": "판정 보류",
        "reason": "현장 접근·노출과 감소조치 이행·검증 자료가 제공되지 않았다.",
    }


def render_site_review(review):
    lines = [f"# CRIA {review['episode_id']} 사전 검토 기록", "",
             f"- 경보 시각(초): `{review['flagged_times_s']}`",
             f"- 가정한 접근 조건: {review['access_assumption']}",
             f"- 우선 확인: {review['first_check']}",
             f"- 실제 위험등급: **{review['actual_risk']}** — {review['reason']}", "",
             "| 확인 항목 | 현장에서 확보할 증빙 | 현장 확인 상태 |", "| --- | --- | --- |"]
    lines.extend(f"| {item} | {request} | 미확인 |" for item, request in review["evidence_to_collect"])
    lines += ["", "참고: [SafetyDesigner 위험성평가 5단계](https://doc.safetics.io/sfd-docs/) · "
              "[감소대책 실행현황](https://doc.safetics.io/docs/ra-est-eval/) · "
              "[고용노동부 사업장 위험성평가 지침](https://moel.go.kr/info/lawinfo/instruction/view.do?bbs_seq=20261100126)"]
    return "\n".join(lines) + "\n"


def make_report(evidence, base, cases, sources, briefing=None):
    model = evidence["model"]
    lines = [f"# 서랍 열기 {evidence['episode_id']}번 | 위험성평가 실습 리포트", "",
             "실습 범위: 서랍과 고정 프레임 사이에 손이 끼이는 한 가지 가상 상황. 실제 사고나 인증 결과는 확인되지 않았다.", "",
             "## 1. CRIA에서 확인한 사실", "",
             f"- 수동 이상 주석(초): `{evidence['manual_times_s']}`",
             f"- {model} 탐지(첫·마지막 창 시각, 초): `{evidence['flagged_times_s']}`. 검증 임계값: `{evidence['threshold']:.3f}`.",
             f"- 데이터만으로는 **{base['demo_level']}**. 확인이 필요한 현장 입력: {', '.join(base['missing'])}.", "",
             "## 2. 작업 환경을 바꿔 본 교육용 시나리오", "",
             "S=상해 심각도, F=노출 빈도·시간, O=위험 사건 가능성, A=회피의 어려움. 각각 1~3의 예시 입력을 사용한다.",
             "교육용 합계: 4~6 저, 7~9 중, 10~12 고. 입력이 비면 보류한다. 세이프틱스 제품 산식이나 법정 기준은 적용하지 않았다.", "",
             "| 시나리오 | S/F/O/A | 합계 | 교육용 등급 |", "| --- | --- | ---: | --- |"]
    lines += [f"| {c['assumption']} | {'/'.join(str(c['inputs'][k]) for k in EXPLAIN)} | {c['total']} | {c['demo_level']} |" for c in cases]
    lines += ["", "## 3. 현장에서 남길 증거", "",
              "- 도면·작업 관찰: 최소 틈새, 손 접근 경로, 노출 시간·빈도, 정상 운전·걸림 해소·정비의 구분.",
              "- 방호를 선택한 뒤 기능 확인: 접근 감지부터 정지까지의 시간·거리와 예기치 않은 재기동 방지. 접촉을 허용하는 설계라면 적용 기준 및 시험 조건에 따라 접촉력·압력도 검증한다.",
              "- 조치 전후를 따로 기록한다. 설치·검증 결과가 없으면 잔여 위험은 판정 보류한다."]
    if briefing:
        lines += ["", "## 4. 모델 브리핑 (사람 검토용)", "", briefing]
    lines += ["", "## 검색된 근거", ""]
    lines += [f"- [{d['id']}: {d['title']}]({d['url']}) — {d['summary']}" for d in sources]
    return "\n".join(lines) + "\n"


def offline_report(episode_id, model):
    evidence = read_detection(episode_id, model)
    base = score_risk("unassessed")
    cases = [score_risk(k) for k in load_json("safety_scenarios.json") if k != "unassessed"]
    sources = retrieve_sources(QUERY, limit=6)
    return make_report(evidence, base, cases, sources, briefing=None), {"evidence": evidence, "base": base, "cases": cases, "sources": sources}


def live_briefing(model_id, episode_id, detector="random_forest", client=None):
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    # Arguments are validated against fixed episode/scenario data. Both tools are read-only.
    funcs = {"read_detection": read_detection, "score_risk": score_risk, "retrieve_sources": retrieve_sources}
    spec = {"read_detection": {"episode_id": {"type": "integer", "enum": [149, 8, 17]}, "model": {"type": "string", "enum": ["random_forest", "lstm", "logistic_regression"]}},
            "score_risk": {"scenario": {"type": "string", "enum": list(load_json("safety_scenarios.json"))}},
            "retrieve_sources": {"query": {"type": "string"}}}
    tools = [{"type": "function", "name": name, "strict": True,
              "description": {"read_detection": "Read saved sensor detections", "score_risk": "Score an illustrative teaching scenario", "retrieve_sources": "Search the verified local source notes"}[name],
              "parameters": {"type": "object", "properties": params, "required": list(params), "additionalProperties": False}}
             for name, params in spec.items()]
    dialogue = [{"role": "user", "content": f"{episode_id}번 {detector} 탐지를 조회하고, unassessed와 access_open 위험 등급을 도구로 구한 뒤, '{QUERY}'로 근거를 검색해. 확인한 사실과 가정을 구분하고 한국어 5문장 이내로 브리핑해. 근거는 [문서 ID]로 표시하고 확인 못 한 현장 수치는 쓰지 마."}]
    log = []
    for _ in range(8):
        response = client.responses.create(model=model_id, instructions="교육용 로봇 작업 위험성평가 초안. 승인·인증·실제 사고로 표현하지 않는다. 도구의 결과와 원문 요약만 근거로 쓴다.",
                                           input=dialogue, tools=tools, store=False)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            if {name for name, _, _ in log} >= set(funcs) and response.output_text.strip():
                return response.output_text.strip(), log
            raise RuntimeError("The model did not complete all three tool calls and a briefing.")
        dialogue.extend(response.output)
        for call in calls:
            args = json.loads(call.arguments)
            data = funcs[call.name](**args)
            log.append((call.name, args, data))
            dialogue.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
    raise RuntimeError("Tool loop exceeded its round limit.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=int, default=149, choices=(149, 8, 17))
    parser.add_argument("--detector", default="random_forest", choices=("random_forest", "lstm", "logistic_regression"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live-model", default=None, help="Optional model ID; requires openai package and OPENAI_API_KEY.")
    mode.add_argument("--precheck", choices=SITE_SCENARIOS, help="Generate an offline site evidence request for the selected assumption.")
    options = parser.parse_args()
    if options.precheck:
        review = prepare_site_review(read_detection(options.episode, options.detector), options.precheck)
        path = ROOT / "results" / f"episode_{options.episode:06}_precheck_{options.precheck}.md"
        path.write_text(render_site_review(review), encoding="utf-8")
        print(path.relative_to(ROOT))
        return
    report, trace = offline_report(options.episode, options.detector)
    suffix = "offline"
    if options.live_model:
        if not os.getenv("OPENAI_API_KEY"):
            parser.error("Set OPENAI_API_KEY in your environment for live mode.")
        briefing, calls = live_briefing(options.live_model, options.episode, options.detector)
        report = make_report(**trace, briefing=briefing)
        trace["responses_tool_calls"] = calls
        suffix = "live"
    name = f"episode_{options.episode:06}_risk_{suffix}"
    (ROOT / "results" / f"{name}.md").write_text(report, encoding="utf-8")
    (ROOT / "results" / f"{name}_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"results/{name}.md")


if __name__ == "__main__":
    main()
