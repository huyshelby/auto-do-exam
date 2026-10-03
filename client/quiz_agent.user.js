// ==UserScript==
// @name         Autonomous Realistic Assessment QA Agent
// @namespace    https://local-rag-qa.internal/
// @version      1.0.0
// @description  Automated QA runner with local RAG reasoning and biological event simulation.
// @match        http*://*/*assessment*
// @match        http*://localhost*/*
// @match        http*://127.0.0.1*/*
// @match        file:///*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  console.info('[QA-Agent] Khởi tạo Autonomous Realistic Assessment QA Agent v1.0.0');

  const CONFIG = {
    SERVER_URL: 'http://127.0.0.1:8000/solve',
    SELECTORS: {
      QUESTION: '.question-text, .quiz-question, #questionTitle, .question-content',
      OPTION_CONTAINER: '.answers-list, .options-group, .choices',
      OPTION_ITEM: '.option-item, .answer-choice, label.radio, .answer-item',
      SUBMIT_BUTTON: '#btnSubmit, .btn-submit, .btn-next, button[type="submit"]',
    },
    AUTO_SUBMIT: false,
    AUTO_SUBMIT_DELAY_MS: 1500,
    POLL_INTERVAL_MS: 1200,
  };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // 1. Box-Muller Gaussian Simulator
  function randomGaussian(mean = 0, std = 1) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v) * std + mean;
  }

  function calculateLocalPacing(text) {
    const words = text.trim().split(/\s+/).length;
    const vRead = Math.max(2.0, randomGaussian(3.5, 0.4));
    const tRead = (words / vRead) * 1000;
    const tDecision = Math.max(600, randomGaussian(1200, 200));
    const tJitter = (Math.random() * 500) - 200;
    const total = Math.round(tRead + tDecision + tJitter);
    return Math.max(3000, Math.min(total, 6000));
  }

  // 2. DOM Extractor
  function extractQuizData() {
    const qEl = document.querySelector(CONFIG.SELECTORS.QUESTION);
    if (!qEl) return null;

    const question = qEl.innerText.trim();
    if (!question) return null;

    const optionEls = document.querySelectorAll(CONFIG.SELECTORS.OPTION_ITEM);
    if (optionEls.length === 0) return null;

    const options = [];
    const DEFAULT_KEYS = ['A', 'B', 'C', 'D', 'E', 'F'];

    optionEls.forEach((el, idx) => {
      // Ưu tiên đọc data-key hoặc input value
      let key = el.getAttribute('data-key') ||
                el.querySelector('input')?.value ||
                DEFAULT_KEYS[idx] ||
                String(idx + 1);

      key = key.trim().toUpperCase();

      // Loại bỏ tiền tố key dạng "A." hoặc "A)" khỏi text nếu có
      let text = el.innerText.trim();
      text = text.replace(/^[A-F\d][\.\)]\s*/i, '');

      options.push({
        key: key,
        text: text,
        domElement: el,
      });
    });

    return { question, options };
  }

  // 3. Realistic Event Cascade Dispatcher
  async function dispatchHumanClick(element) {
    if (!element) return;

    const rect = element.getBoundingClientRect();
    const offsetX = rect.width * (0.35 + Math.random() * 0.3);
    const offsetY = rect.height * (0.35 + Math.random() * 0.3);
    const clientX = rect.left + offsetX;
    const clientY = rect.top + offsetY;

    const baseProps = {
      bubbles: true,
      cancelable: true,
      composed: true,
      view: window,
      clientX: clientX,
      clientY: clientY,
      screenX: (window.screenX || 0) + clientX,
      screenY: (window.screenY || 0) + clientY,
    };

    // Chuỗi sự kiện tiêu chuẩn: pointer -> mouse -> down -> dwell -> up -> click
    element.dispatchEvent(new PointerEvent('pointerover', baseProps));
    element.dispatchEvent(new MouseEvent('mouseover', baseProps));

    element.dispatchEvent(new PointerEvent('pointermove', baseProps));
    element.dispatchEvent(new MouseEvent('mousemove', baseProps));

    await sleep(20 + Math.random() * 30);

    const downProps = { ...baseProps, button: 0, buttons: 1 };
    element.dispatchEvent(new PointerEvent('pointerdown', downProps));
    element.dispatchEvent(new MouseEvent('mousedown', downProps));

    if (typeof element.focus === 'function') {
      try { element.focus(); } catch (e) {}
    }

    // Thời gian giữ chuột tự nhiên (Dwell Time: 60ms - 110ms)
    await sleep(65 + Math.random() * 45);

    const upProps = { ...baseProps, button: 0, buttons: 0 };
    element.dispatchEvent(new PointerEvent('pointerup', upProps));
    element.dispatchEvent(new MouseEvent('mouseup', upProps));

    element.dispatchEvent(new MouseEvent('click', { ...upProps, detail: 1 }));

    // Cập nhật trạng thái radio input
    const radio = element.querySelector('input[type="radio"]') || (element.tagName === 'INPUT' ? element : null);
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event('change', { bubbles: true }));
      radio.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  // 4. Transport Layer: Hỗ trợ cả GM_xmlhttpRequest và standard fetch
  function sendSolveRequest(payload) {
    return new Promise((resolve, reject) => {
      if (typeof GM_xmlhttpRequest !== 'undefined') {
        GM_xmlhttpRequest({
          method: 'POST',
          url: CONFIG.SERVER_URL,
          headers: { 'Content-Type': 'application/json' },
          data: JSON.stringify(payload),
          timeout: 2500,
          onload: (res) => {
            if (res.status >= 200 && res.status < 300) {
              try { resolve(JSON.parse(res.responseText)); }
              catch (e) { reject(new Error('Phản hồi JSON không hợp lệ')); }
            } else {
              reject(new Error(`Server lỗi mã ${res.status}: ${res.responseText}`));
            }
          },
          ontimeout: () => reject(new Error('Yêu cầu tới Server vượt quá timeout')),
          onerror: (err) => reject(err),
        });
      } else {
        // Fallback fetch khi chạy trực tiếp trên Console
        fetch(CONFIG.SERVER_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
          .then((r) => r.json())
          .then(resolve)
          .catch(reject);
      }
    });
  }

  // 5. Execution State Machine
  let isProcessing = false;
  let lastProcessedQuestion = '';

  async function runCycle() {
    if (isProcessing) return;

    const quiz = extractQuizData();
    if (!quiz || quiz.question === lastProcessedQuestion) {
      return;
    }

    isProcessing = true;
    console.info('[QA-Agent] Phát hiện câu hỏi mới:', quiz.question);

    const payload = {
      question: quiz.question,
      options: quiz.options.map((o) => ({ key: o.key, text: o.text })),
    };

    try {
      const response = await sendSolveRequest(payload);
      console.info(`[QA-Agent] Đáp án nhận: [${response.selected_key}] | Tin cậy: ${response.confidence} | Cache: ${response.from_cache}`);

      // Cập nhật động dữ liệu trích dẫn pháp lý vào giao diện nếu có card
      const expCard = document.getElementById('explanationCard');
      if (expCard && response.matched_chunk) {
        const quoteEl = expCard.querySelector('.citation-quote');
        if (quoteEl) quoteEl.innerText = `“${response.matched_chunk}”`;
        const metaTags = expCard.querySelectorAll('.meta-tag strong');
        if (metaTags.length >= 2) {
          metaTags[0].innerText = `${Math.round(response.confidence * 100)}% (Local LLM)`;
          metaTags[1].innerText = response.from_cache ? 'In-Memory Cache O(1)' : 'BM25 In-memory + Local LLM';
        }
      }
      
      const delayMs = response.suggested_delay_ms || calculateLocalPacing(quiz.question);
      console.info(`[QA-Agent] Nhịp độ đọc sinh học: chờ ${delayMs}ms trước khi click...`);

      await sleep(delayMs);

      // Tìm phần tử DOM tương ứng để dispatch sự kiện
      const matchedOpt = quiz.options.find((o) => o.key.toUpperCase() === response.selected_key.toUpperCase());
      if (matchedOpt && matchedOpt.domElement) {
        console.info(`[QA-Agent] Thực thi tương tác chuột sinh học lên phương án [${matchedOpt.key}]`);
        await dispatchHumanClick(matchedOpt.domElement);
        lastProcessedQuestion = quiz.question;

        // Auto submit nếu bật cấu hình
        if (CONFIG.AUTO_SUBMIT) {
          await sleep(CONFIG.AUTO_SUBMIT_DELAY_MS);
          const submitBtn = document.querySelector(CONFIG.SELECTORS.SUBMIT_BUTTON);
          if (submitBtn) {
            console.info('[QA-Agent] Kích hoạt nút xác nhận đáp án...');
            await dispatchHumanClick(submitBtn);
          }
        }
      } else {
        console.warn(`[QA-Agent] Không tìm thấy phần tử DOM khớp với key: ${response.selected_key}`);
      }
    } catch (err) {
      console.error('[QA-Agent] Lỗi chu trình xử lý:', err);
    } finally {
      isProcessing = false;
    }
  }

  // Khởi chạy vòng lặp theo dõi DOM
  setInterval(runCycle, CONFIG.POLL_INTERVAL_MS);
  console.info('[QA-Agent] Sẵn sàng lắng nghe giao diện bài thi!');
})();
