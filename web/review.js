"use strict";

const ui = id => document.getElementById(id);
const video = ui("video");
const timeline = ui("timeline");
const axis = ui("axis");
const scoreChart = ui("score");
const waveChart = ui("wave");
const alerts = ui("alerts");
let horizon = episode.waveform.at(-1)[0];
let reviewKey = "unknown";

episode.axes.forEach((name, index) => axis.add(new Option(name, index, false, name === "Fz")));
episode.alerts.forEach(([start, end]) => {
  const button = document.createElement("button");
  button.type = "button";
  const span = start === end ? start.toFixed(2) : `${start.toFixed(2)}–${end.toFixed(2)}`;
  button.textContent = `${span}초 경보`;
  button.addEventListener("click", () => jump(start, false));
  alerts.append(button);
});

function displayAt(rawTime) {
  const time = Math.max(0, Math.min(rawTime, horizon));
  const savedScore = episode.scores.findLast(row => row[0] <= time + 0.001);
  const flagged = savedScore?.[2] === 1 && time - savedScore[0] < 0.19;
  const title = flagged ? "이상 경보" : savedScore && time - savedScore[0] < 0.19 ? "모델 경보 없음" : "평가 창 대기";
  if (ui("status").textContent !== title) ui("status").textContent = title;
  ui("status").classList.toggle("active", flagged);
  ui("clock").textContent = time.toFixed(2);
  timeline.value = time;
  ui("value").textContent = savedScore && time - savedScore[0] < 0.19 ? `점수 ${savedScore[1].toFixed(2)}` : "점수 —";
  drawChart(scoreChart, episode.scores, 0, 1, time, { horizon, annotation: episode.manual, threshold: episode.threshold });

  const column = Number(axis.value) + 1;
  const wave = episode.waveform.map(row => [row[0], row[column]]);
  const values = wave.map(row => row[1]).filter(value => value !== null);
  const lower = Math.floor(Math.min(...values));
  const upper = Math.max(lower + 1, Math.ceil(Math.max(...values)));
  drawChart(waveChart, wave, lower, upper, time, { horizon, annotation: episode.manual });
}

function jump(seconds, play) {
  if (video.readyState < 1) {
    video.addEventListener("loadedmetadata", () => jump(seconds, play), {once: true});
    video.load();
    return;
  }
  if (!play) video.pause();
  video.currentTime = Math.min(seconds, video.duration);
  displayAt(video.currentTime);
  if (play) video.play().catch(() => { ui("media-error").hidden = false; });
}

function updateReview(key) {
  reviewKey = key;
  const review = episode.cases[key];
  ui("first-check").textContent = `우선 확인 · ${review.first_check}`;
  ui("risk-grade").textContent = review.actual_risk;
  ui("risk-reason").textContent = review.reason;
  const evidence = ui("evidence-list");
  evidence.replaceChildren();
  for (const [title, description] of review.evidence_to_collect) {
    const term = document.createElement("dt");
    const definition = document.createElement("dd");
    term.textContent = title;
    definition.textContent = description;
    evidence.append(term, definition);
  }
}

ui("play").addEventListener("click", () => jump(0, true));
ui("alert-play").addEventListener("click", () => jump(episode.alerts[0][0] - 2, true));
timeline.addEventListener("input", () => jump(Number(timeline.value), false));
axis.addEventListener("change", () => displayAt(video.currentTime));
video.addEventListener("error", () => { ui("media-error").hidden = false; });
video.querySelector("source").addEventListener("error", () => { ui("media-error").hidden = false; });
video.addEventListener("loadedmetadata", () => {
  horizon = Math.min(video.duration, episode.waveform.at(-1)[0]);
  timeline.max = horizon;
  displayAt(video.currentTime);
});
for (const event of ["timeupdate", "seeked", "pause", "ended"]) {
  video.addEventListener(event, () => displayAt(video.currentTime));
}
new ResizeObserver(() => displayAt(video.currentTime)).observe(scoreChart);
document.querySelectorAll('input[name="condition"]').forEach(input => {
  input.addEventListener("change", () => updateReview(input.value));
});
ui("download").addEventListener("click", () => {
  const report = episode.cases[reviewKey].report;
  const url = URL.createObjectURL(new Blob([report], {type: "text/markdown;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = `cria-149-precheck-${reviewKey}.md`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
updateReview("unknown");
displayAt(0);
