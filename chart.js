"use strict";

function drawChart(canvas, points, minimum, maximum, time, { horizon, annotation = [], threshold }) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  const scale = window.devicePixelRatio || 1;
  const pixelWidth = Math.round(width * scale);
  const pixelHeight = Math.round(height * scale);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);

  const left = 36;
  const right = width - 13;
  const top = 11;
  const bottom = height - 22;
  const x = seconds => left + seconds / horizon * (right - left);
  const y = value => bottom - (value - minimum) / (maximum - minimum) * (bottom - top);
  context.fillStyle = "#f8faf9";
  context.fillRect(left, top, right - left, bottom - top);
  context.fillStyle = "#f8e8c1";
  for (const [start, end] of annotation) context.fillRect(x(start), top, x(end) - x(start), bottom - top);

  context.font = "11px Malgun Gothic, sans-serif";
  context.fillStyle = "#536b74";
  context.strokeStyle = "#d9e5e2";
  for (const value of [minimum, (minimum + maximum) / 2, maximum]) {
    context.beginPath();
    context.moveTo(left, y(value));
    context.lineTo(right, y(value));
    context.stroke();
    context.fillText(Number(value.toFixed(1)).toString(), 2, y(value) + 4);
  }
  const tick = width < 380 ? 10 : 5;
  for (let second = 0; second <= horizon; second += tick) context.fillText(`${second}초`, x(second) - 6, height - 6);

  if (threshold !== undefined) {
    context.setLineDash([4, 3]);
    context.strokeStyle = "#996b35";
    context.beginPath();
    context.moveTo(left, y(threshold));
    context.lineTo(right, y(threshold));
    context.stroke();
    context.setLineDash([]);
  }
  context.strokeStyle = "#137b7c";
  context.lineWidth = 1.55;
  context.beginPath();
  let connected = false;
  for (const [seconds, value] of points) {
    if (seconds > time + 0.001) break;
    if (value === null) {
      connected = false;
      continue;
    }
    if (connected) context.lineTo(x(seconds), y(value));
    else context.moveTo(x(seconds), y(value));
    connected = true;
  }
  context.stroke();
  context.fillStyle = "#b3402c";
  if (threshold !== undefined) {
    for (const [seconds, value, flagged] of points) {
      if (seconds > time + 0.001) break;
      if (!flagged) continue;
      context.beginPath();
      context.arc(x(seconds), y(value), 2.3, 0, Math.PI * 2);
      context.fill();
    }
  }
  context.strokeStyle = "#244957";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(x(time), top);
  context.lineTo(x(time), bottom);
  context.stroke();
}

