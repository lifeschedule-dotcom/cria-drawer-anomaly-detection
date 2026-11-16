"use strict";

function summarizeSensorWindow(frames, axes) {
  const sampleCount = frames.length * 4;
  const samples = frames.flatMap(frame => frame.slice(3));
  const mean = Array(axes).fill(0);
  const deviation = Array(axes).fill(0);
  const peak = Array(axes).fill(0);
  const start = Array(axes).fill(0);
  const end = Array(axes).fill(0);
  const round = Math.fround;
  for (let sample = 0; sample < sampleCount; sample++) {
    for (let axis = 0; axis < axes; axis++) {
      const value = samples[sample * axes + axis];
      mean[axis] = round(mean[axis] + value);
      peak[axis] = Math.max(peak[axis], Math.abs(value));
      if (sample < 4) start[axis] = round(start[axis] + value);
      if (sample >= sampleCount - 4) end[axis] = round(end[axis] + value);
    }
  }
  for (let axis = 0; axis < axes; axis++) mean[axis] = round(mean[axis] / sampleCount);
  for (let sample = 0; sample < sampleCount; sample++) {
    for (let axis = 0; axis < axes; axis++) {
      const delta = round(samples[sample * axes + axis] - mean[axis]);
      deviation[axis] = round(deviation[axis] + round(delta * delta));
    }
  }
  return [
    ...mean, ...deviation.map(sum => round(Math.sqrt(round(sum / sampleCount)))), ...peak,
    ...end.map((sum, axis) => round(round(sum / 4) - round(start[axis] / 4))),
  ];
}

function predictForest(features, trees) {
  let total = 0;
  for (const nodes of trees) {
    let node = nodes[0];
    while (node[0] >= 0) {
      const [feature, threshold, left, right] = node;
      node = nodes[features[feature] <= threshold ? left : right];
    }
    total += node[1];
  }
  return total / trees.length;
}

function createStreamAnalyzer(model, axes) {
  const window = [];
  return {
    receive(frame) {
      window.push(frame);
      if (window.length > model.windowFrames) window.shift();
      const [index, time] = frame;
      const strideAligned = (index + 1 - model.windowFrames) % model.stride === 0;
      if (!strideAligned || window.length < model.windowFrames || !window.every(row => row[2] === 4)) return null;
      const features = summarizeSensorWindow(window, axes);
      const score = predictForest(features, model.trees);
      return [time, score, Number(score >= model.threshold)];
    },
  };
}
