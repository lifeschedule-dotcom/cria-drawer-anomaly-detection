"use strict";

(() => {
  const options = [...document.querySelectorAll("[data-source]")];
  const recordedVideo = document.getElementById("video");
  const preview = document.getElementById("camera-preview");
  const connect = document.getElementById("camera-connect");
  const disconnect = document.getElementById("camera-disconnect");
  const message = document.getElementById("camera-message");
  let selected;
  let cameraStream;
  let requestNumber = 0;

  function stopCamera() {
    requestNumber++;
    cameraStream?.getTracks().forEach(track => track.stop());
    cameraStream = undefined;
    preview.srcObject = null;
    preview.hidden = true;
    disconnect.hidden = true;
    connect.disabled = false;
  }

  for (const option of options) {
    option.addEventListener("click", () => {
      const input = option.dataset.source;
      if (selected === input) return;
      if (selected === "camera") stopCamera();
      if (selected === "replay") recordedVideo.pause();
      selected = input;
      for (const item of options) {
        const active = item === option;
        item.setAttribute("aria-pressed", String(active));
        document.getElementById(item.getAttribute("aria-controls")).hidden = !active;
      }
      if (input === "camera") message.textContent = "";
    });
  }

  connect.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      message.textContent = "현재 브라우저에서 카메라에 접근할 수 없습니다.";
      return;
    }
    const request = ++requestNumber;
    connect.disabled = true;
    message.textContent = "카메라 연결을 기다리는 중입니다.";
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (request !== requestNumber || selected !== "camera") {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      cameraStream = stream;
      preview.srcObject = stream;
      preview.hidden = false;
      disconnect.hidden = false;
      message.textContent = "카메라 연결됨 · 영상 미리보기";
      for (const track of stream.getVideoTracks()) {
        track.addEventListener("ended", () => {
          if (cameraStream !== stream) return;
          stopCamera();
          message.textContent = "카메라 연결이 종료됐습니다.";
        });
      }
    } catch (error) {
      if (request !== requestNumber) return;
      connect.disabled = false;
      message.textContent = error.name === "NotAllowedError"
        ? "카메라 권한이 필요합니다. 브라우저의 카메라 설정을 확인해 주세요."
        : "카메라를 열 수 없습니다. 연결 상태나 다른 앱에서 사용 중인지 확인해 주세요.";
    }
  });

  disconnect.addEventListener("click", () => {
    stopCamera();
    message.textContent = "카메라 연결을 해제했습니다.";
    connect.focus();
  });
  window.addEventListener("pagehide", stopCamera);
})();
