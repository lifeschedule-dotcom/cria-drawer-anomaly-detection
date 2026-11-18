"use strict";

const ui = id => document.getElementById(id);
const video = ui("video");
const play = ui("live-play");
const axis = ui("axis");
const scoreChart = ui("score");
const waveChart = ui("wave");
const alertList = ui("live-alerts");
const frames = liveInput.frames;
const axes = liveInput.axes;
const model = rollingForest;
let horizon = frames.at(-1)[1];
let analyzer;
let nextFrame;
let waves;
let scores;
let activeAlert;
let scheduled = 0;
let lastPaint = 0;

ui("threshold").textContent = model.threshold.toFixed(2);
axes.forEach((label, index) => axis.add(new Option(label, index, false, label === "Fz")));

function clearAnalysis() {
  analyzer = createStreamAnalyzer(model, axes.length);
  nextFrame = 0;
  waves = axes.map(() => []);
  scores = [];
  activeAlert = null;
  alertList.replaceChildren();
  ui("no-alerts").hidden = false;
}

function recordAlert([time, , flagged]) {
  if (!flagged) {
    activeAlert = null;
    return;
  }
  if (!activeAlert || time - activeAlert.end > 0.19) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.addEventListener("click", () => {
      video.pause();
      video.currentTime = time;
    });
    item.append(button);
    alertList.append(item);
    activeAlert = { start: time, end: time, button };
    ui("no-alerts").hidden = true;
  }
  activeAlert.end = time;
  const { start, end, button } = activeAlert;
  button.textContent = start === end ? `${start.toFixed(2)}초 경보` : `${start.toFixed(2)}–${end.toFixed(2)}초 경보`;
}

function receiveThrough(time) {
  if (nextFrame && frames[nextFrame - 1][1] > time) clearAnalysis();
  while (nextFrame < frames.length && frames[nextFrame][1] <= time) {
    const frame = frames[nextFrame++];
    const [, timestamp, count] = frame;
    for (let index = 0; index < axes.length; index++) {
      let sum = 0;
      for (let sample = 0; sample < count; sample++) sum += frame[3 + sample * axes.length + index];
      waves[index].push([timestamp, count ? sum / count : null]);
    }
    const score = analyzer.receive(frame);
    if (score) {
      scores.push(score);
      recordAlert(score);
    }
  }
}

function displayAt(time) {
  receiveThrough(time + 0.00005);
  const sample = scores.at(-1);
  const current = sample && time - sample[0] < 0.19;
  const flagged = current && sample[2] === 1;
  const title = current ? flagged ? "이상 경보" : "모델 경보 없음" : "센서 데이터 대기";
  if (ui("status").textContent !== title) ui("status").textContent = title;
  ui("status").classList.toggle("active", Boolean(flagged));
  ui("clock").textContent = time.toFixed(2);
  ui("value").textContent = current ? `점수 ${sample[1].toFixed(2)}` : "—";
  ui("frame-count").textContent = nextFrame;
  ui("score-count").textContent = scores.length;
  const x = Math.min(time, horizon);
  drawChart(scoreChart, scores, 0, 1, x, { horizon, threshold: model.threshold });
  const wave = waves[Number(axis.value)];
  const values = wave.map(point => point[1]).filter(value => value !== null);
  const minimum = values.length ? Math.floor(Math.min(...values)) : 0;
  const maximum = Math.max(minimum + 1, Math.ceil(Math.max(...values)));
  drawChart(waveChart, wave, minimum, maximum, x, { horizon });
}

function tick(now) {
  scheduled = 0;
  if (now - lastPaint >= 40 && !video.seeking) {
    displayAt(video.currentTime);
    lastPaint = now;
  }
  if (!video.paused && !video.ended) scheduled = requestAnimationFrame(tick);
}

play.addEventListener("click", () => {
  if (video.paused) {
    if (video.ended) video.currentTime = 0;
    video.play().catch(() => { ui("media-error").hidden = false; });
  } else video.pause();
});
ui("live-reset").addEventListener("click", () => {
  video.pause();
  video.currentTime = 0;
  clearAnalysis();
  displayAt(0);
});
video.addEventListener("play", () => {
  play.textContent = "일시 정지";
  if (!scheduled) scheduled = requestAnimationFrame(tick);
});
video.addEventListener("pause", () => {
  play.textContent = video.currentTime ? "이어서 분석" : "분석 시작";
  if (!video.seeking) displayAt(video.currentTime);
});
video.addEventListener("ended", () => {
  play.textContent = "다시 분석";
  displayAt(video.currentTime);
});
video.addEventListener("loadedmetadata", () => { horizon = Math.min(video.duration, horizon); });
video.addEventListener("seeked", () => displayAt(video.currentTime));
video.addEventListener("error", () => { ui("media-error").hidden = false; });
video.querySelector("source").addEventListener("error", () => { ui("media-error").hidden = false; });
axis.addEventListener("change", () => displayAt(video.currentTime));
new ResizeObserver(() => displayAt(video.currentTime)).observe(scoreChart);
clearAnalysis();
displayAt(0);
